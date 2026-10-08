#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use orcan_studio_core::{
    ConnectionProfile, MembershipAction, ProbeReport, ProfileStore, ProjectMode, ResolvedSsh,
    RuntimeAction, SshAuthentication, SshCredential, SystemRunner, Target, membership_args,
    parse_probe_report, remote_orcan_command, runtime_args, sync_args,
};
use russh::ChannelMsg;
use russh::client;
use russh::keys::{self, PublicKeyOrCertificate};
use serde::{Deserialize, Serialize};
use std::io;
use std::process::{Command, Stdio};
use std::sync::Arc;
use std::sync::Mutex;
use tauri::Manager;
use tokio::process::Command as TokioCommand;

mod provisioning;
mod transfer_cache;

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
#[serde(rename_all = "snake_case")]
enum TerminalLauncher {
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
    let output = background_command("wsl.exe")
        .args([
            "--distribution",
            &input.distribution,
            "--exec",
            "docker",
            "image",
            "inspect",
            "--format",
            "{{.Id}}\t{{.Size}}\t{{.Architecture}}",
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
        let output = background_command("wsl.exe")
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

/// Captures a server key during SSH handshake but never accepts it. The UI
/// displays the exact fingerprint and requires a deliberate user decision.
struct HostKeyCaptureHandler {
    observed: Arc<Mutex<Option<keys::PublicKey>>>,
}

impl client::Handler for HostKeyCaptureHandler {
    type Error = russh::Error;

    async fn check_server_key(
        &mut self,
        server_public_key: &PublicKeyOrCertificate,
    ) -> Result<bool, Self::Error> {
        if let Ok(mut observed) = self.observed.lock() {
            *observed = Some(server_public_key.public_key().clone());
        }
        Ok(false)
    }
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
    let destination = destination
        .rsplit_once('@')
        .map(|(_, host)| host)
        .unwrap_or(destination);
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

async fn observed_ssh_host_key(
    destination: &str,
    system_ssh: bool,
) -> Result<(HostKeyOffer, keys::PublicKey), String> {
    let (host, port, key_host, known_hosts) = host_trust_endpoint(destination, system_ssh).await?;
    let observed = Arc::new(Mutex::new(None));
    let handler = HostKeyCaptureHandler {
        observed: Arc::clone(&observed),
    };
    // Rejection is expected: the handler captures the key and stops before
    // authentication or command execution.
    let _ = client::connect(
        Arc::new(client::Config::default()),
        (host.as_str(), port),
        handler,
    )
    .await;
    let public_key = observed
        .lock()
        .map_err(|_| "SSH host-key inspection state is unavailable".to_owned())?
        .clone()
        .ok_or_else(|| "Studio could not read an SSH host key from this destination".to_owned())?;
    let check = match &known_hosts {
        Some(path) => keys::known_hosts::check_known_hosts_path(&key_host, port, &public_key, path),
        None => keys::known_hosts::check_known_hosts(&key_host, port, &public_key),
    };
    let status = match check {
        Ok(true) => HostKeyStatus::Trusted,
        Ok(false) => HostKeyStatus::Unknown,
        Err(keys::Error::KeyChanged { .. }) => HostKeyStatus::Changed,
        Err(error) => return Err(format!("could not verify SSH host key: {error}")),
    };
    let offer = HostKeyOffer {
        destination: if port == 22 {
            host.clone()
        } else {
            format!("[{host}]:{port}")
        },
        algorithm: format!("{:?}", public_key.algorithm()),
        fingerprint: public_key.fingerprint(Default::default()).to_string(),
        status,
    };
    Ok((offer, public_key))
}

#[tauri::command]
async fn ssh_host_key(
    destination: String,
    system_ssh: Option<bool>,
) -> Result<HostKeyOffer, String> {
    observed_ssh_host_key(&destination, system_ssh.unwrap_or(false))
        .await
        .map(|(offer, _)| offer)
}

#[tauri::command]
async fn trust_ssh_host_key(
    destination: String,
    fingerprint: String,
    system_ssh: Option<bool>,
    replace_changed: Option<bool>,
) -> Result<(), String> {
    let system_ssh = system_ssh.unwrap_or(false);
    let (offer, public_key) = observed_ssh_host_key(&destination, system_ssh).await?;
    let changed = matches!(offer.status, HostKeyStatus::Changed);
    match offer.status {
        HostKeyStatus::Trusted => return Ok(()),
        HostKeyStatus::Changed if !replace_changed.unwrap_or(false) => return Err("The SSH host key differs from the saved key. Approve its replacement in Studio after verifying the fingerprint.".to_owned()),
        HostKeyStatus::Changed => {},
        HostKeyStatus::Unknown => {}
    }
    if offer.fingerprint != fingerprint {
        return Err("The SSH host key changed while awaiting confirmation. Inspect it again before trusting it.".to_owned());
    }
    let (_, port, host, path) = host_trust_endpoint(&destination, system_ssh).await?;
    if changed {
        #[allow(deprecated)]
        let default_path = std::env::home_dir().map(|home| home.join(".ssh").join("known_hosts"));
        let file = path
            .clone()
            .map(std::path::PathBuf::from)
            .or(default_path)
            .ok_or("could not locate known_hosts for identity replacement")?;
        let identity = if port == 22 {
            host.clone()
        } else {
            format!("[{host}]:{port}")
        };
        tauri::async_runtime::spawn_blocking(move || {
            command_output(
                {
                    let mut command = background_command("ssh-keygen");
                    command.args(["-R", &identity, "-f"]).arg(file);
                    command
                },
                "saved server identity replacement",
            )
        })
        .await
        .map_err(|error| error.to_string())??;
    }
    match path {
        Some(path) => keys::known_hosts::learn_known_hosts_path(&host, port, &public_key, path),
        None => keys::known_hosts::learn_known_hosts(&host, port, &public_key),
    }
    .map_err(|error| format!("could not save SSH host key: {error}"))
}

/// OpenSSH resolves aliases and custom known-hosts locations without signing in.
async fn host_trust_endpoint(
    destination: &str,
    system_ssh: bool,
) -> Result<(String, u16, String, Option<String>), String> {
    if !system_ssh {
        let (host, port) = ssh_endpoint(destination)?;
        return Ok((host.clone(), port, host, None));
    }
    Target::Ssh {
        destination: destination.to_owned(),
    }
    .probe_request()
    .map_err(|error| error.to_string())?;
    let destination = destination.to_owned();
    let config = tauri::async_runtime::spawn_blocking(move || {
        command_output(
            {
                let mut command = background_command("ssh");
                command.args(["-G", "--", &destination]);
                command
            },
            "SSH configuration lookup",
        )
    })
    .await
    .map_err(|error| error.to_string())??;
    parse_host_trust_config(&config)
}

fn parse_host_trust_config(config: &str) -> Result<(String, u16, String, Option<String>), String> {
    let value = |name: &str| {
        config
            .lines()
            .find_map(|line| line.strip_prefix(name))
            .map(str::trim)
    };
    let host = value("hostname ")
        .ok_or("SSH configuration did not report a hostname")?
        .to_owned();
    let port = value("port ")
        .unwrap_or("22")
        .parse()
        .map_err(|_| "SSH configuration reported an invalid port")?;
    let key_host = value("hostkeyalias ")
        .filter(|alias| *alias != "none")
        .unwrap_or(&host)
        .to_owned();
    let path = value("userknownhostsfile ")
        .and_then(|paths| {
            if let Some(quoted) = paths.strip_prefix('"') {
                quoted.split('"').next()
            } else {
                paths.split_whitespace().next()
            }
        })
        .filter(|path| *path != "none")
        .map(str::to_owned);
    Ok((host, port, key_host, path))
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

async fn native_ssh_stream_wsl(
    distribution: &str,
    destination: &str,
    resolved: ResolvedSsh,
    source_script: String,
    remote_command: String,
    operation: &str,
) -> Result<String, String> {
    let mut source = background_tokio_command("wsl.exe")
        .args(["--distribution", distribution, "--exec", "bash", "-lc"])
        .arg(source_script)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| format!("could not start WSL export for {operation}: {error}"))?;
    let source_stdout = source
        .stdout
        .take()
        .ok_or_else(|| format!("WSL export for {operation} has no stdout"))?;
    let session = native_ssh_connect(destination, resolved).await?;
    let mut channel = session
        .channel_open_session()
        .await
        .map_err(|error| format!("could not open SSH channel for {operation}: {error}"))?;
    channel
        .exec(true, remote_command.as_str())
        .await
        .map_err(|error| format!("could not start remote {operation}: {error}"))?;
    channel
        .data(source_stdout)
        .await
        .map_err(|error| format!("{operation} interrupted: {error}"))?;
    channel
        .eof()
        .await
        .map_err(|error| format!("could not finish {operation}: {error}"))?;
    let source_result = source
        .wait_with_output()
        .await
        .map_err(|error| format!("could not finish WSL export for {operation}: {error}"))?;
    if !source_result.status.success() {
        return Err(format!(
            "WSL export for {operation} failed: {}",
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
            "remote {operation} failed: {}",
            String::from_utf8_lossy(&stderr).trim()
        ));
    }
    Ok(String::from_utf8_lossy(&stdout).into_owned())
}

struct ProfileState(Mutex<ProfileStore>);

#[tauri::command]
fn open_terminal(
    enclave: EnclaveInput,
    workspace: String,
    launcher: TerminalLauncher,
    state: tauri::State<'_, ProfileState>,
) -> Result<(), String> {
    let TargetInput::Ssh { .. } = &enclave.target else {
        return Err("native terminal launch currently needs an SSH Enclave profile".to_owned());
    };
    let resolved = state
        .0
        .lock()
        .map_err(|_| "profile store is unavailable".to_owned())?
        .resolve_ssh(
            enclave.profile_id.as_deref(),
            enclave.credential_id.as_deref(),
            enclave.username.as_deref(),
        )
        .map_err(|error| error.to_string())?
        .ok_or_else(|| {
            "save and select a system-SSH profile before opening a terminal".to_owned()
        })?;
    if !matches!(resolved.1.ssh.authentication, SshAuthentication::Agent) {
        return Err("native terminal launch uses system SSH only; Studio never passes a saved password or key to another app".to_owned());
    }
    let profile = resolved
        .0
        .ok_or_else(|| "select a saved SSH profile".to_owned())?;
    let Target::Ssh { destination } = profile.target else {
        return Err("select a saved SSH profile".to_owned());
    };
    Target::Ssh {
        destination: destination.clone(),
    }
    .probe_request()
    .map_err(|error| error.to_string())?;
    if workspace.is_empty()
        || workspace.starts_with('-')
        || workspace
            .chars()
            .any(|c| !c.is_ascii_alphanumeric() && !"._-".contains(c))
    {
        return Err("select a valid workspace name".to_owned());
    }
    let destination = &destination;
    if destination.starts_with('-')
        || !destination
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || "._-@[]:".contains(c))
    {
        return Err(
            "use a hostname, IP address, or SSH Host alias for native terminal access".to_owned(),
        );
    }
    let remote = remote_orcan_command(&["attach".to_owned(), workspace]);
    #[cfg(windows)]
    let mut command = match launcher {
        TerminalLauncher::WindowsTerminal => {
            let mut c = Command::new("wt.exe");
            c.args(["-w", "new", "ssh", "-tt", "--", destination, &remote]);
            c
        }
        TerminalLauncher::PowerShell => {
            use std::os::windows::process::CommandExt;
            let mut c = Command::new("powershell.exe");
            c.creation_flags(0x0000_0010); // CREATE_NEW_CONSOLE
            c.args([
                "-NoExit",
                "-Command",
                &format!(
                    "& ssh -tt -- '{}' '{}'",
                    destination.replace('\'', "''"),
                    remote.replace('\'', "''")
                ),
            ]);
            c
        }
        TerminalLauncher::CommandPrompt => {
            use std::os::windows::process::CommandExt;
            let mut c = Command::new("cmd.exe");
            c.creation_flags(0x0000_0010); // CREATE_NEW_CONSOLE
            c.args([
                "/K",
                "powershell.exe",
                "-NoProfile",
                "-Command",
                &format!(
                    "& ssh -tt -- '{}' '{}'",
                    destination.replace('\'', "''"),
                    remote.replace('\'', "''")
                ),
            ]);
            c
        }
        _ => return Err("choose a Windows terminal on Windows".to_owned()),
    };
    #[cfg(target_os = "macos")]
    let mut command = match launcher {
        TerminalLauncher::MacTerminal => {
            let mut c = Command::new("/usr/bin/osascript");
            let shell = format!(
                "exec ssh -tt -- {} {}",
                shell_quote(destination),
                shell_quote(&remote)
            );
            c.args([
                "-e",
                &format!(
                    "tell application \"Terminal\" to do script {}",
                    serde_json::to_string(&shell).map_err(|error| error.to_string())?
                ),
            ]);
            c
        }
        _ => return Err("choose Terminal on macOS".to_owned()),
    };
    #[cfg(all(unix, not(target_os = "macos")))]
    let mut command = match launcher {
        TerminalLauncher::LinuxTerminal => {
            let mut c = Command::new("x-terminal-emulator");
            c.args(["-e", "ssh", "-tt", "--", destination, &remote]);
            c
        }
        _ => return Err("choose Default Linux terminal on Linux".to_owned()),
    };
    command
        .spawn()
        .map_err(|error| format!("could not open terminal: {error}"))?;
    Ok(())
}

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

/// Creates an immutable credential and, when required, its vault secret.
#[tauri::command]
fn create_credential(
    credential: SshCredential,
    secret: Option<String>,
    state: tauri::State<'_, ProfileState>,
) -> Result<(), String> {
    credential.validate().map_err(|error| error.to_string())?;
    let secret = secret.filter(|secret| !secret.is_empty());
    let vault_secret = match &credential.authentication {
        SshAuthentication::Password if secret.is_some() => Some(("password", secret)),
        SshAuthentication::Password => {
            return Err("a password credential requires a password".to_owned());
        }
        SshAuthentication::PrivateKey {
            has_passphrase: true,
            ..
        } if secret.is_some() => Some(("key-passphrase", secret)),
        SshAuthentication::PrivateKey {
            has_passphrase: true,
            ..
        } => return Err("this private key requires its passphrase".to_owned()),
        SshAuthentication::PrivateKey {
            has_passphrase: false,
            ..
        } if secret.is_none() => None,
        SshAuthentication::PrivateKey {
            has_passphrase: false,
            ..
        } => {
            return Err(
                "mark the key as passphrase-protected before supplying a passphrase".to_owned(),
            );
        }
        SshAuthentication::Agent => {
            return Err("the SSH agent does not create a Studio credential".to_owned());
        }
    };
    state
        .0
        .lock()
        .map_err(|_| "profile store is unavailable".to_owned())?
        .create_credential(credential.clone())
        .map_err(|error| error.to_string())?;
    if let Some((kind, Some(secret))) = vault_secret {
        let stored = vault_entry(&credential.vault_owner(), kind).and_then(|entry| {
            entry
                .set_password(&secret)
                .map_err(|error| error.to_string())
        });
        if let Err(error) = stored {
            let _ = state
                .0
                .lock()
                .map_err(|_| "profile store is unavailable".to_owned())?
                .delete_credential(&credential.id);
            return Err(format!("could not store credential: {error}"));
        }
    }
    Ok(())
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
            let cache =
                transfer_cache::TransferCache::new(app.path().app_cache_dir()?.join("transfers"))?;
            let cleanup_cache = cache.clone();
            tauri::async_runtime::spawn_blocking(move || {
                if let Err(error) = cleanup_cache.cleanup() {
                    eprintln!("Could not clean orphaned Studio transfers: {error}");
                }
            });
            app.manage(cache);
            app.manage(ProfileState(Mutex::new(ProfileStore::new(
                data_dir.join("profiles.json"),
            ))));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            provisioning::check_transfer,
            provisioning::transfer_profiles,
            provisioning::profile_image_inventory,
            provisioning::remove_destination_image,
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
            ssh_host_key,
            trust_ssh_host_key,
            probe,
            test_connection,
            check_docker,
            enclave_action,
            sync,
            runtime_action,
            open_terminal,
            current_user,
            list_profiles,
            save_profile,
            delete_profile,
            save_secret,
            list_credentials,
            create_credential,
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
