//! Deadlines for small commands; binary transfers use an idle clock.
use std::future::Future;
use std::sync::{
    Arc,
    atomic::{AtomicU64, Ordering},
};
use std::time::Duration;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::time::Instant;

pub(super) fn append_response(buffer: &mut Vec<u8>, data: &[u8]) -> Result<(), String> {
    if data.len() > orcan_studio_core::RESPONSE_LIMIT.saturating_sub(buffer.len()) {
        return Err(
            "Command response exceeded the 16 MiB limit; refresh before retrying.".to_owned(),
        );
    }
    buffer.extend_from_slice(data);
    Ok(())
}

pub(super) async fn read_response(
    stream: impl tokio::io::AsyncRead + Unpin,
) -> Result<Vec<u8>, String> {
    let mut buffer = Vec::new();
    stream
        .take((orcan_studio_core::RESPONSE_LIMIT + 1) as u64)
        .read_to_end(&mut buffer)
        .await
        .map_err(|e| e.to_string())?;
    if buffer.len() > orcan_studio_core::RESPONSE_LIMIT {
        return Err(
            "Command response exceeded the 16 MiB limit; refresh before retrying.".to_owned(),
        );
    }
    Ok(buffer)
}

/// Armed until both the helper and its pipes have finished. Dropping an outer
/// future must stop descendants too, not only Tokio's direct child.
pub(super) struct ProcessTree(pub Option<u32>);
impl Drop for ProcessTree {
    fn drop(&mut self) {
        if let Some(pid) = self.0 {
            orcan_studio_core::terminate_process_tree(pid);
        }
    }
}

pub(super) async fn deadline<T>(
    duration: Duration,
    future: impl Future<Output = Result<T, String>>,
) -> Result<T, String> {
    tokio::time::timeout(duration, future).await.map_err(|_| {
        "Operation timed out; remote changes are not rolled back. Refresh before retrying."
            .to_owned()
    })?
}

pub(super) async fn capture(
    mut command: tokio::process::Command,
    input: Option<&[u8]>,
    duration: Duration,
) -> Result<std::process::Output, String> {
    use std::process::Stdio;
    command
        .kill_on_drop(true)
        .stdin(if input.is_some() {
            Stdio::piped()
        } else {
            Stdio::null()
        })
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(unix)]
    command.process_group(0);
    let mut child = command.spawn().map_err(|e| e.to_string())?;
    let pid = child.id().ok_or("Command has no process ID")?;
    let mut tree = ProcessTree(Some(pid));
    let mut stdin = child.stdin.take();
    let stdout = child.stdout.take().ok_or("Command has no stdout")?;
    let stderr = child.stderr.take().ok_or("Command has no stderr")?;
    let result = deadline(duration, async {
        let write = async {
            if let (Some(mut stream), Some(bytes)) = (stdin.take(), input) {
                stream.write_all(bytes).await?;
                stream.shutdown().await?;
            }
            Ok::<_, std::io::Error>(())
        };
        let (_, status, out, err) = tokio::try_join!(
            async { write.await.map_err(|e| e.to_string()) },
            async { child.wait().await.map_err(|e| e.to_string()) },
            read_response(stdout),
            read_response(stderr)
        )?;
        Ok(std::process::Output {
            status,
            stdout: out,
            stderr: err,
        })
    })
    .await;
    if result.is_err() {
        orcan_studio_core::terminate_process_tree(pid);
        let _ = child.kill().await;
    }
    tree.0 = None;
    result
}

#[derive(Clone)]
pub(super) struct Activity {
    started: Instant,
    last: Arc<AtomicU64>,
}

