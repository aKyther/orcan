//! CLI installation and compatibility WSL endpoints. Profile archive/image
//! transfers live in provisioning.rs; this module never owns their cache.
use super::{
    CliProvisionCheck, CliProvisionResult, EnclaveInput, ImageInventory, ONLINE_INSTALL_SCRIPT,
    ONLINE_PROVISION_CHECK_SCRIPT, OnlineProvisionCheck, ProfileState, TargetInput,
    WslCliProvision, WslImageInput, WslImageTransfer, background_command, cli_export,
    command_output, execution, native_ssh, native_ssh_exec, native_ssh_stream_wsl,
    offline_check_result, offline_destination_check, offline_source_check,
    parse_online_provision_check, provision_destination, shell_quote, valid_image_reference,
    validate_wsl_distribution, wsl_image_inventory,
};
use orcan_studio_core::Target;
use tokio::process::Command as TokioCommand;
#[tauri::command]
pub(super) async fn wsl_image_inventory_command(
    input: WslImageInput,
) -> Result<ImageInventory, String> {
    tauri::async_runtime::spawn_blocking(move || wsl_image_inventory(&input))
        .await
        .map_err(|error| format!("image inventory stopped: {error}"))?
}

/// Streams a Docker image from a local WSL distribution to an SSH target.
/// The image is never buffered or written by Studio.
#[tauri::command]
pub(super) async fn transfer_wsl_image(
    input: WslImageTransfer,
    state: tauri::State<'_, ProfileState>,
) -> Result<ImageInventory, String> {
    let destination = EnclaveInput {
        operation_id: None,
        instance: None,
        target: TargetInput::Ssh {
            destination: input.destination.clone(),
        },
        profile_id: input.destination_profile_id.clone(),
        credential_id: input.destination_credential_id.clone(),
        username: input.destination_username.clone(),
    };
    let target = Target::from(destination.target.clone());
    if let Some(resolved) = native_ssh(&destination, &target, &state)? {
        let inventory = wsl_image_inventory(&WslImageInput {
            distribution: input.distribution.clone(),
            image: input.image.clone(),
        })?;
        validate_wsl_distribution(&input.distribution)?;
        native_ssh_stream_wsl(
            &input.distribution,
            &input.destination,
            resolved,
            format!("docker save {}", shell_quote(&input.image)),
            "docker load".to_owned(),
            "Docker image transfer",
        )
        .await?;
        return Ok(inventory);
    }
    tauri::async_runtime::spawn_blocking(move || {
        let inventory = wsl_image_inventory(&WslImageInput {
            distribution: input.distribution.clone(),
            image: input.image.clone(),
        })?;
        Target::Ssh {
            destination: input.destination.clone(),
        }
        .probe_request()
        .map_err(|error| error.to_string())?;
        let mut source = background_command("wsl.exe");
        source.args([
            "--distribution",
            &input.distribution,
            "--exec",
            "docker",
            "save",
            &input.image,
        ]);
        let mut target = background_command("ssh");
        target.args([
            "-o",
            "BatchMode=yes",
            "--",
            &input.destination,
            "docker",
            "load",
        ]);
        let (source_result, target_result) = tauri::async_runtime::block_on(execution::pipe(
            TokioCommand::from(source),
            TokioCommand::from(target),
        ))?;
        if !source_result.status.success() {
            return Err(format!(
                "WSL Docker export failed: {}",
                String::from_utf8_lossy(&source_result.stderr).trim()
            ));
        }
        if !target_result.status.success() {
            return Err(format!(
                "remote Docker import failed: {}",
                String::from_utf8_lossy(&target_result.stderr).trim()
            ));
        }
        Ok(inventory)
    })
    .await
    .map_err(|error| format!("image transfer stopped: {error}"))?
}

