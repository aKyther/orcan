#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use orcan_studio_core::{
    ConnectionProfile, MembershipAction, ProbeReport, ProfileStore, ProjectMode, ResolvedSsh,
    RuntimeAction, SshAuthentication, SshCredential, SystemRunner, Target, membership_args,
    parse_probe_report, remote_orcan_command, runtime_args, sync_args,
};
use russh::ChannelMsg;
use russh::client;
use russh::keys::{self, PublicKeyOrCertificate};
use serde::Deserialize;
use std::io;
use std::process::{Command, Stdio};
use std::sync::Arc;
use std::sync::Mutex;
use tauri::Manager;
use tokio::process::Command as TokioCommand;

#[derive(Clone, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
enum TargetInput {
    Local,
    Wsl2 { distribution: String },
    Ssh { destination: String },
}

#[derive(Deserialize)]
#[serde(rename_all = "snake_case")]
enum WorkspaceAction {
    Rename,
    Remove,
}

impl From<TargetInput> for Target {
    fn from(input: TargetInput) -> Self {
        match input {
            TargetInput::Local => Self::Local,
            TargetInput::Wsl2 { distribution } => Self::Wsl2 { distribution },
            TargetInput::Ssh { destination } => Self::Ssh { destination },
        }
    }
}

/// Identifies the Enclave a command runs on; credentials resolve from the store.
#[derive(Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct EnclaveInput {
    target: TargetInput,
    profile_id: Option<String>,
    credential_id: Option<String>,
    username: Option<String>,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct WslImageInput {
    distribution: String,
    image: String,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct WslImageTransfer {
    distribution: String,
    image: String,
    destination: String,
}

#[derive(Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct WslCliProvision {
    distribution: String,
    destination: String,
    destination_profile_id: Option<String>,
    destination_credential_id: Option<String>,
    destination_username: Option<String>,
    image: Option<String>,
}

#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
struct ImageInventory {
    image: String,
    id: String,
    size: String,
}

#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
struct CliProvisionResult {
    version: String,
    image: Option<String>,
}

#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
struct CliProvisionCheck {
    source: String,
    destination: String,
    image: Option<String>,
}

const ONLINE_INSTALL_SCRIPT: &str = "set -Eeuo pipefail; command -v curl >/dev/null || { echo 'curl is required for online installation' >&2; exit 127; }; curl -fsSL https://raw.githubusercontent.com/aKyther/orcan/main/install.sh | bash; export PATH=\"$HOME/.local/bin:$PATH\"; orcan version";

fn valid_image_reference(image: &str) -> bool {
    !image.is_empty()
        && image.len() <= 255
        && image
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || b"._/-:@+".contains(&byte))
}

fn validate_wsl_distribution(distribution: &str) -> Result<(), String> {
    Target::Wsl2 {
        distribution: distribution.to_owned(),
    }
    .probe_request()
    .map(|_| ())
    .map_err(|error| error.to_string())
}

fn shell_quote(value: &str) -> String {
    format!("'{}'", value.replace('\'', "'\"'\"'"))
}

fn decode_wsl_output(bytes: &[u8]) -> String {
    let utf16le = bytes.starts_with(&[0xff, 0xfe])
        || (bytes.len() > 1
            && bytes
                .iter()
                .skip(1)
                .step_by(2)
                .filter(|byte| **byte == 0)
                .count()
                * 2
                > bytes.len() / 2);
    if utf16le {
        let units = bytes
            .chunks_exact(2)
            .map(|pair| u16::from_le_bytes([pair[0], pair[1]]))
            .collect::<Vec<_>>();
        return String::from_utf16_lossy(units.strip_prefix(&[0xfeff]).unwrap_or(&units));
    }
    String::from_utf8_lossy(bytes).into_owned()
}

fn provision_destination(input: &WslCliProvision) -> EnclaveInput {
    EnclaveInput {
        target: TargetInput::Ssh {
            destination: input.destination.clone(),
        },
        profile_id: input.destination_profile_id.clone(),
        credential_id: input.destination_credential_id.clone(),
        username: input.destination_username.clone(),
    }
}

fn command_output(mut command: Command, label: &str) -> Result<String, String> {
    let output = command
        .output()
        .map_err(|error| format!("could not start {label}: {error}"))?;
    if output.status.success() {
        return Ok(String::from_utf8_lossy(&output.stdout).trim().to_owned());
    }
    let detail = String::from_utf8_lossy(&output.stderr).trim().to_owned();
    Err(format!("{label} failed: {detail}"))
}

fn wsl_image_inventory(input: &WslImageInput) -> Result<ImageInventory, String> {
    validate_wsl_distribution(&input.distribution)?;
    if !valid_image_reference(&input.image) {
        return Err("invalid Docker image reference".to_owned());
    }
    let output = Command::new("wsl.exe")
        .args([
            "--distribution",
            &input.distribution,
            "--exec",
            "docker",
            "image",
            "inspect",
            "--format",
            "{{.Id}}\t{{.Size}}",
            &input.image,
        ])
        .output()
        .map_err(|error| format!("could not start WSL Docker: {error}"))?;
    if !output.status.success() {
        return Err(String::from_utf8_lossy(&output.stderr).trim().to_owned());
    }
    let output_text = String::from_utf8_lossy(&output.stdout);
    let mut fields = output_text.trim().split('\t');
    let id = fields.next().unwrap_or_default();
    let size = fields.next().unwrap_or_default();
    if id.is_empty() || size.is_empty() {
        return Err("WSL Docker returned an incomplete image inventory".to_owned());
    }
    Ok(ImageInventory {
        image: input.image.clone(),
        id: id.to_owned(),
        size: size.to_owned(),
    })
}

