//! Profile-to-profile provisioning. Binary payloads are spooled to a private
//! temporary file on Studio, not buffered in RAM or copied between servers.
use super::transfer_progress::{ProgressReader, TransferProgress};
use super::*;
use sha2::{Digest, Sha256};
use tokio::io::{AsyncReadExt, AsyncSeekExt, AsyncWriteExt};

pub(super) struct PendingTransfers(Mutex<std::collections::HashMap<String, PendingTransfer>>);

impl Default for PendingTransfers {
    fn default() -> Self {
        Self(Mutex::new(std::collections::HashMap::new()))
    }
}

struct PendingTransfer {
    input: TransferInput,
    payload: transfer_cache::TransferPayload,
    expected: Option<ImageContent>,
    install: String,
    digest: String,
}

fn receiver(mode: &str, token: &str, args: &[String]) -> Result<String, String> {
    if token.len() != 36 || !token.bytes().all(|c| c.is_ascii_hexdigit() || c == b'-') {
        return Err("Invalid transfer token".into());
    }
    Ok(format!(
        "python3 -c {} {} {} {}",
        shell_quote(include_str!("transfer_receiver.py")),
        shell_quote(mode),
        shell_quote(token),
        args.iter()
            .map(|arg| shell_quote(arg))
            .collect::<Vec<_>>()
            .join(" ")
    ))
}

async fn payload_digest(path: &std::path::Path, limit: u64) -> Result<String, String> {
    let mut reader = tokio::fs::File::open(path)
        .await
        .map_err(|e| e.to_string())?
        .take(limit);
    let mut digest = Sha256::new();
    let mut buffer = vec![0; 1024 * 1024];
    loop {
        let count = reader.read(&mut buffer).await.map_err(|e| e.to_string())?;
        if count == 0 {
            break;
        }
        digest.update(&buffer[..count]);
    }
    Ok(format!("{:x}", digest.finalize()))
}

#[derive(Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub(super) struct TransferInput {
    source: EnclaveInput,
    destination: EnclaveInput,
    cli: bool,
    image: Option<String>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(super) struct TransferCheck {
    installed_version: Option<String>,
    destination_image_id: Option<String>,
    source_image: Option<ImageInventory>,
    destination_user: String,
}

/// Engine-specific IDs can identify an OCI manifest or an image config.
/// Compare runtime content, not store metadata, tags, compressed size or IDs.
#[derive(Debug, Deserialize, PartialEq)]
#[serde(rename_all = "PascalCase")]
struct ImageContent {
    config: serde_json::Value,
    #[serde(rename = "RootFS")]
    root_fs: ImageRootFs,
    architecture: String,
    os: String,
    #[serde(default)]
    variant: String,
}

#[derive(Debug, Deserialize, PartialEq)]
#[serde(rename_all = "PascalCase")]
struct ImageRootFs {
    #[serde(rename = "Type")]
    kind: String,
    layers: Vec<String>,
}

fn parse_image_content(output: &str) -> Result<ImageContent, String> {
    let images: Vec<ImageContent> = serde_json::from_str(output)
        .map_err(|e| format!("Docker returned invalid image content: {e}"))?;
    if images.len() != 1 {
        return Err("Docker must report exactly one image for verification".into());
    }
    let image = images.into_iter().next().unwrap();
    if !image.config.is_object()
        || image.architecture.is_empty()
        || image.os.is_empty()
        || image.root_fs.kind != "layers"
    {
        return Err("Docker returned incomplete image content for verification".into());
    }
    Ok(image)
}

async fn image_content(
    enclave: &EnclaveInput,
    image: &str,
    state: &tauri::State<'_, ProfileState>,
) -> Result<ImageContent, String> {
    let output = execute(
        enclave,
        &format!("docker image inspect {}", shell_quote(image)),
        state,
    )
    .await?;
    parse_image_content(&output)
}

