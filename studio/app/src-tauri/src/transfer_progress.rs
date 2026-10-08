//! Operation-scoped, throttled progress; byte counts never include stdout logs.
use std::pin::Pin;
use std::task::{Context, Poll};
use std::time::{Duration, Instant};
use tauri::Emitter;
use tokio::io::{AsyncRead, ReadBuf};

#[derive(Clone, serde::Serialize)]
#[serde(rename_all = "camelCase")]
struct ProgressEvent<'a> {
    operation_id: &'a str,
    stage: &'a str,
    bytes: u64,
    total: Option<u64>,
}

pub(super) struct TransferProgress {
    app: tauri::AppHandle,
    id: String,
    stage: &'static str,
    bytes: u64,
    total: Option<u64>,
    last: Instant,
}

impl TransferProgress {
    pub fn new(app: tauri::AppHandle, id: String) -> Self {
        Self {
            app,
            id,
            stage: "checking",
            bytes: 0,
            total: None,
            last: Instant::now(),
        }
    }

    pub fn stage(&mut self, stage: &'static str, total: Option<u64>) {
        self.stage = stage;
        self.bytes = 0;
        self.total = total;
        self.flush();
    }

    pub fn advance(&mut self, bytes: usize) {
        self.bytes = self.bytes.saturating_add(bytes as u64);
        if self.last.elapsed() >= Duration::from_millis(250) {
            self.flush();
        }
    }

    pub fn flush(&mut self) {
        let _ = self.app.emit(
            "provision-progress",
            ProgressEvent {
                operation_id: &self.id,
                stage: self.stage,
                bytes: self.bytes,
                total: self.total,
            },
        );
        self.last = Instant::now();
    }
}

pub(super) struct ProgressReader<R, F> {
    reader: R,
    advance: F,
}

impl<R, F> ProgressReader<R, F> {
    pub fn new(reader: R, advance: F) -> Self {
        Self { reader, advance }
    }
}

impl<R: AsyncRead + Unpin, F: FnMut(usize) + Unpin> AsyncRead for ProgressReader<R, F> {
    fn poll_read(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        buf: &mut ReadBuf<'_>,
    ) -> Poll<std::io::Result<()>> {
        let this = self.get_mut();
        let before = buf.filled().len();
        let result = Pin::new(&mut this.reader).poll_read(cx, buf);
        if let Poll::Ready(Ok(())) = &result {
            let bytes = buf.filled().len() - before;
            if bytes > 0 {
                (this.advance)(bytes);
            }
        }
        result
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tokio::io::AsyncReadExt;

    #[tokio::test]
    async fn reader_preserves_binary_payload_and_counts_actual_bytes() {
        let input: Vec<_> = (0..100_000).map(|i| (i % 256) as u8).collect();
        let mut counted = 0;
        let mut reader = ProgressReader::new(input.as_slice(), |bytes| counted += bytes);
        let mut output = Vec::new();
        reader.read_to_end(&mut output).await.unwrap();
        assert_eq!(output, input);
        assert_eq!(counted, input.len());
    }

    #[tokio::test]
    async fn empty_reader_does_not_invent_progress() {
        let mut counted = 0;
        let mut reader = ProgressReader::new(&b""[..], |bytes| counted += bytes);
        assert_eq!(reader.read_to_end(&mut Vec::new()).await.unwrap(), 0);
        assert_eq!(counted, 0);
    }

    #[tokio::test]
    async fn read_failure_is_preserved_without_fake_bytes() {
        struct Broken;
        impl AsyncRead for Broken {
            fn poll_read(
                self: Pin<&mut Self>,
                _: &mut Context<'_>,
                _: &mut ReadBuf<'_>,
            ) -> Poll<std::io::Result<()>> {
                Poll::Ready(Err(std::io::Error::other("export failed")))
            }
        }
        let mut counted = 0;
        let mut reader = ProgressReader::new(Broken, |bytes| counted += bytes);
        let error = reader.read_to_end(&mut Vec::new()).await.unwrap_err();
        assert_eq!(error.to_string(), "export failed");
        assert_eq!(counted, 0);
    }
}