#[tauri::command]
async fn wsl_image_inventory_command(input: WslImageInput) -> Result<ImageInventory, String> {
    tauri::async_runtime::spawn_blocking(move || wsl_image_inventory(&input))
        .await
        .map_err(|error| format!("image inventory stopped: {error}"))?
}

/// Streams a Docker image from a local WSL distribution to a system-SSH target.
/// The image is never buffered or written by Studio.
#[tauri::command]
async fn transfer_wsl_image(input: WslImageTransfer) -> Result<ImageInventory, String> {
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
        let mut source = Command::new("wsl.exe")
            .args([
                "--distribution",
                &input.distribution,
                "--exec",
                "docker",
                "save",
                &input.image,
            ])
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|error| format!("could not start WSL Docker export: {error}"))?;
        let mut target = Command::new("ssh")
            .args([
                "-o",
                "BatchMode=yes",
                "--",
                &input.destination,
                "docker",
                "load",
            ])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|error| format!("could not start SSH image import: {error}"))?;
        let mut input_stream = source
            .stdout
            .take()
            .ok_or_else(|| "WSL image export has no stdout".to_owned())?;
        let mut output_stream = target
            .stdin
            .take()
            .ok_or_else(|| "SSH image import has no stdin".to_owned())?;
        io::copy(&mut input_stream, &mut output_stream)
            .map_err(|error| format!("image transfer interrupted: {error}"))?;
        drop(output_stream);
        let source_result = source
            .wait_with_output()
            .map_err(|error| format!("could not finish WSL image export: {error}"))?;
        let target_result = target
            .wait_with_output()
            .map_err(|error| format!("could not finish SSH image import: {error}"))?;
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
async fn check_wsl_cli_provision(
    input: WslCliProvision,
    state: tauri::State<'_, ProfileState>,
) -> Result<CliProvisionCheck, String> {
    let destination = provision_destination(&input);
    let target = Target::from(destination.target.clone());
    if let Some(resolved) = native_ssh(&destination, &target, &state)? {
        let source = input.clone();
        tauri::async_runtime::spawn_blocking(move || {
            validate_wsl_distribution(&source.distribution)?;
            let source_script = if let Some(image) = &source.image {
                if !valid_image_reference(image) {
                    return Err("invalid Docker image reference".to_owned());
                }
                format!("set -Eeuo pipefail; command -v orcan >/dev/null; command -v tar >/dev/null; docker image inspect {} >/dev/null", shell_quote(image))
            } else {
                "set -Eeuo pipefail; command -v orcan >/dev/null; command -v tar >/dev/null".to_owned()
            };
            command_output({ let mut command = Command::new("wsl.exe"); command.args(["--distribution", &source.distribution, "--exec", "bash", "-lc"]).arg(source_script); command }, "WSL provisioning requirements check")
        })
        .await
        .map_err(|error| format!("WSL provisioning check stopped: {error}"))??;
        let remote_script = if input.image.is_some() {
            "set -Eeuo pipefail; command -v tar >/dev/null; docker info >/dev/null"
        } else {
            "set -Eeuo pipefail; command -v tar >/dev/null"
        };
        native_ssh_exec(
            &input.destination,
            resolved,
            &format!("bash -lc {}", shell_quote(remote_script)),
        )
        .await?;
        return Ok(CliProvisionCheck {
            source: input.distribution,
            destination: input.destination,
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
        if let Some(image) = &input.image {
            if !valid_image_reference(image) {
                return Err("invalid Docker image reference".to_owned());
            }
        }
        let source_script = if let Some(image) = &input.image {
            format!(
                "set -Eeuo pipefail; command -v orcan >/dev/null; command -v tar >/dev/null; docker image inspect {} >/dev/null",
                shell_quote(image)
            )
        } else {
            "set -Eeuo pipefail; command -v orcan >/dev/null; command -v tar >/dev/null".to_owned()
        };
        command_output(
            {
                let mut command = Command::new("wsl.exe");
                command
                    .args(["--distribution", &input.distribution, "--exec", "bash", "-lc"])
                    .arg(source_script);
                command
            },
            "WSL provisioning requirements check",
        )?;
        let remote_script = if input.image.is_some() {
            "set -Eeuo pipefail; command -v tar >/dev/null; docker info >/dev/null"
        } else {
            "set -Eeuo pipefail; command -v tar >/dev/null"
        };
        command_output(
            {
                let mut command = Command::new("ssh");
                command
                    .args(["-o", "BatchMode=yes", "--", &input.destination])
                    .arg(format!("bash -lc {}", shell_quote(remote_script)));
                command
            },
            "remote provisioning requirements check",
        )?;
        Ok(CliProvisionCheck {
            source: input.distribution,
            destination: input.destination,
            image: input.image,
        })
    })
    .await
    .map_err(|error| format!("CLI provisioning check stopped: {error}"))?
}

/// Builds a minimal CLI kit in WSL and streams it to a system-SSH destination.
/// The kit excludes configuration, projects, sandbox data, and credentials.
#[tauri::command]
async fn provision_wsl_cli(
    input: WslCliProvision,
    state: tauri::State<'_, ProfileState>,
) -> Result<CliProvisionResult, String> {
    let destination = provision_destination(&input);
    let target = Target::from(destination.target.clone());
    let native = native_ssh(&destination, &target, &state)?;
    if let Some(resolved) = native {
        validate_wsl_distribution(&input.distribution)?;
        if let Some(image) = &input.image {
            if !valid_image_reference(image) {
                return Err("invalid Docker image reference".to_owned());
            }
        }
        let image_arg = input
            .image
            .as_deref()
            .map(|image| format!(" --image {}", shell_quote(image)))
            .unwrap_or_default();
        let source_script = format!(
            "set -Eeuo pipefail; kit=$(mktemp -d); trap 'rm -rf \"$kit\"' EXIT; orcan bundle create --output \"$kit\"{image_arg}; tar -C \"$kit\" -czf - ."
        );
        let remote_script = "set -Eeuo pipefail; kit=$(mktemp -d); trap 'rm -rf \"$kit\"' EXIT; tar -xzf - -C \"$kit\"; \"$kit/install-orcan-cli.sh\"; export PATH=\"$HOME/.local/bin:$PATH\"; orcan version";
        let stdout = native_ssh_install_wsl_kit(
            &input.distribution,
            &input.destination,
            resolved,
            source_script,
            format!("bash -lc {}", shell_quote(remote_script)),
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
        if let Some(image) = &input.image {
            if !valid_image_reference(image) {
                return Err("invalid Docker image reference".to_owned());
            }
        }

        let image_arg = input
            .image
            .as_deref()
            .map(|image| format!(" --image {}", shell_quote(image)))
            .unwrap_or_default();
        let source_script = format!(
            "set -Eeuo pipefail; kit=$(mktemp -d); trap 'rm -rf \"$kit\"' EXIT; orcan bundle create --output \"$kit\"{image_arg}; tar -C \"$kit\" -czf - ."
        );
        let remote_script = "set -Eeuo pipefail; kit=$(mktemp -d); trap 'rm -rf \"$kit\"' EXIT; tar -xzf - -C \"$kit\"; \"$kit/install-orcan-cli.sh\"; export PATH=\"$HOME/.local/bin:$PATH\"; orcan version";
        let remote_command = format!("bash -lc {}", shell_quote(remote_script));

        let mut source = Command::new("wsl.exe")
            .args(["--distribution", &input.distribution, "--exec", "bash", "-lc"])
            .arg(source_script)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|error| format!("could not create a WSL CLI kit: {error}"))?;
        let mut target = Command::new("ssh")
            .args(["-o", "BatchMode=yes", "--", &input.destination])
            .arg(remote_command)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|error| format!("could not start SSH CLI installation: {error}"))?;
        let mut input_stream = source
            .stdout
            .take()
            .ok_or_else(|| "WSL CLI kit has no stdout".to_owned())?;
        let mut output_stream = target
            .stdin
            .take()
            .ok_or_else(|| "SSH CLI installation has no stdin".to_owned())?;
        io::copy(&mut input_stream, &mut output_stream)
            .map_err(|error| format!("CLI kit transfer interrupted: {error}"))?;
        drop(output_stream);
        let source_result = source
            .wait_with_output()
            .map_err(|error| format!("could not finish WSL CLI kit: {error}"))?;
        let target_result = target
            .wait_with_output()
            .map_err(|error| format!("could not finish SSH CLI installation: {error}"))?;
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
async fn provision_online(
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
                    let mut command = Command::new("bash");
                    command.args(["-lc", ONLINE_INSTALL_SCRIPT]);
                    command
                },
                "local Orcan installation",
            )?,
            Target::Wsl2 { distribution } => {
                validate_wsl_distribution(&distribution)?;
                command_output(
                    {
                        let mut command = Command::new("wsl.exe");
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
                    let mut command = Command::new("ssh");
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

/// Native SSH options when the Enclave signs in with a saved key or password.
fn native_ssh(
    enclave: &EnclaveInput,
    target: &Target,
    state: &tauri::State<'_, ProfileState>,
) -> Result<Option<ResolvedSsh>, String> {
    let resolved = state
        .0
        .lock()
        .map_err(|_| "profile store is unavailable".to_owned())?
        .resolve_ssh(
            enclave.profile_id.as_deref(),
            enclave.credential_id.as_deref(),
            enclave.username.as_deref(),
        )
        .map_err(|error| error.to_string())?;
    let Some((profile, resolved)) = resolved else {
        return Ok(None);
    };
    if profile.is_some_and(|profile| &profile.target != target) {
        return Err("save this connection before using its credentials".to_owned());
    }
    Ok((matches!(target, Target::Ssh { .. })
        && matches!(
            resolved.ssh.authentication,
            SshAuthentication::Password | SshAuthentication::PrivateKey { .. }
        ))
    .then_some(resolved))
}

/// Runs `orcan <args>` on the Enclave and returns its stdout.
async fn run_on_enclave(
    enclave: EnclaveInput,
    args: Vec<String>,
    state: tauri::State<'_, ProfileState>,
) -> Result<String, String> {
    let target = Target::from(enclave.target.clone());
    if let (Some(resolved), Target::Ssh { destination }) =
        (native_ssh(&enclave, &target, &state)?, &target)
    {
        return native_ssh_exec(destination, resolved, &remote_orcan_command(&args)).await;
    }
    tauri::async_runtime::spawn_blocking(move || target.run_orcan(&SystemRunner, &args))
        .await
        .map_err(|error| format!("Orcan task stopped: {error}"))?
        .map(|output| output.stdout)
        .map_err(|error| error.to_string())
}

#[tauri::command]
async fn probe(
    enclave: EnclaveInput,
    state: tauri::State<'_, ProfileState>,
) -> Result<ProbeReport, String> {
    let args = ["studio", "probe", "--json"].map(str::to_owned).to_vec();
    let stdout = run_on_enclave(enclave, args, state).await?;
    parse_probe_report(&stdout).map_err(|error| error.to_string())
}

/// Lists distributions that the Windows WSL launcher exposes to Studio.
#[tauri::command]
async fn list_wsl_distributions() -> Result<Vec<String>, String> {
    tauri::async_runtime::spawn_blocking(|| {
        let output = Command::new("wsl.exe")
            .args(["--list", "--quiet"])
            .output()
            .map_err(|error| format!("could not start wsl.exe: {error}"))?;
        if !output.status.success() {
            return Err(String::from_utf8_lossy(&output.stderr).trim().to_owned());
        }
        Ok(decode_wsl_output(&output.stdout)
            .split(['\n', '\0'])
            .map(|name| {
                name.trim_matches(|character: char| {
                    character.is_whitespace() || character == '\u{feff}'
                })
            })
            .filter(|name| !name.is_empty())
            .map(str::to_owned)
            .collect())
    })
    .await
    .map_err(|error| format!("WSL discovery stopped: {error}"))?
}

/// Returns the Linux account used when Studio starts commands in a WSL
/// distribution without an explicit `--user` override.
#[tauri::command]
async fn wsl_default_user(distribution: String) -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(move || {
        validate_wsl_distribution(&distribution)?;
        command_output(
            {
                let mut command = Command::new("wsl.exe");
                command.args(["--distribution", &distribution, "--exec", "id", "-un"]);
                command
            },
            "WSL default-user check",
        )
    })
    .await
    .map_err(|error| format!("WSL default-user check stopped: {error}"))?
}

/// A convenience value only: the remote credential form remains editable
/// because an SSH server may use a different account than this device.
#[tauri::command]
fn current_user() -> String {
    ["USERNAME", "USER"]
        .into_iter()
        .filter_map(|name| std::env::var(name).ok())
        .find(|user| {
            !user.is_empty()
                && user
                    .chars()
                    .all(|character| character.is_ascii_alphanumeric() || "._-".contains(character))
        })
        .unwrap_or_default()
}

#[tauri::command]
async fn sync(enclave: EnclaveInput, state: tauri::State<'_, ProfileState>) -> Result<(), String> {
    run_on_enclave(enclave, sync_args(), state)
        .await
        .map(|_| ())
}

#[tauri::command]
async fn enclave_action(
    enclave: EnclaveInput,
    apply: bool,
    with_git: bool,
    with_docker: bool,
    with_ttyd: bool,
    ttyd_credential: Option<String>,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    let mut args = vec![
        "studio".to_owned(),
        "enclave".to_owned(),
        if apply { "apply" } else { "plan" }.to_owned(),
        "--empty".to_owned(),
    ];
    if with_git {
        args.push("--with-git".to_owned());
    }
    if with_docker {
        args.push("--with-docker".to_owned());
    }
    let ttyd_credential = ttyd_credential.filter(|value| !value.is_empty());
    if with_ttyd && ttyd_credential.is_none() {
        args.push("--with-ttyd".to_owned());
    }
    if let Some(credential) = ttyd_credential {
        args.extend(["--with-ttyd-auth".to_owned(), credential]);
    }
    if apply {
        args.push("--yes".to_owned());
    }
    let stdout = run_on_enclave(enclave, args, state).await?;
    serde_json::from_str(&stdout).map_err(|error| format!("invalid enclave response: {error}"))
}

#[tauri::command]
async fn runtime_action(
    enclave: EnclaveInput,
    action: RuntimeAction,
    state: tauri::State<'_, ProfileState>,
) -> Result<(), String> {
    run_on_enclave(enclave, runtime_args(action), state)
        .await
        .map(|_| ())
}

/// Plans or applies a workspace membership change on the Enclave.
#[tauri::command]
async fn membership_action(
    enclave: EnclaveInput,
    action: MembershipAction,
    workspace: String,
    project: String,
    project_mode: ProjectMode,
    apply: bool,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    let args = membership_args(action, &workspace, &project, project_mode, apply)
        .map_err(|error| error.to_string())?;
    let stdout = run_on_enclave(enclave, args, state).await?;
    let value: serde_json::Value = serde_json::from_str(&stdout)
        .map_err(|error| format!("invalid settings response: {error}"))?;
    if value["ok"] == false {
        return Err(value["error"]
            .as_str()
            .unwrap_or("settings change refused")
            .to_owned());
    }
    Ok(value)
}

#[tauri::command]
async fn workspace_action(
    enclave: EnclaveInput,
    action: WorkspaceAction,
    workspace: String,
    new_name: Option<String>,
    apply: bool,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    let operation = match action {
        WorkspaceAction::Rename => "workspace-rename",
        WorkspaceAction::Remove => "workspace-remove",
    };
    let mut args = vec![
        "studio".to_owned(),
        "settings".to_owned(),
        format!("{operation}-{}", if apply { "apply" } else { "plan" }),
        "--workspace".to_owned(),
        workspace,
    ];
    if let Some(new_name) = new_name {
        args.extend(["--new-name".to_owned(), new_name]);
    }
    if apply {
        args.push("--yes".to_owned());
    }
    studio_json(enclave, args, state).await
}

#[derive(Debug)]
struct KnownHostsHandler {
    host: String,
    port: u16,
}

impl client::Handler for KnownHostsHandler {
    type Error = russh::Error;

    async fn check_server_key(
        &mut self,
        server_public_key: &PublicKeyOrCertificate,
    ) -> Result<bool, Self::Error> {
        // Unknown, changed, and unreadable known_hosts entries all reject the
        // connection. Studio never learns a key merely because it saw one.
        Ok(keys::known_hosts::check_known_hosts(
            &self.host,
            self.port,
            &server_public_key.public_key(),
        )
        .unwrap_or(false))
    }
}

fn ssh_endpoint(destination: &str) -> Result<(String, u16), String> {
    if let Some(bracketed) = destination.strip_prefix('[') {
        let (host, port) = bracketed
            .split_once("]:")
            .ok_or_else(|| "use [IPv6-address]:port for an IPv6 SSH destination".to_owned())?;
        return Ok((
            host.to_owned(),
            port.parse().map_err(|_| "invalid SSH port".to_owned())?,
        ));
    }
    if let Some((host, port)) = destination.rsplit_once(':') {
        if !host.contains(':') && port.chars().all(|character| character.is_ascii_digit()) {
            return Ok((
                host.to_owned(),
                port.parse().map_err(|_| "invalid SSH port".to_owned())?,
            ));
        }
    }
    Ok((destination.to_owned(), 22))
}

fn required_vault_secret(owner: &str, kind: &str) -> Result<String, String> {
    vault_entry(owner, kind)?
        .get_password()
        .map_err(|_| format!("no {kind} is stored for this connection"))
}

async fn native_ssh_connect(
    destination: &str,
    resolved: ResolvedSsh,
) -> Result<client::Handle<KnownHostsHandler>, String> {
    let ResolvedSsh { vault_owner, ssh } = resolved;
    let username = ssh
        .username
        .as_deref()
        .ok_or_else(|| "SSH username is required for this authentication method".to_owned())?;
    let (host, port) = ssh_endpoint(destination)?;
    let handler = KnownHostsHandler {
        host: host.clone(),
        port,
    };
    let mut session = client::connect(
        Arc::new(client::Config::default()),
        (host.as_str(), port),
        handler,
    )
    .await
    .map_err(|error| format!("SSH connection or host-key verification failed: {error}"))?;
    let authenticated = match &ssh.authentication {
        SshAuthentication::Password => session
            .authenticate_password(username, required_vault_secret(&vault_owner, "password")?)
            .await
            .map_err(|error| format!("password authentication failed: {error}"))?,
        SshAuthentication::PrivateKey {
            path,
            has_passphrase,
        } => {
            let passphrase = has_passphrase
                .then(|| required_vault_secret(&vault_owner, "key-passphrase"))
                .transpose()?;
            let key = keys::load_secret_key(path, passphrase.as_deref())
                .map_err(|error| format!("could not read private key: {error}"))?;
            session
                .authenticate_publickey(
                    username,
                    keys::PrivateKeyWithHashAlg::new(Arc::new(key), None),
                )
                .await
                .map_err(|error| format!("private-key authentication failed: {error}"))?
        }
        SshAuthentication::Agent => {
            return Err("SSH agent profiles use the system SSH transport".to_owned());
        }
    };
    if !authenticated.success() {
        return Err("SSH authentication was rejected by the remote host".to_owned());
    }
    Ok(session)
}

/// Runs one command over native SSH (host key checked against known_hosts).
async fn native_ssh_exec(
    destination: &str,
    resolved: ResolvedSsh,
    command: &str,
) -> Result<String, String> {
    let ResolvedSsh { vault_owner, ssh } = resolved;
    let username = ssh
        .username
        .as_deref()
        .ok_or_else(|| "SSH username is required for this authentication method".to_owned())?;
    let (host, port) = ssh_endpoint(destination)?;
    let handler = KnownHostsHandler {
        host: host.clone(),
        port,
    };
    let mut session = client::connect(
        Arc::new(client::Config::default()),
        (host.as_str(), port),
        handler,
    )
    .await
    .map_err(|error| format!("SSH connection or host-key verification failed: {error}"))?;

    let authenticated = match &ssh.authentication {
        SshAuthentication::Password => {
            let password = required_vault_secret(&vault_owner, "password")?;
            session
                .authenticate_password(username, password)
                .await
                .map_err(|error| format!("password authentication failed: {error}"))?
        }
        SshAuthentication::PrivateKey {
            path,
            has_passphrase,
        } => {
            let passphrase = has_passphrase
                .then(|| required_vault_secret(&vault_owner, "key-passphrase"))
                .transpose()?;
            let key = keys::load_secret_key(path, passphrase.as_deref())
                .map_err(|error| format!("could not read private key: {error}"))?;
            session
                .authenticate_publickey(
                    username,
                    keys::PrivateKeyWithHashAlg::new(Arc::new(key), None),
                )
                .await
                .map_err(|error| format!("private-key authentication failed: {error}"))?
        }
        SshAuthentication::Agent => {
            return Err("SSH agent profiles use the system SSH transport".to_owned());
        }
    };
    if !authenticated.success() {
        return Err("SSH authentication was rejected by the remote host".to_owned());
    }

    let mut channel = session
        .channel_open_session()
        .await
        .map_err(|error| format!("could not open SSH command channel: {error}"))?;
    channel
        .exec(true, command)
        .await
        .map_err(|error| format!("could not start Orcan on the Enclave: {error}"))?;

    let mut stdout = Vec::new();
    let mut stderr = Vec::new();
    let mut exit_status = None;
    while let Some(message) = channel.wait().await {
        match message {
            ChannelMsg::Data { data } => stdout.extend_from_slice(&data),
            ChannelMsg::ExtendedData { data, .. } => stderr.extend_from_slice(&data),
            ChannelMsg::ExitStatus {
                exit_status: status,
            } => exit_status = Some(status),
            _ => {}
        }
    }
    if exit_status.unwrap_or(1) != 0 {
        return Err(format!(
            "`{command}` failed on the Enclave: {}",
            String::from_utf8_lossy(&stderr).trim()
        ));
    }
    Ok(String::from_utf8_lossy(&stdout).into_owned())
}

async fn native_ssh_install_wsl_kit(
    distribution: &str,
    destination: &str,
    resolved: ResolvedSsh,
    source_script: String,
    remote_command: String,
) -> Result<String, String> {
    let mut source = TokioCommand::new("wsl.exe")
        .args(["--distribution", distribution, "--exec", "bash", "-lc"])
        .arg(source_script)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| format!("could not create a WSL CLI kit: {error}"))?;
    let source_stdout = source
        .stdout
        .take()
        .ok_or_else(|| "WSL CLI kit has no stdout".to_owned())?;
    let session = native_ssh_connect(destination, resolved).await?;
    let mut channel = session
        .channel_open_session()
        .await
        .map_err(|error| format!("could not open SSH installation channel: {error}"))?;
    channel
        .exec(true, remote_command.as_str())
        .await
        .map_err(|error| format!("could not start remote CLI installation: {error}"))?;
    channel
        .data(source_stdout)
        .await
        .map_err(|error| format!("CLI kit transfer interrupted: {error}"))?;
    channel
        .eof()
        .await
        .map_err(|error| format!("could not finish CLI kit transfer: {error}"))?;
    let source_result = source
        .wait_with_output()
        .await
        .map_err(|error| format!("could not finish WSL CLI kit: {error}"))?;
    if !source_result.status.success() {
        return Err(format!(
            "WSL CLI kit creation failed: {}",
            String::from_utf8_lossy(&source_result.stderr).trim()
        ));
    }
    let mut stdout = Vec::new();
    let mut stderr = Vec::new();
    let mut exit_status = None;
    while let Some(message) = channel.wait().await {
        match message {
            ChannelMsg::Data { data } => stdout.extend_from_slice(&data),
            ChannelMsg::ExtendedData { data, .. } => stderr.extend_from_slice(&data),
            ChannelMsg::ExitStatus {
                exit_status: status,
            } => exit_status = Some(status),
            _ => {}
        }
    }
    if exit_status.unwrap_or(1) != 0 {
        return Err(format!(
            "remote CLI installation failed: {}",
            String::from_utf8_lossy(&stderr).trim()
        ));
    }
    Ok(String::from_utf8_lossy(&stdout).into_owned())
}

struct ProfileState(Mutex<ProfileStore>);

/// Execute a Studio helper through the selected Enclave and decode its JSON reply.
async fn studio_json(
    enclave: EnclaveInput,
    args: Vec<String>,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    let stdout = run_on_enclave(enclave, args, state).await?;
    let value: serde_json::Value = serde_json::from_str(&stdout)
        .map_err(|error| format!("invalid Orcan Studio response: {error}"))?;
    if value["ok"] == false {
        return Err(value["error"]
            .as_str()
            .unwrap_or("Orcan Studio operation refused")
            .to_owned());
    }
    Ok(value)
}

#[tauri::command]
async fn parent_plan(
    enclave: EnclaveInput,
    path: String,
    branch: String,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    parent_command(enclave, "plan", path, branch, None, state).await
}

#[tauri::command]
async fn import_plan(
    enclave: EnclaveInput,
    source: String,
    projects_root: String,
    parent: Option<String>,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    let mut args = vec![
        "studio",
        "import",
        "plan",
        "--source",
        &source,
        "--projects-root",
        &projects_root,
    ]
    .into_iter()
    .map(str::to_owned)
    .collect::<Vec<_>>();
    if let Some(parent) = parent.filter(|value| !value.trim().is_empty()) {
        args.extend(["--parent".to_owned(), parent]);
    }
    studio_json(enclave, args, state).await
}

#[tauri::command]
async fn import_apply(
    enclave: EnclaveInput,
    source: String,
    projects_root: String,
    parent: Option<String>,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    let mut args = vec![
        "studio",
        "import",
        "apply",
        "--source",
        &source,
        "--projects-root",
        &projects_root,
        "--yes",
    ]
    .into_iter()
    .map(str::to_owned)
    .collect::<Vec<_>>();
    if let Some(parent) = parent.filter(|value| !value.trim().is_empty()) {
        args.extend(["--parent".to_owned(), parent]);
    }
    studio_json(enclave, args, state).await
}

#[tauri::command]
async fn directory_plan(
    enclave: EnclaveInput,
    projects_root: String,
    parent: String,
    name: String,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    studio_json(
        enclave,
        vec![
            "studio",
            "directory",
            "plan",
            "--projects-root",
            &projects_root,
            "--parent",
            &parent,
            "--name",
            &name,
        ]
        .into_iter()
        .map(str::to_owned)
        .collect(),
        state,
    )
    .await
}

#[tauri::command]
async fn directory_apply(
    enclave: EnclaveInput,
    projects_root: String,
    parent: String,
    name: String,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    studio_json(
        enclave,
        vec![
            "studio",
            "directory",
            "apply",
            "--projects-root",
            &projects_root,
            "--parent",
            &parent,
            "--name",
            &name,
            "--yes",
        ]
        .into_iter()
        .map(str::to_owned)
        .collect(),
        state,
    )
    .await
}

#[tauri::command]
async fn worktree_branches(
    enclave: EnclaveInput,
    repo: String,
    worktrees_root: String,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    studio_json(
        enclave,
        vec![
            "studio",
            "worktree",
            "branches",
            "--repo",
            &repo,
            "--worktrees-root",
            &worktrees_root,
        ]
        .into_iter()
        .map(str::to_owned)
        .collect(),
        state,
    )
    .await
}

#[tauri::command]
async fn worktree_cleanup(
    enclave: EnclaveInput,
    path: String,
    worktrees_root: String,
    remove_branch: bool,
    apply: bool,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    let mut args = vec![
        "studio",
        "worktree",
        if apply { "remove-apply" } else { "remove-plan" },
        "--path",
        &path,
        "--worktrees-root",
        &worktrees_root,
    ]
    .into_iter()
    .map(str::to_owned)
    .collect::<Vec<_>>();
    if apply {
        args.push("--yes".to_owned());
    }
    if remove_branch {
        args.push("--remove-branch".to_owned());
    }
    studio_json(enclave, args, state).await
}

#[tauri::command]
async fn parent_apply(
    enclave: EnclaveInput,
    path: String,
    branch: String,
    expected_head: String,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    parent_command(enclave, "apply", path, branch, Some(expected_head), state).await
}

async fn parent_command(
    enclave: EnclaveInput,
    mode: &str,
    path: String,
    branch: String,
    expected_head: Option<String>,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    let mut args = vec![
        "studio".to_owned(),
        "parent".to_owned(),
        mode.to_owned(),
        "--path".to_owned(),
        path,
        "--branch".to_owned(),
        branch,
    ];
    if let Some(head) = expected_head {
        args.extend(["--expected-head".to_owned(), head, "--yes".to_owned()]);
    }
    studio_json(enclave, args, state).await
}

/// `owner` is a profile id (legacy inline SSH) or `credential:<id>`.
fn vault_entry(owner: &str, kind: &str) -> Result<keyring::Entry, String> {
    keyring::Entry::new("io.orcan.studio", &format!("{owner}:{kind}"))
        .map_err(|error| format!("credential vault unavailable: {error}"))
}

#[tauri::command]
fn list_profiles(state: tauri::State<'_, ProfileState>) -> Result<Vec<ConnectionProfile>, String> {
    state
        .0
        .lock()
        .map_err(|_| "profile store is unavailable".to_owned())?
        .list()
        .map_err(|error| error.to_string())
}

#[tauri::command]
fn save_profile(
    profile: ConnectionProfile,
    state: tauri::State<'_, ProfileState>,
) -> Result<(), String> {
    state
        .0
        .lock()
        .map_err(|_| "profile store is unavailable".to_owned())?
        .upsert(profile)
        .map_err(|error| error.to_string())
}

#[tauri::command]
fn delete_profile(id: String, state: tauri::State<'_, ProfileState>) -> Result<(), String> {
    state
        .0
        .lock()
        .map_err(|_| "profile store is unavailable".to_owned())?
        .delete(&id)
        .map_err(|error| error.to_string())?;
    delete_vault_secrets(&id);
    Ok(())
}

fn delete_vault_secrets(owner: &str) {
    for kind in ["password", "key-passphrase"] {
        let _ = vault_entry(owner, kind)
            .and_then(|entry| entry.delete_credential().map_err(|error| error.to_string()));
    }
}

#[tauri::command]
fn list_credentials(state: tauri::State<'_, ProfileState>) -> Result<Vec<SshCredential>, String> {
    state
        .0
        .lock()
        .map_err(|_| "profile store is unavailable".to_owned())?
        .list_credentials()
        .map_err(|error| error.to_string())
}

/// Saves the credential and, when given, its secret in the OS vault.
#[tauri::command]
fn save_credential(
    credential: SshCredential,
    secret: Option<String>,
    state: tauri::State<'_, ProfileState>,
) -> Result<(), String> {
    let kind = match credential.authentication {
        SshAuthentication::Password => "password",
        SshAuthentication::PrivateKey { .. } => "key-passphrase",
        SshAuthentication::Agent => "",
    };
    state
        .0
        .lock()
        .map_err(|_| "profile store is unavailable".to_owned())?
        .upsert_credential(credential.clone())
        .map_err(|error| error.to_string())?;
    match secret.filter(|secret| !secret.is_empty()) {
        Some(secret) if !kind.is_empty() => vault_entry(&credential.vault_owner(), kind)?
            .set_password(&secret)
            .map_err(|error| format!("could not store credential: {error}")),
        _ => Ok(()),
    }
}

#[tauri::command]
fn delete_credential(id: String, state: tauri::State<'_, ProfileState>) -> Result<(), String> {
    state
        .0
        .lock()
        .map_err(|_| "profile store is unavailable".to_owned())?
        .delete_credential(&id)
        .map_err(|error| error.to_string())?;
    delete_vault_secrets(&format!("credential:{id}"));
    Ok(())
}

#[tauri::command]
fn save_secret(profile_id: String, kind: String, secret: String) -> Result<(), String> {
    if secret.is_empty() || !matches!(kind.as_str(), "password" | "key-passphrase") {
        return Err("invalid credential payload".to_owned());
    }
    vault_entry(&profile_id, &kind)?
        .set_password(&secret)
        .map_err(|error| format!("could not store credential: {error}"))
}

#[tauri::command]
async fn worktree_plan(
    enclave: EnclaveInput,
    repo: String,
    branch: String,
    worktrees_root: String,
    workspaces: Vec<String>,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    let mut args = vec![
        "studio".to_owned(),
        "worktree".to_owned(),
        "plan".to_owned(),
        "--repo".to_owned(),
        repo,
        "--branch".to_owned(),
        branch,
        "--worktrees-root".to_owned(),
        worktrees_root,
    ];
    for workspace in workspaces {
        args.extend(["--workspace".to_owned(), workspace]);
    }
    studio_json(enclave, args, state).await
}

#[tauri::command]
async fn worktree_inventory(
    enclave: EnclaveInput,
    worktrees_root: String,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    studio_json(
        enclave,
        vec![
            "studio".to_owned(),
            "worktree".to_owned(),
            "list".to_owned(),
            "--worktrees-root".to_owned(),
            worktrees_root,
        ],
        state,
    )
    .await
}

#[tauri::command]
async fn worktree_apply(
    enclave: EnclaveInput,
    repo: String,
    branch: String,
    worktrees_root: String,
    workspaces: Vec<String>,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    let mut args = vec![
        "studio".to_owned(),
        "worktree".to_owned(),
        "apply".to_owned(),
        "--repo".to_owned(),
        repo,
        "--branch".to_owned(),
        branch,
        "--worktrees-root".to_owned(),
        worktrees_root,
        "--yes".to_owned(),
    ];
    for workspace in workspaces {
        args.extend(["--workspace".to_owned(), workspace]);
    }
    studio_json(enclave, args, state).await
}

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            let data_dir = app.path().app_data_dir()?;
            app.manage(ProfileState(Mutex::new(ProfileStore::new(
                data_dir.join("profiles.json"),
            ))));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            list_wsl_distributions,
            wsl_default_user,
            wsl_image_inventory_command,
            transfer_wsl_image,
            check_wsl_cli_provision,
            provision_wsl_cli,
            provision_online,
            probe,
            enclave_action,
            sync,
            runtime_action,
            current_user,
            list_profiles,
            save_profile,
            delete_profile,
            save_secret,
            list_credentials,
            save_credential,
            delete_credential,
            parent_plan,
            parent_apply,
            import_plan,
            import_apply,
            directory_plan,
            directory_apply,
            worktree_branches,
            worktree_cleanup,
            worktree_plan,
            worktree_inventory,
            worktree_apply,
            membership_action,
            workspace_action
        ])
        .run(tauri::generate_context!())
        .expect("error while running Orcan Studio");
}