fn process(enclave: &EnclaveInput, script: &str) -> Result<TokioCommand, String> {
    let script = format!("export PATH=\"$HOME/.local/bin:$PATH\"; {script}");
    match &enclave.target {
        TargetInput::Local => {
            if cfg!(windows) {
                return Err(
                    "Local Windows does not run Linux Orcan. Choose a WSL2 profile.".into(),
                );
            }
            let mut command = background_tokio_command("bash");
            command.args(["-lc", &script]);
            Ok(command)
        }
        TargetInput::Wsl2 { distribution } => {
            validate_wsl_distribution(distribution)?;
            let mut command = background_tokio_command("wsl.exe");
            command.args(["--distribution", distribution]);
            if let Some(user) = &enclave.username {
                command.args(["--user", user]);
            }
            command.args(["--exec", "bash", "-lc", &script]);
            Ok(command)
        }
        TargetInput::Ssh { destination } => {
            Target::from(enclave.target.clone())
                .probe_request()
                .map_err(|e| e.to_string())?;
            let mut command = background_tokio_command("ssh");
            command.args(["-o", "BatchMode=yes"]);
            if let Some(user) = &enclave.username {
                command.args(["-l", user]);
            }
            command.args([
                "--",
                destination,
                &format!("bash -lc {}", shell_quote(&script)),
            ]);
            Ok(command)
        }
    }
}

fn profile_process(
    enclave: &EnclaveInput,
    script: &str,
    state: &tauri::State<'_, ProfileState>,
) -> Result<TokioCommand, String> {
    let mut endpoint = enclave.clone();
    if matches!(endpoint.target, TargetInput::Ssh { .. }) {
        let resolved = state
            .0
            .lock()
            .map_err(|_| "profile store is unavailable")?
            .resolve_ssh(
                endpoint.profile_id.as_deref(),
                endpoint.credential_id.as_deref(),
                endpoint.username.as_deref(),
            )
            .map_err(|e| e.to_string())?;
        if let Some((_, resolved)) = resolved {
            endpoint.username = resolved.ssh.username;
        }
    }
    process(&endpoint, script)
}

pub(super) async fn execute(
    enclave: &EnclaveInput,
    script: &str,
    state: &tauri::State<'_, ProfileState>,
) -> Result<String, String> {
    if let (TargetInput::Ssh { destination }, Some(resolved)) = (
        &enclave.target,
        native_ssh(enclave, &Target::from(enclave.target.clone()), state)?,
    ) {
        return native_ssh_exec(
            destination,
            resolved,
            &format!(
                "bash -lc {}",
                shell_quote(&format!("export PATH=\"$HOME/.local/bin:$PATH\"; {script}"))
            ),
        )
        .await;
    }
    let output = profile_process(enclave, script, state)?
        .output()
        .await
        .map_err(|e| e.to_string())?;
    if !output.status.success() {
        return Err(String::from_utf8_lossy(&output.stderr).trim().to_owned());
    }
    Ok(String::from_utf8_lossy(&output.stdout).trim().to_owned())
}

/// Bounded secret payload on stdin, never in process arguments or a temp file.
pub(super) async fn execute_with_input(
    enclave: &EnclaveInput,
    script: &str,
    payload: &[u8],
    state: &tauri::State<'_, ProfileState>,
) -> Result<String, String> {
    if let (TargetInput::Ssh { destination }, Some(resolved)) = (
        &enclave.target,
        native_ssh(enclave, &Target::from(enclave.target.clone()), state)?,
    ) {
        let session = native_ssh_connect(destination, resolved).await?;
        let mut channel = session
            .channel_open_session()
            .await
            .map_err(|e| e.to_string())?;
        let command = format!("bash -lc {}", shell_quote(script));
        channel
            .exec(true, command.as_str())
            .await
            .map_err(|e| e.to_string())?;
        channel.data(payload).await.map_err(|e| e.to_string())?;
        channel.eof().await.map_err(|e| e.to_string())?;
        let mut output = Vec::new();
        let mut status = None;
        while let Some(message) = channel.wait().await {
            match message {
                ChannelMsg::Data { data } => output.extend_from_slice(&data),
                ChannelMsg::ExitStatus { exit_status } => status = Some(exit_status),
                _ => {}
            }
            if output.len() > 16384 {
                return Err("Unexpected SSH preparation response".into());
            }
        }
        if status != Some(0) {
            return Err("SSH installation refused. Check destination filename collisions, permissions and key format; existing files were not overwritten.".into());
        }
        return String::from_utf8(output).map_err(|_| "Invalid SSH preparation response".into());
    }
    let mut command = profile_process(enclave, script, state)?;
    command
        .kill_on_drop(true)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    let mut child = command.spawn().map_err(|e| e.to_string())?;
    let mut stdin = child
        .stdin
        .take()
        .ok_or("Destination has no input stream")?;
    let write = async {
        stdin.write_all(payload).await?;
        stdin.shutdown().await
    };
    let (sent, output) = tokio::join!(write, child.wait_with_output());
    sent.map_err(|_| "SSH transfer interrupted; inspect destination before retrying")?;
    let output = output.map_err(|_| "SSH preparation process stopped")?;
    if !output.status.success() {
        return Err("SSH installation refused. Check destination filename collisions, permissions and key format; existing files were not overwritten.".into());
    }
    String::from_utf8(output.stdout).map_err(|_| "Invalid SSH preparation response".into())
}

