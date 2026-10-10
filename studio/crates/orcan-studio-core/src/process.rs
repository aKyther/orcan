//! Bounded, cancellable capture for local, WSL and system-SSH helpers.

use crate::{ProcessOutput, ProcessRequest, ProcessRunner, StudioError};
use std::io::Read;
use std::process::{Command, Stdio};
use std::sync::{
    Arc,
    atomic::{AtomicBool, Ordering},
    mpsc,
};
use std::time::{Duration, Instant};

pub const COMMAND_TIMEOUT: Duration = Duration::from_secs(900);
pub const CHECK_TIMEOUT: Duration = Duration::from_secs(90);
/// Small command responses only; never use this path for an image archive.
pub const RESPONSE_LIMIT: usize = 16 * 1024 * 1024;

pub struct ControlledRunner {
    pub timeout: Duration,
    pub cancelled: Arc<AtomicBool>,
}

impl ProcessRunner for ControlledRunner {
    fn run(&self, request: &ProcessRequest) -> Result<ProcessOutput, StudioError> {
        let output = capture_command(
            crate::system_command(&request.program).args(&request.arguments),
            self.timeout,
            &self.cancelled,
        )?;
        Ok(ProcessOutput {
            success: output.status.success(),
            stdout: String::from_utf8_lossy(&output.stdout).into_owned(),
            stderr: String::from_utf8_lossy(&output.stderr).into_owned(),
        })
    }
}

/// Capture both pipes concurrently: neither large output nor inherited pipes
/// may make the caller wait beyond the deadline. Cancellation does not undo
/// remote changes; callers must refresh before retrying mutations.
pub fn capture_command(
    command: &mut Command,
    timeout: Duration,
    cancelled: &AtomicBool,
) -> Result<std::process::Output, StudioError> {
    let label = command.get_program().to_string_lossy().into_owned();
    if cancelled.load(Ordering::Relaxed) {
        return Err(StudioError::Cancelled);
    }
    command.stdout(Stdio::piped()).stderr(Stdio::piped());
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        command.process_group(0);
    }
    let mut child = command.spawn().map_err(|error| StudioError::Launch {
        command: label.clone(),
        reason: error.to_string(),
    })?;
    let (send, receive) = mpsc::channel();
    fn read_pipe(
        mut pipe: impl Read + Send + 'static,
        stdout: bool,
        send: mpsc::Sender<(bool, std::io::Result<Vec<u8>>)>,
    ) {
        std::thread::spawn(move || {
            let mut bytes = Vec::new();
            let result = pipe
                .by_ref()
                .take((RESPONSE_LIMIT + 1) as u64)
                .read_to_end(&mut bytes)
                .and_then(|_| {
                    if bytes.len() > RESPONSE_LIMIT {
                        Err(std::io::Error::other(
                            "Command response exceeded the 16 MiB limit; refresh before retrying",
                        ))
                    } else {
                        Ok(bytes)
                    }
                });
            let _ = send.send((stdout, result));
        });
    }
    read_pipe(child.stdout.take().unwrap(), true, send.clone());
    read_pipe(child.stderr.take().unwrap(), false, send);
    let deadline = Instant::now() + timeout;
    let mut stdout = None;
    let mut stderr = None;
    let mut status = None;
    let result = 'capture: loop {
        while let Ok((is_stdout, bytes)) = receive.try_recv() {
            match bytes {
                Ok(bytes) => {
                    if is_stdout {
                        stdout = Some(bytes);
                    } else {
                        stderr = Some(bytes);
                    }
                }
                Err(error) => {
                    break 'capture Err(StudioError::Launch {
                        command: label.clone(),
                        reason: error.to_string(),
                    });
                }
            }
        }
        if status.is_none() {
            match child.try_wait() {
                Ok(value) => status = value,
                Err(error) => {
                    break Err(StudioError::Launch {
                        command: label.clone(),
                        reason: error.to_string(),
                    });
                }
            }
        }
        if status.is_some() && stdout.is_some() && stderr.is_some() {
            break Ok(std::process::Output {
                status: status.unwrap(),
                stdout: stdout.take().unwrap(),
                stderr: stderr.take().unwrap(),
            });
        }
        if cancelled.load(Ordering::Relaxed) {
            break Err(StudioError::Cancelled);
        }
        if Instant::now() >= deadline {
            break Err(StudioError::TimedOut {
                command: label,
                seconds: timeout.as_secs(),
            });
        }
        std::thread::sleep(Duration::from_millis(10));
    };
    if result.is_err() {
        terminate_process_tree(child.id());
        let _ = child.kill();
        let _ = child.wait();
    }
    result
}

/// Only call for an owned helper launched in its own process group.
pub fn terminate_process_tree(pid: u32) {
    #[cfg(unix)]
    // The child has its own process group. Never signal Studio's group.
    unsafe {
        libc::kill(-(pid as i32), libc::SIGKILL);
    }
    #[cfg(windows)]
    {
        let _ = crate::system_command("taskkill")
            .args(["/PID", &pid.to_string(), "/T", "/F"])
            .status();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[cfg(unix)]
    #[test]
    fn oversized_response_stops_the_helper_without_waiting_for_exit() {
        let started = Instant::now();
        let result = capture_command(
            Command::new("sh").args([
                "-c",
                &format!("head -c {} /dev/zero; sleep 30", RESPONSE_LIMIT + 1),
            ]),
            CHECK_TIMEOUT,
            &AtomicBool::new(false),
        );
        assert!(result.unwrap_err().to_string().contains("16 MiB"));
        assert!(started.elapsed() < Duration::from_secs(3));
    }

    #[test]
    fn cancellation_before_launch_never_starts_a_process() {
        assert_eq!(
            capture_command(
                &mut Command::new("nonexistent-orcan-helper"),
                CHECK_TIMEOUT,
                &AtomicBool::new(true)
            )
            .unwrap_err(),
            StudioError::Cancelled
        );
    }

    #[cfg(unix)]
    #[test]
    fn inherited_pipes_and_sleeping_children_respect_the_deadline() {
        let started = Instant::now();
        let result = capture_command(
            Command::new("sh").args(["-c", "sleep 30 & printf ready"]),
            Duration::from_millis(100),
            &AtomicBool::new(false),
        );
        assert!(matches!(result, Err(StudioError::TimedOut { .. })));
        assert!(started.elapsed() < Duration::from_secs(2));
    }

    #[cfg(unix)]
    #[test]
    fn cancellation_stops_a_running_helper() {
        let cancelled = Arc::new(AtomicBool::new(false));
        let signal = cancelled.clone();
        std::thread::spawn(move || {
            std::thread::sleep(Duration::from_millis(50));
            signal.store(true, Ordering::Relaxed);
        });
        let started = Instant::now();
        let result = capture_command(
            Command::new("sh").args(["-c", "sleep 30"]),
            CHECK_TIMEOUT,
            &cancelled,
        );
        assert_eq!(result.unwrap_err(), StudioError::Cancelled);
        assert!(started.elapsed() < Duration::from_secs(2));
    }

    #[cfg(unix)]
    #[test]
    fn drains_both_large_pipes_without_deadlocking() {
        let result = capture_command(
            Command::new("sh").args([
                "-c",
                "head -c 100000 /dev/zero; head -c 100000 /dev/zero >&2",
            ]),
            CHECK_TIMEOUT,
            &AtomicBool::new(false),
        )
        .unwrap();
        assert!(result.status.success());
        assert_eq!(result.stdout.len(), 100000);
        assert_eq!(result.stderr.len(), 100000);
    }
}
