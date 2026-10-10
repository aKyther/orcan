//! Native SSH authentication, server trust and command streaming.
use super::profiles::vault_entry;
use super::{
    HostKeyOffer, HostKeyStatus, background_command, background_tokio_command, command_output,
};
use orcan_studio_core::{ResolvedSsh, SshAuthentication, Target};
use russh::keys::PublicKeyOrCertificate;
use russh::{ChannelMsg, client, keys};
use std::process::Stdio;
use std::sync::{Arc, Mutex};

pub(super) struct KnownHostsHandler {
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
pub(super) async fn ssh_host_key(
    destination: String,
    system_ssh: Option<bool>,
) -> Result<HostKeyOffer, String> {
    observed_ssh_host_key(&destination, system_ssh.unwrap_or(false))
        .await
        .map(|(offer, _)| offer)
}

#[tauri::command]
pub(super) async fn trust_ssh_host_key(
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

pub(super) fn parse_host_trust_config(
    config: &str,
) -> Result<(String, u16, String, Option<String>), String> {
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

pub(super) async fn native_ssh_connect(
    destination: &str,
    resolved: ResolvedSsh,
) -> Result<client::Handle<KnownHostsHandler>, String> {
    tokio::time::timeout(
        std::time::Duration::from_secs(45),
        native_ssh_connect_inner(destination, resolved),
    )
    .await
    .map_err(|_| "SSH connection timed out. Check the server, VPN and credentials.".to_owned())?
}

async fn native_ssh_connect_inner(
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
pub(super) async fn native_ssh_exec(
    destination: &str,
    resolved: ResolvedSsh,
    command: &str,
) -> Result<String, String> {
    native_ssh_exec_controlled(
        destination,
        resolved,
        command,
        orcan_studio_core::COMMAND_TIMEOUT,
        Default::default(),
    )
    .await
}

pub(super) async fn native_ssh_exec_controlled(
    destination: &str,
    resolved: ResolvedSsh,
    command: &str,
    timeout: std::time::Duration,
    cancelled: std::sync::Arc<std::sync::atomic::AtomicBool>,
) -> Result<String, String> {
    let cancelled_wait = async {
        loop {
            if cancelled.load(std::sync::atomic::Ordering::Relaxed) {
                break;
            }
            tokio::time::sleep(std::time::Duration::from_millis(20)).await;
        }
    };
    tokio::select! {
        result = tokio::time::timeout(timeout, native_ssh_exec_inner(destination, resolved, command)) =>
            result.map_err(|_| "SSH command timed out; remote changes are not rolled back. Refresh before retrying.".to_owned())?,
        _ = cancelled_wait => Err("SSH command cancelled; remote changes are not rolled back. Refresh before retrying.".to_owned()),
    }
}

async fn native_ssh_exec_inner(
    destination: &str,
    resolved: ResolvedSsh,
    command: &str,
) -> Result<String, String> {
    let session = native_ssh_connect(destination, resolved).await?;

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
            ChannelMsg::Data { data } => super::execution::append_response(&mut stdout, &data)?,
            ChannelMsg::ExtendedData { data, .. } => {
                super::execution::append_response(&mut stderr, &data)?
            }
            ChannelMsg::ExitStatus {
                exit_status: status,
            } => exit_status = Some(status),
            _ => {}
        }
    }
    if exit_status.unwrap_or(1) != 0 {
        let detail = if stderr.is_empty() { &stdout } else { &stderr };
        return Err(format!(
            "`{command}` failed on the Enclave: {}",
            String::from_utf8_lossy(detail).trim()
        ));
    }
    Ok(String::from_utf8_lossy(&stdout).into_owned())
}

pub(super) async fn native_ssh_stream_wsl(
    distribution: &str,
    destination: &str,
    resolved: ResolvedSsh,
    source_script: String,
    remote_command: String,
    operation: &str,
) -> Result<String, String> {
    let activity = super::execution::Activity::new();
    activity
        .guard(
            std::time::Duration::from_secs(300),
            native_ssh_stream_wsl_inner(
                distribution,
                destination,
                resolved,
                source_script,
                remote_command,
                operation,
                &activity,
            ),
        )
        .await
}

async fn native_ssh_stream_wsl_inner(
    distribution: &str,
    destination: &str,
    resolved: ResolvedSsh,
    source_script: String,
    remote_command: String,
    operation: &str,
    activity: &super::execution::Activity,
) -> Result<String, String> {
    let mut command = background_tokio_command("wsl.exe");
    command
        .args(["--distribution", distribution, "--exec", "bash", "-lc"])
        .arg(source_script)
        .kill_on_drop(true)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(unix)]
    command.process_group(0);
    let mut source = command
        .spawn()
        .map_err(|error| format!("could not start WSL export for {operation}: {error}"))?;
    let mut tree = super::execution::ProcessTree(source.id());
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
    let diagnostics = source.stderr.take().ok_or("WSL export has no stderr")?;
    let send = async {
        channel
            .data(super::transfer_progress::ProgressReader::new(
                source_stdout,
                |_| activity.touch(),
            ))
            .await
            .map_err(|error| format!("{operation} interrupted: {error}"))?;
        channel
            .eof()
            .await
            .map_err(|error| format!("could not finish {operation}: {error}"))
    };
    let (_, status, diagnostics) = tokio::try_join!(
        send,
        async { source.wait().await.map_err(|e| e.to_string()) },
        super::execution::read_response(diagnostics)
    )?;
    tree.0 = None;
    if !status.success() {
        return Err(format!(
            "WSL export for {operation} failed: {}",
            String::from_utf8_lossy(&diagnostics).trim()
        ));
    }
    let mut stdout = Vec::new();
    let mut stderr = Vec::new();
    let mut exit_status = None;
    while let Some(message) = channel.wait().await {
        activity.touch();
        match message {
            ChannelMsg::Data { data } => super::execution::append_response(&mut stdout, &data)?,
            ChannelMsg::ExtendedData { data, .. } => {
                super::execution::append_response(&mut stderr, &data)?
            }
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
