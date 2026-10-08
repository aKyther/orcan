//! Profile-to-profile provisioning. Binary payloads are spooled to a private
//! temporary file on Studio, not buffered in RAM or copied between servers.
use super::transfer_progress::{ProgressReader, TransferProgress};
use super::*;
use tokio::io::AsyncWriteExt;

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

fn validate(input: &TransferInput) -> Result<(), String> {
    if input.cli && input.image.is_some() {
        return Err("CLI and image transfers are separate. Use the image transfer panel.".into());
    }
    if Target::from(input.source.target.clone()) == Target::from(input.destination.target.clone())
        && input.source.username == input.destination.username
    {
        return Err("Source and destination refer to the same endpoint".into());
    }
    if input.source.profile_id.is_some() && input.source.profile_id == input.destination.profile_id
    {
        return Err("Choose different source and destination profiles".into());
    }
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
    state: &tauri::State<'_, ProfileState>,
    progress: &mut TransferProgress,
) -> Result<String, String> {
    let total = if upload {
        Some(file.as_file().metadata().map_err(|e| e.to_string())?.len())
    } else {
        None
    };
    progress.stage(if upload { "transferring" } else { "exporting" }, total);
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
            let reader = tokio::fs::File::open(file.path())
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
            let reader = tokio::fs::File::open(file.path()).await?;
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
) -> Result<String, String> {
    let mut progress = TransferProgress::new(app, operation_id);
    progress.stage("checking", None);
    let result = transfer_profiles_inner(input, state, cache, &mut progress).await;
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
    progress: &mut TransferProgress,
) -> Result<String, String> {
    let check = check_transfer(input.clone(), state.clone()).await?;
    if !input.cli
        && check
            .source_image
            .as_ref()
            .is_some_and(|image| Some(&image.id) == check.destination_image_id.as_ref())
    {
        return Ok("Destination already has the same image. No transfer needed.".into());
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
        &state,
        progress,
    )
    .await
    .map_err(|e| format!("Source export failed: {e}"))?;
    move_file(
        &input.destination,
        &destination,
        &payload.file,
        true,
        &state,
        progress,
    )
    .await
    .map_err(|e| format!("Destination installation failed: {e}"))?;
    progress.stage("verifying", None);
    if input.cli {
        execute(&input.destination, "orcan version", &state).await?;
    }
    if let Some(image) = &check.source_image {
        let installed =
            profile_image_inventory(input.destination.clone(), image.image.clone(), state).await?;
        if installed.id != image.id {
            return Err("Destination image differs from source".into());
        }
    }
    Ok("Installation verified on destination. Existing configuration and projects were not transferred.".into())
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
    execute(&enclave, &format!(
        "set -Eeuo pipefail; image={}; if [[ -n \"$(docker container ls -aq --filter \"ancestor=$image\")\" ]]; then echo 'Remove the container first; this image is still used' >&2; exit 1; fi; docker image rm -- \"$image\"",
        shell_quote(&current.id)
    ), &state).await
}

#[cfg(test)]
mod tests {
    use super::*;

    fn endpoint(target: TargetInput, id: &str) -> EnclaveInput {
        EnclaveInput {
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
        assert!(validate(&input).is_err(), "CLI installation must not bundle an image");
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
