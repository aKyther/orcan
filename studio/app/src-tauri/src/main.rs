use orcan_studio_core::{
    ConnectionProfile, ProbeReport, ProfileStore, SshAuthentication, SystemRunner, Target,
    parse_probe_report,
};
use russh::ChannelMsg;
use russh::client;
use russh::keys::{self, PublicKeyOrCertificate};
use serde::Deserialize;
use std::process::Command;
use std::sync::Arc;
use std::sync::Mutex;
use tauri::Manager;

#[derive(Deserialize)]
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

#[tauri::command]
async fn probe(
    target: TargetInput,
    profile_id: Option<String>,
    state: tauri::State<'_, ProfileState>,
) -> Result<ProbeReport, String> {
    let target = Target::from(target);
    if let Some(profile_id) = profile_id {
        let profile = state
            .0
            .lock()
            .map_err(|_| "profile store is unavailable".to_owned())?
            .list()
            .map_err(|error| error.to_string())?
            .into_iter()
            .find(|profile| profile.id == profile_id)
            .ok_or_else(|| "selected profile no longer exists".to_owned())?;
        if profile.target != target {
            return Err("save this connection before using its credentials".to_owned());
        }
        if matches!(
            profile.ssh.authentication,
            SshAuthentication::Password | SshAuthentication::PrivateKey { .. }
        ) {
            return native_ssh_probe(profile).await;
        }
    }
    tauri::async_runtime::spawn_blocking(move || target.probe(&SystemRunner))
        .await
        .map_err(|error| format!("probe task stopped: {error}"))?
        .map_err(|error| error.to_string())
}

#[tauri::command]
async fn sync(target: TargetInput) -> Result<(), String> {
    let target = Target::from(target);
    tauri::async_runtime::spawn_blocking(move || target.sync(&SystemRunner))
        .await
        .map_err(|error| format!("sync task stopped: {error}"))?
        .map_err(|error| error.to_string())
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

fn required_vault_secret(profile_id: &str, kind: &str) -> Result<String, String> {
    vault_entry(profile_id, kind)?
        .get_password()
        .map_err(|_| format!("no {kind} is stored for this profile"))
}

async fn native_ssh_probe(profile: ConnectionProfile) -> Result<ProbeReport, String> {
    let Target::Ssh { destination } = &profile.target else {
        return Err("native SSH requires an SSH profile".to_owned());
    };
    let username = profile
        .ssh
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

    let authenticated = match &profile.ssh.authentication {
        SshAuthentication::Password => {
            let password = required_vault_secret(&profile.id, "password")?;
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
                .then(|| required_vault_secret(&profile.id, "key-passphrase"))
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
        .exec(true, "orcan studio probe --json")
        .await
        .map_err(|error| format!("could not start Orcan probe: {error}"))?;

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
            "remote Orcan probe failed: {}",
            String::from_utf8_lossy(&stderr).trim()
        ));
    }
    parse_probe_report(&String::from_utf8_lossy(&stdout)).map_err(|error| error.to_string())
}

struct ProfileState(Mutex<ProfileStore>);

#[tauri::command]
async fn parent_plan(path: String, branch: String) -> Result<serde_json::Value, String> {
    parent_command("plan", &path, &branch, None).await
}

#[tauri::command]
async fn import_plan(
    source: String,
    projects_root: String,
    destination: Option<String>,
) -> Result<serde_json::Value, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let mut command = Command::new("orcan");
        command.args([
            "studio",
            "import",
            "plan",
            "--source",
            &source,
            "--projects-root",
            &projects_root,
        ]);
        if let Some(destination) = destination.filter(|value| !value.trim().is_empty()) {
            command.args(["--destination", &destination]);
        }
        command.output()
    })
    .await
    .map_err(|error| format!("import plan stopped: {error}"))?
    .map_err(|error| format!("could not start import plan: {error}"))
    .and_then(|output| {
        serde_json::from_slice(&output.stdout)
            .map_err(|error| format!("invalid import plan response: {error}"))
    })
}

#[tauri::command]
async fn import_apply(
    source: String,
    projects_root: String,
    destination: Option<String>,
) -> Result<serde_json::Value, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let mut command = Command::new("orcan");
        command.args([
            "studio",
            "import",
            "apply",
            "--source",
            &source,
            "--projects-root",
            &projects_root,
            "--yes",
        ]);
        if let Some(destination) = destination.filter(|value| !value.trim().is_empty()) {
            command.args(["--destination", &destination]);
        }
        command.output()
    })
    .await
    .map_err(|error| format!("import stopped: {error}"))?
    .map_err(|error| format!("could not start import: {error}"))
    .and_then(|output| {
        serde_json::from_slice(&output.stdout)
            .map_err(|error| format!("invalid import response: {error}"))
    })
}