/// Checks the fixed dependencies needed by offline WSL-to-SSH CLI provisioning.
#[tauri::command]
pub(super) async fn check_wsl_cli_provision(
    input: WslCliProvision,
    state: tauri::State<'_, ProfileState>,
) -> Result<CliProvisionCheck, String> {
    let destination = provision_destination(&input);
    let target = Target::from(destination.target.clone());
    if let Some(resolved) = native_ssh(&destination, &target, &state)? {
        let source = input.clone();
        let source_output = tauri::async_runtime::spawn_blocking(move || {
            validate_wsl_distribution(&source.distribution)?;
            let source_script = offline_source_check(source.image.as_deref())?;
            command_output(
                {
                    let mut command = background_command("wsl.exe");
                    command
                        .args([
                            "--distribution",
                            &source.distribution,
                            "--exec",
                            "bash",
                            "-lc",
                        ])
                        .arg(source_script);
                    command
                },
                "WSL provisioning requirements check",
            )
        })
        .await
        .map_err(|error| format!("WSL provisioning check stopped: {error}"))??;
        let remote_script = offline_destination_check(input.image.is_some());
        let destination_output = native_ssh_exec(
            &input.destination,
            resolved,
            &format!("bash -lc {}", shell_quote(&remote_script)),
        )
        .await?;
        return offline_check_result(input, source_output, destination_output);
    }
    tauri::async_runtime::spawn_blocking(move || {
        validate_wsl_distribution(&input.distribution)?;
        Target::Ssh {
            destination: input.destination.clone(),
        }
        .probe_request()
        .map_err(|error| error.to_string())?;
        if let Some(image) = &input.image {
            if !valid_image_reference(image) {
                return Err("invalid Docker image reference".to_owned());
            }
        }
        let source_script = offline_source_check(input.image.as_deref())?;
        let source_output = command_output(
            {
                let mut command = background_command("wsl.exe");
                command
                    .args([
                        "--distribution",
                        &input.distribution,
                        "--exec",
                        "bash",
                        "-lc",
                    ])
                    .arg(source_script);
                command
            },
            "WSL provisioning requirements check",
        )?;
        let remote_script = offline_destination_check(input.image.is_some());
        let destination_output = command_output(
            {
                let mut command = background_command("ssh");
                command
                    .args(["-o", "BatchMode=yes", "--", &input.destination])
                    .arg(format!("bash -lc {}", shell_quote(&remote_script)));
                command
            },
            "remote provisioning requirements check",
        )?;
        offline_check_result(input, source_output, destination_output)
    })
    .await
    .map_err(|error| format!("CLI provisioning check stopped: {error}"))?
}

/// Builds a minimal CLI kit in WSL and streams it to a system-SSH destination.
/// The kit excludes configuration, projects, sandbox data, and credentials.
#[tauri::command]
pub(super) async fn provision_wsl_cli(
    input: WslCliProvision,
    state: tauri::State<'_, ProfileState>,
) -> Result<CliProvisionResult, String> {
    let destination = provision_destination(&input);
    let target = Target::from(destination.target.clone());
    let native = native_ssh(&destination, &target, &state)?;
    if let Some(resolved) = native {
        validate_wsl_distribution(&input.distribution)?;
        let source_script = cli_export::command(input.image.as_deref())?;
        let remote_script = "set -Eeuo pipefail; kit=$(mktemp -d); trap 'rm -rf \"$kit\"' EXIT; tar -xzf - -C \"$kit\"; \"$kit/install-orcan-cli.sh\"; export PATH=\"$HOME/.local/bin:$PATH\"; orcan version";
        let stdout = native_ssh_stream_wsl(
            &input.distribution,
            &input.destination,
            resolved,
            source_script,
            format!("bash -lc {}", shell_quote(remote_script)),
            "CLI kit transfer",
        )
        .await?;
        let version = stdout.lines().last().unwrap_or_default().trim().to_owned();
        if version.is_empty() {
            return Err("remote CLI installation did not report an Orcan version".to_owned());
        }
        return Ok(CliProvisionResult {
            version,
            image: input.image,
        });
    }
    tauri::async_runtime::spawn_blocking(move || {
        validate_wsl_distribution(&input.distribution)?;
        Target::Ssh {
            destination: input.destination.clone(),
        }
        .probe_request()
        .map_err(|error| error.to_string())?;
        let source_script = cli_export::command(input.image.as_deref())?;
        let remote_script = "set -Eeuo pipefail; kit=$(mktemp -d); trap 'rm -rf \"$kit\"' EXIT; tar -xzf - -C \"$kit\"; \"$kit/install-orcan-cli.sh\"; export PATH=\"$HOME/.local/bin:$PATH\"; orcan version";
        let remote_command = format!("bash -lc {}", shell_quote(remote_script));

        let mut source = background_command("wsl.exe");
        source.args(["--distribution", &input.distribution, "--exec", "bash", "-lc"])
            .arg(source_script)
;
        let mut target = background_command("ssh");
        target.args(["-o", "BatchMode=yes", "--", &input.destination])
            .arg(remote_command)
;
        let (source_result, target_result) = tauri::async_runtime::block_on(execution::pipe(TokioCommand::from(source), TokioCommand::from(target)))?;
        if !source_result.status.success() {
            return Err(format!(
                "WSL CLI kit creation failed: {}",
                String::from_utf8_lossy(&source_result.stderr).trim()
            ));
        }
        if !target_result.status.success() {
            return Err(format!(
                "remote CLI installation failed: {}",
                String::from_utf8_lossy(&target_result.stderr).trim()
            ));
        }
        let version = String::from_utf8_lossy(&target_result.stdout)
            .lines()
            .last()
            .unwrap_or_default()
            .trim()
            .to_owned();
        if version.is_empty() {
            return Err("remote CLI installation did not report an Orcan version".to_owned());
        }
        Ok(CliProvisionResult {
            version,
            image: input.image,
        })
    })
    .await
    .map_err(|error| format!("CLI provisioning stopped: {error}"))?
}