/// Compatibility installation endpoints still stream source directly into the
/// receiver. Drain every diagnostic pipe concurrently, under the same idle rule.
pub(super) async fn pipe(
    mut source: tokio::process::Command,
    mut target: tokio::process::Command,
) -> Result<(std::process::Output, std::process::Output), String> {
    use std::process::Stdio;
    source
        .kill_on_drop(true)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    target
        .kill_on_drop(true)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(unix)]
    {
        source.process_group(0);
        target.process_group(0);
    }
    let mut source = source.spawn().map_err(|e| e.to_string())?;
    let mut source_tree = ProcessTree(source.id());
    let mut target = target.spawn().map_err(|e| e.to_string())?;
    let mut target_tree = ProcessTree(target.id());
    let source_out = source.stdout.take().ok_or("Source has no stdout")?;
    let source_err = source.stderr.take().ok_or("Source has no stderr")?;
    let mut target_in = target.stdin.take().ok_or("Destination has no stdin")?;
    let target_out = target.stdout.take().ok_or("Destination has no stdout")?;
    let target_err = target.stderr.take().ok_or("Destination has no stderr")?;
    let activity = Activity::new();
    let result = activity.guard(Duration::from_secs(300), async {
        let copy = async {
            let mut reader = super::transfer_progress::ProgressReader::new(source_out, |_| activity.touch());
            tokio::io::copy(&mut reader, &mut target_in).await.map_err(|e| e.to_string())?;
            target_in.shutdown().await.map_err(|e| e.to_string())?;
            drop(target_in);
            Ok(())
        };
        let (_, source_status, target_status, source_err, target_out, target_err) = tokio::try_join!(
            copy,
            async { source.wait().await.map_err(|e| e.to_string()) },
            async { target.wait().await.map_err(|e| e.to_string()) },
            read_response(source_err), read_response(target_out), read_response(target_err)
        )?;
        Ok((std::process::Output { status: source_status, stdout: Vec::new(), stderr: source_err }, std::process::Output { status: target_status, stdout: target_out, stderr: target_err }))
    }).await;
    if result.is_ok() {
        source_tree.0 = None;
        target_tree.0 = None;
    }
    result
}
impl Activity {
    pub fn new() -> Self {
        Self {
            started: Instant::now(),
            last: Arc::new(AtomicU64::new(0)),
        }
    }
    pub fn touch(&self) {
        self.last
            .store(self.started.elapsed().as_millis() as u64, Ordering::Relaxed);
    }
    pub async fn guard<T>(
        &self,
        idle: Duration,
        future: impl Future<Output = Result<T, String>>,
    ) -> Result<T, String> {
        self.touch();
        let stalled = async {
            loop {
                tokio::time::sleep(idle.min(Duration::from_secs(1))).await;
                if self
                    .started
                    .elapsed()
                    .as_millis()
                    .saturating_sub(self.last.load(Ordering::Relaxed) as u128)
                    >= idle.as_millis()
                {
                    break;
                }
            }
        };
        tokio::select! { result = future => result, _ = stalled => Err("Transfer made no progress before the idle deadline. Refresh the destination; retained payloads can be resumed.".to_owned()) }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[cfg(unix)]
    #[tokio::test]
    async fn pipeline_streams_binary_and_drains_source_and_receiver_logs() {
        let mut source = tokio::process::Command::new("sh");
        source.args([
            "-c",
            "head -c 100000 /dev/zero >&2; head -c 200000 /dev/zero",
        ]);
        let mut target = tokio::process::Command::new("sh");
        target.args(["-c", "head -c 100000 /dev/zero >&2; wc -c"]);
        let (source, target) = deadline(Duration::from_secs(3), pipe(source, target))
            .await
            .unwrap();
        assert!(source.status.success() && target.status.success());
        assert_eq!(source.stderr.len(), 100000);
        assert_eq!(target.stderr.len(), 100000);
        assert_eq!(String::from_utf8(target.stdout).unwrap().trim(), "200000");
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn stdin_payload_closes_before_waiting_for_the_command() {
        let command = tokio::process::Command::new("cat");
        let output = capture(command, Some(b"payload"), Duration::from_secs(2))
            .await
            .unwrap();
        assert!(output.status.success());
        assert_eq!(output.stdout, b"payload");
    }

    #[tokio::test]
    async fn response_limit_rejects_excess_without_truncating_json() {
        let bytes = vec![0; orcan_studio_core::RESPONSE_LIMIT + 1];
        assert!(
            read_response(bytes.as_slice())
                .await
                .unwrap_err()
                .contains("16 MiB")
        );
        let mut buffer = vec![0; orcan_studio_core::RESPONSE_LIMIT];
        assert!(append_response(&mut buffer, b"x").is_err());
        assert_eq!(buffer.len(), orcan_studio_core::RESPONSE_LIMIT);
        assert_eq!(read_response(&b"valid"[..]).await.unwrap(), b"valid");
    }
    #[tokio::test(start_paused = true)]
    async fn deadline_bounds_an_unresponsive_operation() {
        assert!(
            deadline::<()>(Duration::from_millis(10), std::future::pending())
                .await
                .unwrap_err()
                .contains("not rolled back")
        );
    }
    #[tokio::test(start_paused = true)]
    async fn idle_guard_accepts_progress_beyond_one_deadline() {
        let activity = Activity::new();
        activity
            .guard(Duration::from_millis(40), async {
                for _ in 0..5 {
                    tokio::time::sleep(Duration::from_millis(10)).await;
                    activity.touch();
                }
                Ok(())
            })
            .await
            .unwrap();
        assert!(
            activity
                .guard::<()>(Duration::from_millis(10), std::future::pending())
                .await
                .unwrap_err()
                .contains("resumed")
        );
    }
    #[cfg(unix)]
    #[tokio::test]
    async fn command_timeout_also_bounds_inherited_pipes() {
        let mut command = tokio::process::Command::new("bash");
        command.args(["-c", "sleep 30 & exit 0"]);
        assert!(
            capture(command, None, Duration::from_millis(30))
                .await
                .is_err()
        );
    }
}
