#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use orcan_studio_core::{
    MembershipAction, ProbeReport, ProfileStore, ProjectMode, ResolvedSsh, RuntimeAction,
    SshAuthentication, Target, membership_args, parse_probe_report, remote_orcan_command,
    runtime_args, sync_args,
};
use serde::{Deserialize, Serialize};
use std::io;
use std::process::{Command, Stdio};
use std::sync::Mutex;
use tauri::Manager;
use tokio::process::Command as TokioCommand;

mod cleanup;
mod commands;
mod context;
mod execution;
use context::studio_json;
mod profiles;
mod ssh;
#[cfg(test)]
use ssh::parse_host_trust_config;
use ssh::{native_ssh_connect, native_ssh_exec, native_ssh_stream_wsl};
mod enclave;
mod groups;
mod identities;
mod provisioning;
mod ssh_access;
mod terminal;
mod transfer_cache;
mod transfer_progress;

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
    operation_id: Option<String>,
    instance: Option<String>,
    target: TargetInput,
    profile_id: Option<String>,
    credential_id: Option<String>,
    username: Option<String>,
}

#[derive(Deserialize)]
#[serde(rename_all = "snake_case")]
enum TerminalLauncher {
    Wsl,
    WindowsTerminal,
    PowerShell,
    CommandPrompt,
    MacTerminal,
    LinuxTerminal,
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
    destination_profile_id: Option<String>,
    destination_credential_id: Option<String>,
    destination_username: Option<String>,
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
    architecture: String,
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
    destination_user: String,
    image_architecture: Option<String>,
    destination_architecture: String,
}

fn offline_source_check(image: Option<&str>) -> Result<String, String> {
    let base = "set -Eeuo pipefail; export PATH=\"$HOME/.local/bin:$PATH\"; for tool in orcan tar; do command -v \"$tool\" >/dev/null || { echo \"Source needs $tool\" >&2; exit 1; }; done; orcan version >/dev/null;";
    match image {
        Some(image) if valid_image_reference(image) => Ok(format!(
            "{base} docker image inspect --format '{{{{.Architecture}}}}' {}",
            shell_quote(image)
        )),
        Some(_) => Err("invalid Docker image reference".to_owned()),
        None => Ok(format!("{base} printf none")),
    }
}

fn offline_destination_check(image: bool) -> String {
    let docker = if image { "docker info >/dev/null;" } else { "" };
    format!(
        "set -Eeuo pipefail; for tool in bash tar python3; do command -v \"$tool\" >/dev/null || {{ echo \"Destination needs $tool\" >&2; exit 1; }}; done; test -w \"$HOME\" || {{ echo 'Destination home is not writable' >&2; exit 1; }}; {docker} printf '%s\\t%s' \"$(id -un)\" \"$(uname -m)\""
    )
}

fn offline_check_result(
    input: WslCliProvision,
    source: String,
    destination: String,
) -> Result<CliProvisionCheck, String> {
    let (user, architecture) = destination
        .trim()
        .split_once('\t')
        .ok_or("Destination did not report its user and architecture")?;
    let architecture = match architecture {
        "x86_64" => "amd64",
        "aarch64" => "arm64",
        other => other,
    }
    .to_owned();
    let image_architecture = input.image.as_ref().map(|_| source.trim().to_owned());
    if let Some(image_arch) = &image_architecture {
        if image_arch != &architecture {
            return Err(format!(
                "Image architecture {image_arch} does not match destination {architecture}. Choose or build an image for {architecture}."
            ));
        }
    }
    Ok(CliProvisionCheck {
        source: input.distribution,
        destination: input.destination,
        image: input.image,
        destination_user: user.to_owned(),
        image_architecture,
        destination_architecture: architecture,
    })
}

#[cfg(test)]
mod provisioning_tests {
    use super::*;

    fn input(image: Option<&str>) -> WslCliProvision {
        WslCliProvision {
            distribution: "Ubuntu".into(),
            destination: "server".into(),
            destination_profile_id: None,
            destination_credential_id: None,
            destination_username: None,
            image: image.map(str::to_owned),
        }
    }