pub(super) fn distinct_endpoints(
    source: &EnclaveInput,
    destination: &EnclaveInput,
) -> Result<(), String> {
    if Target::from(source.target.clone()) == Target::from(destination.target.clone())
        && source.username == destination.username
    {
        return Err("Source and destination refer to the same endpoint".into());
    }
    if source.profile_id.is_some() && source.profile_id == destination.profile_id {
        return Err("Choose different source and destination profiles".into());
    }
    Ok(())
}

fn validate(input: &TransferInput) -> Result<(), String> {
    if input.cli && input.image.is_some() {
        return Err("CLI and image transfers are separate. Use the image transfer panel.".into());
    }
    distinct_endpoints(&input.source, &input.destination)?;
    if !input.cli && input.image.is_none() {
        return Err("Choose CLI or a Docker image to transfer".into());
    }
    if input
        .image
        .as_ref()
        .is_some_and(|image| !valid_image_reference(image))
    {
        return Err("invalid Docker image reference".into());
    }
    Ok(())
}

#[tauri::command]
pub(super) async fn profile_image_inventory(
    enclave: EnclaveInput,
    image: String,
    state: tauri::State<'_, ProfileState>,
) -> Result<ImageInventory, String> {
    if !valid_image_reference(&image) {
        return Err("invalid Docker image reference".into());
    }
    let output = execute(
        &enclave,
        &format!(
            "docker image inspect --format '{{{{.Id}}}}\t{{{{.Size}}}}\t{{{{.Architecture}}}}' {}",
            shell_quote(&image)
        ),
        &state,
    )
    .await?;
    let fields: Vec<_> = output.trim().split('\t').collect();
    if fields.len() != 3 {
        return Err("Docker returned incomplete image information".into());
    }
    Ok(ImageInventory {
        image,
        id: fields[0].into(),
        size: fields[1].into(),
        architecture: fields[2].into(),
    })
}

#[tauri::command]
pub(super) async fn check_transfer(
    input: TransferInput,
    state: tauri::State<'_, ProfileState>,
) -> Result<TransferCheck, String> {
    validate(&input)?;
    if input.cli {
        execute(&input.source, &offline_source_check(None)?, &state).await?;
    }
    let source_image = match &input.image {
        Some(image) => {
            Some(profile_image_inventory(input.source.clone(), image.clone(), state.clone()).await?)
        }
        None => None,
    };
    let destination = execute(
        &input.destination,
        &offline_destination_check(input.image.is_some()),
        &state,
    )
    .await?;
    let (user, arch) = destination
        .trim()
        .split_once('\t')
        .ok_or("Destination did not report user and architecture")?;
    let arch = match arch {
        "x86_64" => "amd64",
        "aarch64" => "arm64",
        other => other,
    };
    if source_image
        .as_ref()
        .is_some_and(|image| image.architecture != arch)
    {
        return Err(format!(
            "Image architecture does not match destination {arch}"
        ));
    }
    let version = execute(
        &input.destination,
        "if command -v orcan >/dev/null; then orcan version; else printf not-installed; fi",
        &state,
    )
    .await?;
    let destination_image_id = match &input.image {
        Some(image) => {
            let output = execute(&input.destination, &format!(
                "docker image inspect --format '{{{{.Id}}}}' {} 2>/dev/null || printf not-installed", shell_quote(image)
            ), &state).await?;
            (output.trim() != "not-installed").then(|| output.trim().to_owned())
        }
        None => None,
    };
    Ok(TransferCheck {
        installed_version: (version.trim() != "not-installed").then(|| version.trim().to_owned()),
        destination_image_id,
        source_image,
        destination_user: user.into(),
    })
}

