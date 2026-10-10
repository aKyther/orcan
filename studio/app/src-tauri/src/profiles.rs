//! Profile metadata and immutable credentials; secrets remain in the OS vault.
use super::ProfileState;
use orcan_studio_core::{ConnectionProfile, SshAuthentication, SshCredential};

pub(super) fn vault_entry(owner: &str, kind: &str) -> Result<keyring::Entry, String> {
    keyring::Entry::new("io.orcan.studio", &format!("{owner}:{kind}"))
        .map_err(|error| format!("credential vault unavailable: {error}"))
}

#[tauri::command]
pub(super) fn list_profiles(
    state: tauri::State<'_, ProfileState>,
) -> Result<Vec<ConnectionProfile>, String> {
    state
        .0
        .lock()
        .map_err(|_| "profile store is unavailable".to_owned())?
        .list()
        .map_err(|error| error.to_string())
}

#[tauri::command]
pub(super) fn save_profile(
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
pub(super) fn delete_profile(
    id: String,
    state: tauri::State<'_, ProfileState>,
) -> Result<(), String> {
    state
        .0
        .lock()
        .map_err(|_| "profile store is unavailable".to_owned())?
        .delete(&id)
        .map_err(|error| error.to_string())?;
    delete_vault_secrets(&id);
    Ok(())
}

pub(super) fn delete_vault_secrets(owner: &str) {
    for kind in ["password", "key-passphrase"] {
        let _ = vault_entry(owner, kind)
            .and_then(|entry| entry.delete_credential().map_err(|error| error.to_string()));
    }
}

#[tauri::command]
pub(super) fn list_credentials(
    state: tauri::State<'_, ProfileState>,
) -> Result<Vec<SshCredential>, String> {
    state
        .0
        .lock()
        .map_err(|_| "profile store is unavailable".to_owned())?
        .list_credentials()
        .map_err(|error| error.to_string())
}

/// Creates an immutable credential and, when required, its vault secret.
#[tauri::command]
pub(super) fn create_credential(
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
pub(super) fn delete_credential(
    id: String,
    state: tauri::State<'_, ProfileState>,
) -> Result<(), String> {
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
pub(super) fn save_secret(profile_id: String, kind: String, secret: String) -> Result<(), String> {
    if secret.is_empty() || !matches!(kind.as_str(), "password" | "key-passphrase") {
        return Err("invalid credential payload".to_owned());
    }
    vault_entry(&profile_id, &kind)?
        .set_password(&secret)
        .map_err(|error| format!("could not store credential: {error}"))
}
