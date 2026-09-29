use orcan_studio_core::{
    ConnectionProfile, MembershipAction, ProbeReport, ProfileStore, ResolvedSsh, RuntimeAction,
    SshAuthentication, SshCredential, SystemRunner, Target, membership_args, parse_probe_report,
    remote_orcan_command, runtime_args, sync_args,
};
use russh::ChannelMsg;
use russh::client;
use russh::keys::{self, PublicKeyOrCertificate};
use serde::Deserialize;
use std::process::Command;
use std::sync::Arc;
use std::sync::Mutex;
use tauri::Manager;

#[derive(Clone, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
enum TargetInput {
    Local,
    Wsl2 { distribution: String },
    Ssh { destination: String },
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
#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct EnclaveInput {
    target: TargetInput,
    profile_id: Option<String>,
    credential_id: Option<String>,
    username: Option<String>,
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

#[tauri::command]
async fn sync(enclave: EnclaveInput, state: tauri::State<'_, ProfileState>) -> Result<(), String> {
    run_on_enclave(enclave, sync_args(), state)
        .await
        .map(|_| ())
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
    apply: bool,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    let args =
        membership_args(action, &workspace, &project, apply).map_err(|error| error.to_string())?;
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
    destination: Option<String>,
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
    if let Some(destination) = destination.filter(|value| !value.trim().is_empty()) {
        args.extend(["--destination".to_owned(), destination]);
    }
    studio_json(enclave, args, state).await
}

#[tauri::command]
async fn import_apply(
    enclave: EnclaveInput,
    source: String,
    projects_root: String,
    destination: Option<String>,
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
    if let Some(destination) = destination.filter(|value| !value.trim().is_empty()) {
        args.extend(["--destination".to_owned(), destination]);
    }
    studio_json(enclave, args, state).await
}

#[tauri::command]
async fn worktree_cleanup(
    enclave: EnclaveInput,
    path: String,
    worktrees_root: String,
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
            probe,
            sync,
            runtime_action,
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
            worktree_cleanup,
            worktree_plan,
            worktree_apply,
            membership_action
        ])
        .run(tauri::generate_context!())
        .expect("error while running Orcan Studio");
}