// Native SSH handles binary files directly, including password credentials.
// Process transports use file-backed stdin/stdout and drain stderr via Tokio.
async fn move_file(
    enclave: &EnclaveInput,
    script: &str,
    file: &tempfile::NamedTempFile,
    upload: bool,
    offset: u64,
    state: &tauri::State<'_, ProfileState>,
    progress: &mut TransferProgress,
) -> Result<String, String> {
    let total = if upload {
        Some(file.as_file().metadata().map_err(|e| e.to_string())?.len())
    } else {
        None
    };
    progress.stage(if upload { "transferring" } else { "exporting" }, total);
    if upload {
        progress.resume_at(offset);
    }
    if let (TargetInput::Ssh { destination }, Some(resolved)) = (
        &enclave.target,
        native_ssh(enclave, &Target::from(enclave.target.clone()), state)?,
    ) {
        let session = native_ssh_connect(destination, resolved).await?;
        let mut channel = session
            .channel_open_session()
            .await
            .map_err(|e| e.to_string())?;
        let command = format!(
            "bash -lc {}",
            shell_quote(&format!("export PATH=\"$HOME/.local/bin:$PATH\"; {script}"))
        );
        channel
            .exec(true, command.as_str())
            .await
            .map_err(|e| e.to_string())?;
        if upload {
            let mut reader = tokio::fs::File::open(file.path())
                .await
                .map_err(|e| e.to_string())?;
            reader
                .seek(std::io::SeekFrom::Start(offset))
                .await
                .map_err(|e| e.to_string())?;
            channel
                .data(ProgressReader::new(reader, |bytes| progress.advance(bytes)))
                .await
                .map_err(|e| e.to_string())?;
            progress.flush();
        }
        channel.eof().await.map_err(|e| e.to_string())?;
        if upload {
            progress.stage("installing", None);
        }
        let mut writer = if upload {
            None
        } else {
            Some(
                tokio::fs::File::create(file.path())
                    .await
                    .map_err(|e| e.to_string())?,
            )
        };
        let mut stdout = Vec::new();
        let mut stderr = Vec::new();
        let mut status = None;
        while let Some(message) = channel.wait().await {
            match message {
                ChannelMsg::Data { data } => {
                    if let Some(writer) = &mut writer {
                        writer.write_all(&data).await.map_err(|e| e.to_string())?;
                        progress.advance(data.len());
                    } else {
                        stdout.extend_from_slice(&data);
                    }
                }
                ChannelMsg::ExtendedData { data, .. } => stderr.extend_from_slice(&data),
                ChannelMsg::ExitStatus { exit_status } => status = Some(exit_status),
                _ => {}
            }
        }
        if let Some(writer) = &mut writer {
            writer.flush().await.map_err(|e| e.to_string())?;
            progress.flush();
        }
        if status != Some(0) {
            return Err(String::from_utf8_lossy(&stderr).trim().to_owned());
        }
        return Ok(String::from_utf8_lossy(&stdout).trim().to_owned());
    }
    let mut command = profile_process(enclave, script, state)?;
    command.kill_on_drop(true);
    command.stdin(if upload {
        Stdio::piped()
    } else {
        Stdio::null()
    });
    command.stdout(Stdio::piped());
    command.stderr(Stdio::piped());
    let mut child = command.spawn().map_err(|e| e.to_string())?;
    let stdin = child.stdin.take();
    let stdout = if upload { None } else { child.stdout.take() };
    let copy = async {
        if upload {
            let mut reader = tokio::fs::File::open(file.path()).await?;
            reader.seek(std::io::SeekFrom::Start(offset)).await?;
            let mut reader = ProgressReader::new(reader, |bytes| progress.advance(bytes));
            let mut stdin =
                stdin.ok_or_else(|| io::Error::other("Destination has no input stream"))?;
            tokio::io::copy(&mut reader, &mut stdin).await?;
            stdin.shutdown().await?;
            progress.flush();
            progress.stage("installing", None);
        } else {
            let reader = stdout.ok_or_else(|| io::Error::other("Source has no output stream"))?;
            let mut reader = ProgressReader::new(reader, |bytes| progress.advance(bytes));
            let mut writer = tokio::fs::File::create(file.path()).await?;
            tokio::io::copy(&mut reader, &mut writer).await?;
            writer.flush().await?;
            progress.flush();
        }
        Ok::<_, io::Error>(())
    };
    let (copied, output) = tokio::join!(copy, child.wait_with_output());
    let output = output.map_err(|e| e.to_string())?;
    if !output.status.success() {
        return Err(String::from_utf8_lossy(&output.stderr).trim().to_owned());
    }
    copied.map_err(|e| e.to_string())?;
    Ok(String::from_utf8_lossy(&output.stdout).trim().to_owned())
}