    #[test]
    fn image_requires_matching_destination_architecture() {
        assert!(
            offline_check_result(
                input(Some("orcan:latest")),
                "amd64".into(),
                "alice\tx86_64".into()
            )
            .is_ok()
        );
        assert!(
            offline_check_result(
                input(Some("orcan:latest")),
                "amd64".into(),
                "alice\taarch64".into()
            )
            .err()
            .unwrap()
            .contains("does not match")
        );
    }

    #[test]
    fn cli_without_image_accepts_other_architectures() {
        let check =
            offline_check_result(input(None), "none".into(), "alice\taarch64".into()).unwrap();
        assert_eq!(check.destination_user, "alice");
        assert_eq!(check.destination_architecture, "arm64");
        assert!(check.image_architecture.is_none());
    }

    #[test]
    fn system_ssh_trust_uses_resolved_host_port_alias_and_file() {
        let result = parse_host_trust_config("hostname 192.0.2.1\nport 2222\nhostkeyalias private-server\nuserknownhostsfile \"C:/Users/Test User/.ssh/known_hosts\" /other/file\n").unwrap();
        assert_eq!(
            result,
            (
                "192.0.2.1".into(),
                2222,
                "private-server".into(),
                Some("C:/Users/Test User/.ssh/known_hosts".into())
            )
        );
        assert!(parse_host_trust_config("port 22\n").is_err());
        assert!(parse_host_trust_config("hostname server\nport invalid\n").is_err());
    }
}

#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
struct OnlineProvisionCheck {
    user: String,
    installed_version: Option<String>,
}

#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
struct DockerReadiness {
    available: bool,
    version: Option<String>,
    detail: String,
}

#[derive(Serialize)]
#[serde(rename_all = "snake_case")]
enum HostKeyStatus {
    Trusted,
    Unknown,
    Changed,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct HostKeyOffer {
    destination: String,
    algorithm: String,
    fingerprint: String,
    status: HostKeyStatus,
}

const ONLINE_INSTALL_SCRIPT: &str = "set -Eeuo pipefail; command -v curl >/dev/null || { echo 'curl is required for online installation' >&2; exit 127; }; curl -fsSL https://raw.githubusercontent.com/aKyther/orcan/main/install.sh | bash; export PATH=\"$HOME/.local/bin:$PATH\"; orcan version";
const ONLINE_PROVISION_CHECK_SCRIPT: &str = "set -Eeuo pipefail; for tool in bash curl git python3; do command -v \"$tool\" >/dev/null || { echo \"$tool is required for online installation\" >&2; exit 127; }; done; curl -fsSI --connect-timeout 5 --max-time 15 https://raw.githubusercontent.com/aKyther/orcan/main/install.sh >/dev/null || { echo 'official Orcan installer is unreachable' >&2; exit 69; }; version=$(export PATH=\"$HOME/.local/bin:$PATH\"; if command -v orcan >/dev/null; then orcan version 2>/dev/null | head -n 1; else printf '%s' not-installed; fi); user=\"${USER:-${USERNAME:-unknown}}\"; printf '%s\\t%s\\n' \"$user\" \"$version\"";

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

/// Studio owns the output of its helper processes. On Windows, suppress their
/// transient console windows so WSL, OpenSSH, and Docker tasks remain native
/// background work instead of visibly interrupting the desktop.
#[cfg(windows)]
fn background_command(program: &str) -> Command {
    let mut command = Command::new(program);
    use std::os::windows::process::CommandExt;

    command.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    command
}

#[cfg(not(windows))]
fn background_command(program: &str) -> Command {
    Command::new(program)
}

#[cfg(windows)]
fn background_tokio_command(program: &str) -> TokioCommand {
    let mut command = TokioCommand::new(program);
    use std::os::windows::process::CommandExt;

    command.as_std_mut().creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    command
}

#[cfg(not(windows))]
fn background_tokio_command(program: &str) -> TokioCommand {
    TokioCommand::new(program)
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
        operation_id: None,
        instance: None,
        target: TargetInput::Ssh {
            destination: input.destination.clone(),
        },
        profile_id: input.destination_profile_id.clone(),
        credential_id: input.destination_credential_id.clone(),
        username: input.destination_username.clone(),
    }
}