/// Installs the public Orcan CLI on a saved profile. Profiles deliberately do
/// not require Orcan to exist, so this is the first provisioning step for a
/// new WSL, local, or SSH destination with internet access.
#[tauri::command]
pub(super) async fn check_online_provision(
    enclave: EnclaveInput,
    state: tauri::State<'_, ProfileState>,
) -> Result<OnlineProvisionCheck, String> {
    let target = Target::from(enclave.target.clone());
    if let (Some(resolved), Target::Ssh { destination }) =
        (native_ssh(&enclave, &target, &state)?, &target)
    {
        return native_ssh_exec(
            destination,
            resolved,
            &format!("bash -lc {}", shell_quote(ONLINE_PROVISION_CHECK_SCRIPT)),
        )
        .await
        .and_then(parse_online_provision_check);
    }
    tauri::async_runtime::spawn_blocking(move || {
        let output = match target {
            Target::Local => command_output(
                {
                    let mut command = background_command("bash");
                    command.args(["-lc", ONLINE_PROVISION_CHECK_SCRIPT]);
                    command
                },
                "local provisioning requirements check",
            ),
            Target::Wsl2 { distribution } => {
                validate_wsl_distribution(&distribution)?;
                command_output(
                    {
                        let mut command = background_command("wsl.exe");
                        command
                            .args(["--distribution", &distribution, "--exec", "bash", "-lc"])
                            .arg(ONLINE_PROVISION_CHECK_SCRIPT);
                        command
                    },
                    "WSL provisioning requirements check",
                )
            }
            Target::Ssh { destination } => command_output(
                {
                    let mut command = background_command("ssh");
                    command
                        .args(["-o", "BatchMode=yes", "--", &destination])
                        .arg(format!(
                            "bash -lc {}",
                            shell_quote(ONLINE_PROVISION_CHECK_SCRIPT)
                        ));
                    command
                },
                "remote provisioning requirements check",
            ),
        }?;
        parse_online_provision_check(output)
    })
    .await
    .map_err(|error| format!("online provisioning check stopped: {error}"))?
}

/// Installs or updates the public Orcan CLI after a successful preflight.
#[tauri::command]
pub(super) async fn provision_online(
    enclave: EnclaveInput,
    state: tauri::State<'_, ProfileState>,
) -> Result<CliProvisionResult, String> {
    let target = Target::from(enclave.target.clone());
    if let (Some(resolved), Target::Ssh { destination }) =
        (native_ssh(&enclave, &target, &state)?, &target)
    {
        let stdout = native_ssh_exec(
            destination,
            resolved,
            &format!("bash -lc {}", shell_quote(ONLINE_INSTALL_SCRIPT)),
        )
        .await?;
        let version = stdout
            .lines()
            .rev()
            .find(|line| !line.trim().is_empty())
            .unwrap_or_default()
            .trim()
            .to_owned();
        if version.is_empty() {
            return Err("online installation did not report an Orcan version".to_owned());
        }
        return Ok(CliProvisionResult {
            version,
            image: None,
        });
    }
    tauri::async_runtime::spawn_blocking(move || {
        let stdout = match target {
            Target::Local => command_output(
                {
                    let mut command = background_command("bash");
                    command.args(["-lc", ONLINE_INSTALL_SCRIPT]);
                    command
                },
                "local Orcan installation",
            )?,
            Target::Wsl2 { distribution } => {
                validate_wsl_distribution(&distribution)?;
                command_output(
                    {
                        let mut command = background_command("wsl.exe");
                        command
                            .args(["--distribution", &distribution, "--exec", "bash", "-lc"])
                            .arg(ONLINE_INSTALL_SCRIPT);
                        command
                    },
                    "WSL Orcan installation",
                )?
            }
            Target::Ssh { destination } => command_output(
                {
                    let mut command = background_command("ssh");
                    command
                        .args(["-o", "BatchMode=yes", "--", &destination])
                        .arg(format!("bash -lc {}", shell_quote(ONLINE_INSTALL_SCRIPT)));
                    command
                },
                "remote Orcan installation",
            )?,
        };
        let version = stdout
            .lines()
            .rev()
            .find(|line| !line.trim().is_empty())
            .unwrap_or_default()
            .trim()
            .to_owned();
        if version.is_empty() {
            return Err("online installation did not report an Orcan version".to_owned());
        }
        Ok(CliProvisionResult {
            version,
            image: None,
        })
    })
    .await
    .map_err(|error| format!("online provisioning stopped: {error}"))?
}