#[tauri::command]
pub(super) async fn transfer_profiles(
    input: TransferInput,
    operation_id: String,
    app: tauri::AppHandle,
    state: tauri::State<'_, ProfileState>,
    cache: tauri::State<'_, transfer_cache::TransferCache>,
    pending: tauri::State<'_, PendingTransfers>,
) -> Result<String, String> {
    receiver("inspect", &operation_id, &[])?;
    let mut progress = TransferProgress::new(app, operation_id.clone());
    progress.stage("checking", None);
    let result =
        transfer_profiles_inner(input, state, cache, &pending, &operation_id, &mut progress).await;
    progress.stage(
        if result.is_ok() {
            "completed"
        } else {
            "failed"
        },
        None,
    );
    result
}

async fn transfer_profiles_inner(
    input: TransferInput,
    state: tauri::State<'_, ProfileState>,
    cache: tauri::State<'_, transfer_cache::TransferCache>,
    pending: &PendingTransfers,
    token: &str,
    progress: &mut TransferProgress,
) -> Result<String, String> {
    let check = check_transfer(input.clone(), state.clone()).await?;
    let source_content = match &input.image {
        Some(image) => Some(image_content(&input.source, image, &state).await?),
        None => None,
    };
    if check.destination_image_id.is_some() {
        if let (Some(image), Some(expected)) = (&input.image, &source_content) {
            if image_content(&input.destination, image, &state).await? == *expected {
                return Ok(
                    "Destination already has the same image content. No transfer needed.".into(),
                );
            }
        }
    }
    let (source, destination): (String, String) = if input.cli {
        ("set -Eeuo pipefail; kit=$(mktemp -d); trap 'rm -rf \"$kit\"' EXIT; orcan bundle create --output \"$kit/bundle\" >&2; tar -C \"$kit/bundle\" -czf - .".into(),
        "set -Eeuo pipefail; kit=$(mktemp -d); trap 'rm -rf \"$kit\"' EXIT; tar -xzf - -C \"$kit\"; \"$kit/install-orcan-cli.sh\"; orcan version".into())
    } else {
        (
            format!("docker save {}", shell_quote(input.image.as_ref().unwrap())),
            "docker load".into(),
        )
    };
    let payload = cache
        .create()
        .map_err(|e| format!("Could not create private transfer file: {e}"))?;
    move_file(
        &input.source,
        &source,
        &payload.file,
        false,
        0,
        &state,
        progress,
    )
    .await
    .map_err(|e| format!("Source export failed: {e}"))?;
    if let (Some(image), Some(expected)) = (&input.image, &source_content) {
        if image_content(&input.source, image, &state).await? != *expected {
            return Err("Source image changed during export. Check the source and retry.".into());
        }
    }
    progress.stage("hashing", None);
    let digest = payload_digest(payload.file.path(), u64::MAX).await?;
    let transfer = PendingTransfer {
        input,
        payload,
        expected: source_content,
        install: destination,
        digest,
    };
    complete_or_retain(token, transfer, &state, pending, progress).await
}

async fn complete_or_retain(
    token: &str,
    transfer: PendingTransfer,
    state: &tauri::State<'_, ProfileState>,
    pending: &PendingTransfers,
    progress: &mut TransferProgress,
) -> Result<String, String> {
    let result = finish_transfer(token, &transfer, state, progress).await;
    if result.is_err() {
        pending
            .0
            .lock()
            .map_err(|_| "Pending transfer store is unavailable")?
            .insert(token.into(), transfer);
    }
    result
}