fn command_output(mut command: Command, label: &str) -> Result<String, String> {
    let timeout = if ["check", "test", "lookup", "inventory"]
        .iter()
        .any(|word| label.contains(word))
    {
        orcan_studio_core::CHECK_TIMEOUT
    } else {
        orcan_studio_core::COMMAND_TIMEOUT
    };
    let output = orcan_studio_core::capture_command(&mut command, timeout, &Default::default())
        .map_err(|error| format!("{label}: {error}"))?;
    if output.status.success() {
        return Ok(String::from_utf8_lossy(&output.stdout).trim().to_owned());
    }
    let detail = String::from_utf8_lossy(&output.stderr).trim().to_owned();
    Err(format!("{label} failed: {detail}"))
}

fn parse_online_provision_check(output: String) -> Result<OnlineProvisionCheck, String> {
    let (user, version) = output
        .trim()
        .split_once('\t')
        .ok_or_else(|| "online provisioning check returned an incomplete result".to_owned())?;
    if user.is_empty() {
        return Err("online provisioning check did not report a user".to_owned());
    }
    Ok(OnlineProvisionCheck {
        user: user.to_owned(),
        installed_version: (version != "not-installed" && !version.is_empty())
            .then(|| version.to_owned()),
    })
}

fn docker_readiness(result: Result<String, String>) -> DockerReadiness {
    match result {
        Ok(version) if !version.trim().is_empty() => DockerReadiness {
            available: true,
            version: Some(version.trim().to_owned()),
            detail: "Docker daemon is ready".to_owned(),
        },
        Ok(_) => DockerReadiness {
            available: false,
            version: None,
            detail: "Docker did not report a server version".to_owned(),
        },
        Err(error) => DockerReadiness {
            available: false,
            version: None,
            detail: error,
        },
    }
}

fn wsl_image_inventory(input: &WslImageInput) -> Result<ImageInventory, String> {
    validate_wsl_distribution(&input.distribution)?;
    if !valid_image_reference(&input.image) {
        return Err("invalid Docker image reference".to_owned());
    }
    let output = orcan_studio_core::capture_command(
        background_command("wsl.exe").args([
            "--distribution",
            &input.distribution,
            "--exec",
            "docker",
            "image",
            "inspect",
            "--format",
            "{{.Id}}\t{{.Size}}\t{{.Architecture}}",
            &input.image,
        ]),
        orcan_studio_core::CHECK_TIMEOUT,
        &Default::default(),
    )
    .map_err(|error| format!("could not start WSL Docker: {error}"))?;
    if !output.status.success() {
        return Err(String::from_utf8_lossy(&output.stderr).trim().to_owned());
    }
    let output_text = String::from_utf8_lossy(&output.stdout);
    let mut fields = output_text.trim().split('\t');
    let id = fields.next().unwrap_or_default();
    let size = fields.next().unwrap_or_default();
    let architecture = fields.next().unwrap_or_default();
    if id.is_empty() || size.is_empty() || architecture.is_empty() {
        return Err("WSL Docker returned an incomplete image inventory".to_owned());
    }
    Ok(ImageInventory {
        image: input.image.clone(),
        id: id.to_owned(),
        size: size.to_owned(),
        architecture: architecture.to_owned(),
    })
}

async fn provisioning_ssh_command(
    enclave: EnclaveInput,
    command: String,
    state: &tauri::State<'_, ProfileState>,
) -> Result<String, String> {
    let target = Target::from(enclave.target.clone());
    if !matches!(target, Target::Ssh { .. }) {
        return provisioning::execute(&enclave, &command, state).await;
    }
    let Target::Ssh { destination } = &target else {
        unreachable!()
    };
    target.probe_request().map_err(|error| error.to_string())?;
    if let Some(resolved) = native_ssh(&enclave, &target, state)? {
        return native_ssh_exec(destination, resolved, &command).await;
    }
    let destination = destination.clone();
    tauri::async_runtime::spawn_blocking(move || {
        command_output(
            {
                let mut process = background_command("ssh");
                process
                    .args(["-o", "BatchMode=yes", "--", &destination])
                    .arg(command);
                process
            },
            "remote provisioning check",
        )
    })
    .await
    .map_err(|error| error.to_string())?
}

