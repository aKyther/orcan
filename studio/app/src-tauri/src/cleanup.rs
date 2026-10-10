//! Explicit installation removal, independent of transfer source selection.
use super::*;

async fn inventory(
    enclave: &EnclaveInput,
    state: &tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    let output = provisioning::execute(
        enclave,
        &format!(
            "python3 -c {}",
            shell_quote(include_str!("server_cleanup.py"))
        ),
        state,
    )
    .await?;
    serde_json::from_str(&output).map_err(|error| format!("Invalid server inventory: {error}"))
}

#[tauri::command]
pub(super) async fn server_cleanup_inventory(
    enclave: EnclaveInput,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    inventory(&enclave, &state).await
}

#[tauri::command]
pub(super) async fn remove_server_cli(
    enclave: EnclaveInput,
    expected_path: String,
    expected_version: String,
    confirmed: bool,
    state: tauri::State<'_, ProfileState>,
) -> Result<String, String> {
    if !confirmed {
        return Err("Removal needs confirmation".into());
    }
    let current = inventory(&enclave, &state).await?;
    validate_cli_removal(&current, &expected_path, &expected_version)?;
    provisioning::execute(
        &enclave,
        &format!(
            "printf 'yes\n' | ({})",
            remote_orcan_command(&["uninstall".into(), "--cli-only".into()])
        ),
        &state,
    )
    .await
}

fn validate_cli_removal(
    inventory: &serde_json::Value,
    path: &str,
    version: &str,
) -> Result<(), String> {
    let cli = &inventory["cli"];
    if cli["removable"] != true {
        return Err("This CLI does not support safe CLI-only removal. Update it first.".into());
    }
    if cli["path"].as_str() != Some(path) || cli["version"].as_str() != Some(version) {
        return Err("CLI changed. Check the server again.".into());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn cli_removal_requires_unchanged_capable_installation() {
        let mut plan = serde_json::json!({"cli":{"path":"/home/user/.local/bin/orcan","version":"orcan 4.0.0","removable":true}});
        assert!(validate_cli_removal(&plan, "/home/user/.local/bin/orcan", "orcan 4.0.0").is_ok());
        assert!(validate_cli_removal(&plan, "/other/orcan", "orcan 4.0.0").is_err());
        assert!(validate_cli_removal(&plan, "/home/user/.local/bin/orcan", "orcan 4.1.0").is_err());
        plan["cli"]["removable"] = false.into();
        assert!(validate_cli_removal(&plan, "/home/user/.local/bin/orcan", "orcan 4.0.0").is_err());
    }
}