async fn finish_transfer(
    token: &str,
    transfer: &PendingTransfer,
    state: &tauri::State<'_, ProfileState>,
    progress: &mut TransferProgress,
) -> Result<String, String> {
    let destination = &transfer.input.destination;
    let total = transfer
        .payload
        .file
        .as_file()
        .metadata()
        .map_err(|e| e.to_string())?
        .len();
    progress.stage("hashing", None);
    let inspection = execute(destination, &receiver("inspect", token, &[])?, state).await?;
    let (offset, prefix) = inspection
        .split_once('\t')
        .ok_or("Destination did not report its transfer offset")?;
    let offset: u64 = offset.parse().map_err(|_| "Invalid destination offset")?;
    if offset > total || payload_digest(transfer.payload.file.path(), offset).await? != prefix {
        return Err("Destination partial file does not match this transfer. Discard it and start a new transfer.".into());
    }
    let args = vec![
        offset.to_string(),
        total.to_string(),
        transfer.digest.clone(),
    ];
    if offset < total {
        move_file(
            destination,
            &receiver("append", token, &args)?,
            &transfer.payload.file,
            true,
            offset,
            state,
            progress,
        )
        .await
        .map_err(|e| {
            format!("Upload interrupted. Resume this transfer without exporting again: {e}")
        })?;
    }
    progress.stage("installing", None);
    execute(
        destination,
        &receiver(
            "install",
            token,
            &[
                total.to_string(),
                transfer.digest.clone(),
                transfer.install.clone(),
            ],
        )?,
        state,
    )
    .await
    .map_err(|e| {
        format!(
            "Destination installation did not finish. Retry will reuse the verified payload: {e}"
        )
    })?;
    progress.stage("verifying", None);
    if transfer.input.cli {
        execute(destination, "orcan version", state).await?;
    }
    if let Some(image) = &transfer.input.image {
        let installed =
            profile_image_inventory(destination.clone(), image.clone(), state.clone()).await?;
        let installed_content = image_content(destination, image, state).await?;
        if transfer.expected.as_ref() != Some(&installed_content) {
            return Err(format!(
                "Destination image content differs from exported source (configuration, layers or platform). Destination ID: {}. Check the selected image and Docker endpoints.",
                installed.id
            ));
        }
    }
    execute(destination, &receiver("remove", token, &[])?, state)
        .await
        .map_err(|e| {
            format!(
                "Installation verified, but transfer cleanup failed. Retry to finish cleanup: {e}"
            )
        })?;
    Ok("Installation verified on destination. Existing configuration and projects were not transferred.".into())
}

#[tauri::command]
pub(super) fn has_pending_transfer(
    token: String,
    pending: tauri::State<'_, PendingTransfers>,
) -> Result<bool, String> {
    Ok(pending
        .0
        .lock()
        .map_err(|_| "Pending transfer store is unavailable")?
        .contains_key(&token))
}

#[tauri::command]
pub(super) async fn resume_transfer(
    token: String,
    operation_id: String,
    app: tauri::AppHandle,
    state: tauri::State<'_, ProfileState>,
    pending: tauri::State<'_, PendingTransfers>,
) -> Result<String, String> {
    let transfer = pending.0.lock().map_err(|_| "Pending transfer store is unavailable")?
        .remove(&token).ok_or("This transfer is not available or is already running. Resume requires the same Studio session.")?;
    let mut progress = TransferProgress::new(app, operation_id);
    let result = complete_or_retain(&token, transfer, &state, &pending, &mut progress).await;
    progress.stage(
        if result.is_ok() {
            "completed"
        } else {
            "failed"
        },
        None,
    );
    result
}

#[tauri::command]
pub(super) async fn discard_transfer(
    token: String,
    state: tauri::State<'_, ProfileState>,
    pending: tauri::State<'_, PendingTransfers>,
) -> Result<(), String> {
    let transfer = pending
        .0
        .lock()
        .map_err(|_| "Pending transfer store is unavailable")?
        .remove(&token)
        .ok_or("Transfer is not available or is already running")?;
    if let Err(error) = execute(
        &transfer.input.destination,
        &receiver("remove", &token, &[])?,
        &state,
    )
    .await
    {
        pending
            .0
            .lock()
            .map_err(|_| "Pending transfer store is unavailable")?
            .insert(token, transfer);
        return Err(format!(
            "Could not remove the destination partial file. Reconnect and discard again: {error}"
        ));
    }
    Ok(())
}

#[tauri::command]
pub(super) async fn remove_destination_image(
    enclave: EnclaveInput,
    image: String,
    expected_id: String,
    confirmed: bool,
    state: tauri::State<'_, ProfileState>,
) -> Result<String, String> {
    if !confirmed {
        return Err("Removal needs confirmation".into());
    }
    let current = profile_image_inventory(enclave.clone(), image.clone(), state.clone()).await?;
    if current.id != expected_id {
        return Err("Image changed. Check the destination again.".into());
    }
    execute(
        &enclave,
        &image_removal_script(&current.image, &expected_id),
        &state,
    )
    .await
}