#[tauri::command]
async fn check_image_destination(
    enclave: EnclaveInput,
    architecture: String,
    state: tauri::State<'_, ProfileState>,
) -> Result<String, String> {
    let output = provisioning_ssh_command(
        enclave,
        "docker info >/dev/null && uname -m".to_owned(),
        &state,
    )
    .await?;
    let remote = match output.trim() {
        "x86_64" => "amd64",
        "aarch64" => "arm64",
        other => other,
    };
    if remote != architecture {
        return Err(format!(
            "Image architecture {architecture} does not match destination {remote}. Choose an image for {remote}."
        ));
    }
    Ok(remote.to_owned())
}

#[tauri::command]
async fn verify_provision(
    enclave: EnclaveInput,
    image: Option<String>,
    expected_id: Option<String>,
    cli: bool,
    state: tauri::State<'_, ProfileState>,
) -> Result<String, String> {
    let version = if cli {
        Some(run_on_enclave(enclave.clone(), vec!["version".to_owned()], state.clone()).await?)
    } else {
        None
    };
    if let Some(image) = image {
        if !valid_image_reference(&image) {
            return Err("invalid Docker image reference".to_owned());
        }
        let id = provisioning_ssh_command(
            enclave,
            format!(
                "docker image inspect --format '{{{{.Id}}}}' {}",
                shell_quote(&image)
            ),
            &state,
        )
        .await?;
        if expected_id.is_some_and(|expected| expected != id.trim()) {
            return Err("Destination image differs from the exported image".to_owned());
        }
        return Ok(format!(
            "{}Image {image} verified on destination.",
            version
                .map(|v| format!("{} · ", v.trim()))
                .unwrap_or_default()
        ));
    }
    Ok(format!(
        "{} verified on destination.",
        version.unwrap_or_default().trim()
    ))
}

#[tauri::command]
async fn wsl_image_inventory_command(input: WslImageInput) -> Result<ImageInventory, String> {
    tauri::async_runtime::spawn_blocking(move || wsl_image_inventory(&input))
        .await
        .map_err(|error| format!("image inventory stopped: {error}"))?
}

