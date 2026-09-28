use orcan_studio_core::{ConnectionProfile, ProbeReport, ProfileStore, SystemRunner, Target};
use serde::Deserialize;
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
async fn probe(target: TargetInput) -> Result<ProbeReport, String> {
    let target = Target::from(target);
    tauri::async_runtime::spawn_blocking(move || target.probe(&SystemRunner))
        .await
        .map_err(|error| format!("probe task stopped: {error}"))?
        .map_err(|error| error.to_string())
}

struct ProfileState(Mutex<ProfileStore>);

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
            list_profiles,
            save_profile,
            delete_profile,
            save_secret
        ])
        .run(tauri::generate_context!())
        .expect("error while running Orcan Studio");
}