#[tauri::command]
async fn worktree_cleanup(
    path: String,
    worktrees_root: String,
    apply: bool,
) -> Result<serde_json::Value, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let mut command = Command::new("orcan");
        command.args([
            "studio",
            "worktree",
            if apply { "remove-apply" } else { "remove-plan" },
            "--path",
            &path,
            "--worktrees-root",
            &worktrees_root,
        ]);
        if apply {
            command.arg("--yes");
        }
        command.output()
    })
    .await
    .map_err(|error| format!("cleanup stopped: {error}"))?
    .map_err(|error| format!("could not start cleanup: {error}"))
    .and_then(|output| {
        serde_json::from_slice(&output.stdout)
            .map_err(|error| format!("invalid cleanup response: {error}"))
    })
}

#[tauri::command]
async fn parent_apply(
    path: String,
    branch: String,
    expected_head: String,
) -> Result<serde_json::Value, String> {
    parent_command("apply", &path, &branch, Some(&expected_head)).await
}

async fn parent_command(
    mode: &str,
    path: &str,
    branch: &str,
    expected_head: Option<&str>,
) -> Result<serde_json::Value, String> {
    let mode = mode.to_owned();
    let path = path.to_owned();
    let branch = branch.to_owned();
    let expected_head = expected_head.map(str::to_owned);
    let output = tauri::async_runtime::spawn_blocking(move || {
        let mut command = Command::new("orcan");
        command.args([
            "studio", "parent", &mode, "--path", &path, "--branch", &branch,
        ]);
        if let Some(head) = expected_head {
            command.args(["--expected-head", &head, "--yes"]);
        }
        command.output()
    })
    .await
    .map_err(|error| format!("parent task stopped: {error}"))?
    .map_err(|error| format!("could not start Orcan parent operation: {error}"))?;
    let value: serde_json::Value = serde_json::from_slice(&output.stdout)
        .map_err(|error| format!("invalid parent operation response: {error}"))?;
    if !output.status.success() {
        return Err(value["error"]
            .as_str()
            .unwrap_or("parent operation failed")
            .to_owned());
    }
    Ok(value)
}

fn vault_entry(profile_id: &str, kind: &str) -> Result<keyring::Entry, String> {
    keyring::Entry::new("io.orcan.studio", &format!("{profile_id}:{kind}"))
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
    for kind in ["password", "key-passphrase"] {
        let _ = vault_entry(&id, kind)
            .and_then(|entry| entry.delete_credential().map_err(|error| error.to_string()));
    }
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
    repo: String,
    branch: String,
    worktrees_root: String,
    workspaces: Vec<String>,
) -> Result<serde_json::Value, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let mut command = Command::new("orcan");
        command.args([
            "studio",
            "worktree",
            "plan",
            "--repo",
            &repo,
            "--branch",
            &branch,
            "--worktrees-root",
            &worktrees_root,
        ]);
        for workspace in workspaces {
            command.args(["--workspace", &workspace]);
        }
        command.output()
    })
    .await
    .map_err(|error| format!("worktree plan stopped: {error}"))?
    .map_err(|error| format!("could not start worktree plan: {error}"))
    .and_then(|output| {
        serde_json::from_slice(&output.stdout)
            .map_err(|error| format!("invalid worktree plan response: {error}"))
    })
}

#[tauri::command]
async fn worktree_apply(
    repo: String,
    branch: String,
    worktrees_root: String,
    workspaces: Vec<String>,
) -> Result<serde_json::Value, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let mut command = Command::new("orcan");
        command.args([
            "studio",
            "worktree",
            "apply",
            "--repo",
            &repo,
            "--branch",
            &branch,
            "--worktrees-root",
            &worktrees_root,
            "--yes",
        ]);
        for workspace in workspaces {
            command.args(["--workspace", &workspace]);
        }
        command.output()
    })
    .await
    .map_err(|error| format!("worktree task stopped: {error}"))?
    .map_err(|error| format!("could not start worktree: {error}"))
    .and_then(|output| {
        serde_json::from_slice(&output.stdout)
            .map_err(|error| format!("invalid worktree response: {error}"))
    })
}

#[tauri::command]
async fn settings_project_action(
    config: String,
    workspace: String,
    project: String,
    action: String,
    apply: bool,
) -> Result<serde_json::Value, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let mut command = Command::new("orcan");
        command.args([
            "studio",
            "settings",
            match (action.as_str(), apply) {
                ("detach", true) => "project-detach-apply",
                ("detach", false) => "project-detach-plan",
                (_, true) => "project-add-apply",
                _ => "project-add-plan",
            },
            "--config",
            &config,
            "--workspace",
            &workspace,
            "--project",
            &project,
        ]);
        if apply {
            command.arg("--yes");
        }
        command.output()
    })
    .await
    .map_err(|error| format!("settings task stopped: {error}"))?
    .map_err(|error| format!("could not start settings task: {error}"))
    .and_then(|output| {
        serde_json::from_slice(&output.stdout)
            .map_err(|error| format!("invalid settings response: {error}"))
    })
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
            list_profiles,
            save_profile,
            delete_profile,
            save_secret,
            parent_plan,
            parent_apply,
            import_plan,
            import_apply,
            worktree_cleanup,
            worktree_plan,
            worktree_apply,
            settings_project_action
        ])
        .run(tauri::generate_context!())
        .expect("error while running Orcan Studio");
}