/// Streams a Docker image from a local WSL distribution to an SSH target.
/// The image is never buffered or written by Studio.
#[tauri::command]
async fn transfer_wsl_image(
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
        let mut source = background_command("wsl.exe")
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
        let mut target = background_command("ssh")
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
            "set -Eeuo pipefail; kit=$(mktemp -d); trap 'rm -rf \"$kit\"' EXIT; orcan bundle create --output \"$kit/bundle\"{image_arg} >&2; tar -C \"$kit/bundle\" -czf - ."
        );
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
            "set -Eeuo pipefail; kit=$(mktemp -d); trap 'rm -rf \"$kit\"' EXIT; orcan bundle create --output \"$kit/bundle\"{image_arg} >&2; tar -C \"$kit/bundle\" -czf - ."
        );
        let remote_script = "set -Eeuo pipefail; kit=$(mktemp -d); trap 'rm -rf \"$kit\"' EXIT; tar -xzf - -C \"$kit\"; \"$kit/install-orcan-cli.sh\"; export PATH=\"$HOME/.local/bin:$PATH\"; orcan version";
        let remote_command = format!("bash -lc {}", shell_quote(remote_script));

        let mut source = background_command("wsl.exe")
            .args(["--distribution", &input.distribution, "--exec", "bash", "-lc"])
            .arg(source_script)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|error| format!("could not create a WSL CLI kit: {error}"))?;
        let mut target = background_command("ssh")
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
async fn check_online_provision(
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
    mut args: Vec<String>,
    state: tauri::State<'_, ProfileState>,
) -> Result<String, String> {
    let control = commands::OperationControl::register(enclave.operation_id.clone())?;
    let timeout = if args.first().is_some_and(|arg| arg == "studio")
        && args.get(1).is_some_and(|arg| arg == "probe")
    {
        orcan_studio_core::CHECK_TIMEOUT
    } else {
        orcan_studio_core::COMMAND_TIMEOUT
    };
    if let Some(instance) = &enclave.instance {
        enclave::validate_instance(instance)?;
        args.splice(0..0, ["--instance".to_owned(), instance.clone()]);
    }
    let target = Target::from(enclave.target.clone());
    if let (Some(resolved), Target::Ssh { destination }) =
        (native_ssh(&enclave, &target, &state)?, &target)
    {
        return ssh::native_ssh_exec_controlled(
            destination,
            resolved,
            &remote_orcan_command(&args),
            timeout,
            control.cancelled.clone(),
        )
        .await;
    }
    tauri::async_runtime::spawn_blocking(move || {
        target.run_orcan(
            &orcan_studio_core::ControlledRunner {
                timeout,
                cancelled: control.cancelled.clone(),
            },
            &args,
        )
    })
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

/// Verifies only the saved transport. A profile can be valid before Orcan is
/// installed, so this deliberately does not call the Studio protocol.
#[tauri::command]
async fn test_connection(
    enclave: EnclaveInput,
    state: tauri::State<'_, ProfileState>,
) -> Result<String, String> {
    let target = Target::from(enclave.target.clone());
    if let (Some(resolved), Target::Ssh { destination }) =
        (native_ssh(&enclave, &target, &state)?, &target)
    {
        return native_ssh_exec(destination, resolved, "id -un")
            .await
            .map(|user| user.trim().to_owned());
    }
    tauri::async_runtime::spawn_blocking(move || match target {
        Target::Local => Ok(current_user()),
        Target::Wsl2 { distribution } => {
            validate_wsl_distribution(&distribution)?;
            command_output(
                {
                    let mut command = background_command("wsl.exe");
                    command.args(["--distribution", &distribution, "--exec", "id", "-un"]);
                    command
                },
                "WSL connection test",
            )
        }
        Target::Ssh { destination } => command_output(
            {
                let mut command = background_command("ssh");
                command
                    .args(["-o", "BatchMode=yes", "--", &destination])
                    .arg("id -un");
                command
            },
            "SSH connection test",
        ),
    })
    .await
    .map_err(|error| format!("connection test stopped: {error}"))?
    .map(|user| user.trim().to_owned())
}

/// Asks the selected host's Docker client for a daemon version without
/// changing Docker state. An unavailable daemon is a readiness result, not a
/// transport failure: Studio can then guide the user before Enclave creation.
#[tauri::command]
async fn check_docker(
    enclave: EnclaveInput,
    state: tauri::State<'_, ProfileState>,
) -> Result<DockerReadiness, String> {
    let target = Target::from(enclave.target.clone());
    if let (Some(resolved), Target::Ssh { destination }) =
        (native_ssh(&enclave, &target, &state)?, &target)
    {
        return Ok(docker_readiness(
            native_ssh_exec(
                destination,
                resolved,
                "docker version --format '{{.Server.Version}}'",
            )
            .await,
        ));
    }
    tauri::async_runtime::spawn_blocking(move || {
        let result = match target {
            Target::Local => command_output(
                {
                    let mut command = background_command("docker");
                    command.args(["version", "--format", "{{.Server.Version}}"]);
                    command
                },
                "local Docker check",
            ),
            Target::Wsl2 { distribution } => {
                validate_wsl_distribution(&distribution)?;
                command_output(
                    {
                        let mut command = background_command("wsl.exe");
                        command.args([
                            "--distribution",
                            &distribution,
                            "--exec",
                            "docker",
                            "version",
                            "--format",
                            "{{.Server.Version}}",
                        ]);
                        command
                    },
                    "WSL Docker check",
                )
            }
            Target::Ssh { destination } => command_output(
                {
                    let mut command = background_command("ssh");
                    command
                        .args(["-o", "BatchMode=yes", "--", &destination])
                        .arg("docker version --format '{{.Server.Version}}'");
                    command
                },
                "remote Docker check",
            ),
        };
        Ok(docker_readiness(result))
    })
    .await
    .map_err(|error| format!("Docker check stopped: {error}"))?
}

/// Lists distributions that the Windows WSL launcher exposes to Studio.
#[tauri::command]
async fn list_wsl_distributions() -> Result<Vec<String>, String> {
    tauri::async_runtime::spawn_blocking(|| {
        let output = orcan_studio_core::capture_command(
            background_command("wsl.exe").args(["--list", "--quiet"]),
            orcan_studio_core::CHECK_TIMEOUT,
            &Default::default(),
        )
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
                let mut command = background_command("wsl.exe");
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
    ttyd_host_port: Option<u16>,
    cpus: Option<f64>,
    memory_gb: Option<u32>,
    image: Option<String>,
    projects_root: Option<String>,
    identity_id: Option<String>,
    identity_version: Option<u32>,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    let mut report = probe(enclave.clone(), state.clone()).await?;
    if image.is_some() || projects_root.is_some() {
        let (images, roots) = enclave::creation_choices(&enclave, &report, &state).await?;
        if let Some(image) = &image {
            if !images.contains(image) {
                return Err(
                    "Select an available Orcan image from a fresh destination check.".into(),
                );
            }
            report.runtime.docker.image.name = image.clone();
            report.runtime.docker.image.present = true;
        }
        if let Some(root) = &projects_root {
            if !roots.contains(root) {
                return Err("Select a project root reported by Orcan on this host.".into());
            }
        }
    }
    let identity = match (identity_id, identity_version) {
        (Some(id), Some(version)) => {
            if !report.capabilities.identity_templates {
                return Err("Update the host Orcan CLI before using identity templates".into());
            }
            let identity = identities::read_at(&identities::root()?, &id, version)?;
            let label = provisioning::execute(&enclave, &format!("docker image inspect --format '{{{{index .Config.Labels \"io.orcan.identity.version\"}}}}' {}", shell_quote(&report.runtime.docker.image.name)), &state).await?;
            if label.trim() != "1" {
                return Err("This image cannot preserve identity instructions. Select an updated Orcan image.".into());
            }
            Some(identity)
        }
        (None, None) => None,
        _ => return Err("Select an identity and its exact version".into()),
    };
    if let Some(reason) = enclave::creation_blocker(&report) {
        return Err(reason);
    }
    if enclave.instance.is_some()
        && (with_ttyd || ttyd_credential.is_some())
        && ttyd_host_port.is_none()
    {
        return Err("Choose a browser-terminal host port for this named container".into());
    }
    if let Some(port) = ttyd_host_port {
        let ports =
            provisioning::execute(&enclave, "docker ps --format '{{.Ports}}'", &state).await?;
        if ports.contains(&format!(":{port}->")) {
            return Err(format!(
                "Host port {port} is already published by a running container. Choose another port."
            ));
        }
    }
    let mut args = vec![
        "studio".to_owned(),
        "enclave".to_owned(),
        if apply { "apply" } else { "plan" }.to_owned(),
        "--empty".to_owned(),
    ];
    if let Some(identity) = identity {
        args.extend([
            "--identity-json".into(),
            serde_json::to_string(&identity).map_err(|e| e.to_string())?,
        ]);
    }
    if let Some(image) = image {
        args.extend(["--image".into(), image]);
    }
    if let Some(root) = projects_root {
        args.extend(["--projects-root".into(), root]);
    }
    if with_git {
        // Access options are independent of the selected runtime name.
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
    if let Some(port) = ttyd_host_port {
        if port < 1024 {
            return Err("Browser-terminal host port must be 1024–65535".into());
        }
        args.extend(["--ttyd-host-port".into(), port.to_string()]);
    }
    if let Some(cpus) = cpus {
        if !cpus.is_finite() || cpus <= 0.0 || cpus > 1024.0 {
            return Err("CPU limit must be greater than zero and at most 1024".into());
        }
        args.extend(["--cpus".into(), cpus.to_string()]);
    }
    if let Some(memory) = memory_gb {
        if memory == 0 || memory > 65536 {
            return Err("RAM must be 1–65536 GiB".into());
        }
        args.extend(["--memory-gb".into(), memory.to_string()]);
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
    let report = probe(enclave.clone(), state.clone()).await?;
    enclave::verify_container_owner(&enclave, &report, &state).await?;
    match enclave::lifecycle_command(&report, action)? {
        Some(command) => provisioning::execute(&enclave, &command, &state)
            .await
            .map(|_| ()),
        None => run_on_enclave(enclave, runtime_args(action), state)
            .await
            .map(|_| ()),
    }
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
struct ProfileState(Mutex<ProfileStore>);

#[tauri::command]
async fn open_terminal(
    enclave: EnclaveInput,
    workspace: String,
    launcher: TerminalLauncher,
    host_id: Option<String>,
    container_id: Option<String>,
    state: tauri::State<'_, ProfileState>,
) -> Result<(), String> {
    terminal::open(enclave, workspace, launcher, host_id, container_id, state).await
}

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            let data_dir = app.path().app_data_dir()?;
            let cache =
                transfer_cache::TransferCache::new(app.path().app_cache_dir()?.join("transfers"))?;
            let cleanup_cache = cache.clone();
            tauri::async_runtime::spawn_blocking(move || {
                if let Err(error) = cleanup_cache.cleanup() {
                    eprintln!("Could not clean orphaned Studio transfers: {error}");
                }
            });
            app.manage(cache);
            app.manage(provisioning::PendingTransfers::default());
            app.manage(ProfileState(Mutex::new(ProfileStore::new(
                data_dir.join("profiles.json"),
            ))));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::cancel_operation,
            identities::list_identities,
            identities::save_identity,
            identities::open_studio_data,
            ssh_access::git_ssh_keys,
            ssh_access::transfer_git_ssh_key,
            ssh_access::test_git_ssh,
            ssh_access::git_ssh_host_identity,
            ssh_access::trust_git_ssh_host,
            provisioning::check_transfer,
            provisioning::transfer_profiles,
            provisioning::has_pending_transfer,
            provisioning::resume_transfer,
            provisioning::discard_transfer,
            provisioning::profile_image_inventory,
            provisioning::remove_destination_image,
            cleanup::server_cleanup_inventory,
            cleanup::remove_server_cli,
            list_wsl_distributions,
            wsl_default_user,
            wsl_image_inventory_command,
            transfer_wsl_image,
            check_image_destination,
            verify_provision,
            check_wsl_cli_provision,
            provision_wsl_cli,
            check_online_provision,
            provision_online,
            ssh::ssh_host_key,
            ssh::trust_ssh_host_key,
            probe,
            test_connection,
            check_docker,
            enclave_action,
            enclave::enclave_readiness,
            enclave::list_instances,
            enclave::server_capacity,
            sync,
            runtime_action,
            open_terminal,
            groups::list_groups,
            groups::save_group,
            groups::register_target,
            groups::group_probe,
            groups::group_start,
            groups::replace_container,
            current_user,
            profiles::list_profiles,
            profiles::save_profile,
            profiles::delete_profile,
            profiles::save_secret,
            profiles::list_credentials,
            profiles::create_credential,
            profiles::delete_credential,
            context::parent_plan,
            context::parent_apply,
            context::import_plan,
            context::import_apply,
            context::directory_plan,
            context::directory_apply,
            context::worktree_branches,
            context::worktree_cleanup,
            context::worktree_plan,
            context::worktree_inventory,
            context::worktree_apply,
            membership_action,
            workspace_action
        ])
        .run(tauri::generate_context!())
        .expect("error while running Orcan Studio");
}