fn image_removal_script(image: &str, expected_id: &str) -> String {
    format!(
        "set -Eeuo pipefail; image={}; expected={}; current=$(docker image inspect --format '{{{{.Id}}}}' \"$image\"); [[ \"$current\" == \"$expected\" ]] || {{ echo 'Image changed. Check the server again.' >&2; exit 1; }}; users=$(docker container ls -aq --filter \"ancestor=$current\"); if [[ -n \"$users\" ]]; then echo 'Remove the container first; this image is still used' >&2; exit 1; fi; docker image rm -- \"$image\"",
        shell_quote(image), shell_quote(expected_id)
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn image_removal_keeps_used_changed_or_unchecked_images_and_removes_only_selected_tag() {
        for (id, users, docker_error, success) in [
            ("sha256:checked", "", false, true),
            ("sha256:changed", "", false, false),
            ("sha256:checked", "container-id", false, false),
            ("sha256:checked", "", true, false),
        ] {
            let directory = tempfile::tempdir().unwrap();
            let removed = directory.path().join("removed");
            let mock = format!(
                "docker() {{ if [[ \"$1 $2\" == 'image inspect' ]]; then echo {}; elif [[ \"$1 $2\" == 'container ls' ]]; then {}; else printf '%s' \"$4\" > {}; fi; }}; ",
                shell_quote(id),
                if docker_error { "return 1".to_string() } else { format!("printf '%s' {}", shell_quote(users)) },
                shell_quote(&removed.to_string_lossy()),
            );
            let output = std::process::Command::new("bash")
                .args([
                    "-c",
                    &(mock + &image_removal_script("orcan:selected", "sha256:checked")),
                ])
                .output()
                .unwrap();
            assert_eq!(output.status.success(), success);
            assert_eq!(removed.exists(), success);
            if success {
                assert_eq!(std::fs::read_to_string(removed).unwrap(), "orcan:selected");
            }
        }
    }

    #[tokio::test]
    async fn resume_hash_matches_only_the_requested_prefix() {
        let file = tempfile::NamedTempFile::new().unwrap();
        std::fs::write(file.path(), b"abcdef").unwrap();
        assert_eq!(
            payload_digest(file.path(), 3).await.unwrap(),
            format!("{:x}", Sha256::digest(b"abc"))
        );
        assert_eq!(
            payload_digest(file.path(), u64::MAX).await.unwrap(),
            format!("{:x}", Sha256::digest(b"abcdef"))
        );
    }

    #[test]
    fn receiver_tokens_cannot_escape_private_directory() {
        assert!(receiver("inspect", "../../path", &[]).is_err());
        assert!(receiver("inspect", "12345678-1234-1234-1234-123456789abc", &[]).is_ok());
    }

    fn inspect_fixture() -> serde_json::Value {
        serde_json::json!([{
            "Id": "sha256:config", "Size": 100, "RepoTags": ["orcan:latest"],
            "Architecture": "amd64", "Os": "linux",
            "Config": {"Env": ["LANG=C.UTF-8"], "Cmd": ["orcan-supervisord"]},
            "RootFS": {"Type": "layers", "Layers": ["sha256:first", "sha256:second"]}
        }])
    }

    #[test]
    fn image_content_ignores_store_ids_sizes_tags_and_json_key_order() {
        let source = inspect_fixture();
        let mut destination = source.clone();
        destination[0]["Id"] = serde_json::json!("sha256:manifest");
        destination[0]["Size"] = serde_json::json!(200);
        destination[0]["RepoTags"] = serde_json::json!(["another:tag"]);
        destination[0]["Descriptor"] = serde_json::json!({"digest": "sha256:manifest"});
        assert_eq!(
            parse_image_content(&source.to_string()).unwrap(),
            parse_image_content(&destination.to_string()).unwrap()
        );
    }

    #[test]
    fn image_content_rejects_changed_config_layers_and_platform_even_with_same_id() {
        let source = inspect_fixture();
        let expected = parse_image_content(&source.to_string()).unwrap();
        for (field, value) in [
            ("Config", serde_json::json!({"Cmd": ["different-command"]})),
            (
                "RootFS",
                serde_json::json!({"Type": "layers", "Layers": ["sha256:second", "sha256:first"]}),
            ),
            ("Architecture", serde_json::json!("arm64")),
            ("Os", serde_json::json!("windows")),
            ("Variant", serde_json::json!("v8")),
        ] {
            let mut changed = source.clone();
            changed[0][field] = value;
            assert_ne!(
                expected,
                parse_image_content(&changed.to_string()).unwrap(),
                "{field}"
            );
        }
    }

    #[test]
    fn image_content_fails_closed_on_missing_or_invalid_information() {
        for invalid in ["not-json", "[]", "[{}]"] {
            assert!(parse_image_content(invalid).is_err());
        }
        let fixture = inspect_fixture();
        assert!(
            parse_image_content(&serde_json::json!([fixture[0], fixture[0]]).to_string()).is_err()
        );
        for field in ["Config", "RootFS", "Architecture", "Os"] {
            let mut incomplete = fixture.clone();
            incomplete[0].as_object_mut().unwrap().remove(field);
            assert!(
                parse_image_content(&incomplete.to_string()).is_err(),
                "{field}"
            );
        }
    }

    fn endpoint(target: TargetInput, id: &str) -> EnclaveInput {
        EnclaveInput {
            instance: None,
            target,
            profile_id: Some(id.into()),
            credential_id: None,
            username: None,
        }
    }

    #[test]
    fn accepts_all_transport_pairs_except_same_endpoint() {
        let sources = [
            TargetInput::Local,
            TargetInput::Wsl2 {
                distribution: "Ubuntu".into(),
            },
            TargetInput::Ssh {
                destination: "source.example".into(),
            },
        ];
        let destinations = [
            TargetInput::Local,
            TargetInput::Wsl2 {
                distribution: "Debian".into(),
            },
            TargetInput::Ssh {
                destination: "destination.example".into(),
            },
        ];
        for source in &sources {
            for destination in &destinations {
                let input = TransferInput {
                    source: endpoint(source.clone(), "source"),
                    destination: endpoint(destination.clone(), "destination"),
                    cli: true,
                    image: None,
                };
                assert_eq!(
                    validate(&input).is_ok(),
                    !matches!(
                        (source, destination),
                        (TargetInput::Local, TargetInput::Local)
                    )
                );
            }
        }
    }

    #[test]
    fn shared_transfer_guard_ignores_profile_aliases_but_preserves_user_scope() {
        let source = endpoint(TargetInput::Local, "source");
        let mut destination = endpoint(TargetInput::Local, "alias");
        assert!(distinct_endpoints(&source, &destination).is_err());
        destination.username = Some("another-user".into());
        assert!(distinct_endpoints(&source, &destination).is_ok());
        destination.profile_id = source.profile_id.clone();
        assert!(distinct_endpoints(&source, &destination).is_err());
    }

    #[test]
    fn rejects_empty_transfer_and_unsafe_image() {
        let mut input = TransferInput {
            source: endpoint(TargetInput::Local, "a"),
            destination: endpoint(
                TargetInput::Ssh {
                    destination: "remote.example".into(),
                },
                "b",
            ),
            cli: false,
            image: None,
        };
        assert!(validate(&input).is_err());
        input.image = Some("orcan:latest; rm -rf /".into());
        assert!(validate(&input).is_err());
        input.image = Some("orcan:latest".into());
        assert!(validate(&input).is_ok());
        input.cli = true;
        assert!(
            validate(&input).is_err(),
            "CLI installation must not bundle an image"
        );
        input.cli = false;
        input.destination.profile_id = input.source.profile_id.clone();
        assert!(validate(&input).is_err());
    }

    #[test]
    fn wsl_uses_the_selected_user_and_one_script_argument() {
        let mut enclave = endpoint(
            TargetInput::Wsl2 {
                distribution: "Ubuntu".into(),
            },
            "a",
        );
        enclave.username = Some("alice".into());
        let command = process(&enclave, "printf '%s' hello").unwrap();
        let args: Vec<_> = command
            .as_std()
            .get_args()
            .map(|arg| arg.to_string_lossy().into_owned())
            .collect();
        assert_eq!(
            &args[..7],
            &[
                "--distribution",
                "Ubuntu",
                "--user",
                "alice",
                "--exec",
                "bash",
                "-lc"
            ]
        );
        assert!(args[7].ends_with("printf '%s' hello"));
    }
}
