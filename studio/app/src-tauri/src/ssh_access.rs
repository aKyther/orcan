//! Optional user-approved host Git access, separate from CLI/image provisioning.
use super::*;
use sha2::{Digest, Sha256};
use zeroize::Zeroizing;

fn command(mode: &str, args: &[String]) -> String {
    format!(
        "python3 -c {} {} {}",
        shell_quote(include_str!("ssh_access.py")),
        shell_quote(mode),
        args.iter()
            .map(|value| shell_quote(value))
            .collect::<Vec<_>>()
            .join(" ")
    )
}

#[tauri::command]
pub(super) async fn git_ssh_keys(
    enclave: EnclaveInput,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    let output = provisioning::execute(&enclave, &command("list", &[]), &state).await?;
    serde_json::from_str(&output).map_err(|_| "Invalid SSH key inventory".into())
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub(super) struct KeyTransfer {
    source: EnclaveInput,
    destination: EnclaveInput,
    source_name: String,
    destination_name: String,
    fingerprint: String,
    host: String,
    user: String,
    configure: bool,
    confirmed: bool,
}

#[tauri::command]
pub(super) async fn transfer_git_ssh_key(
    input: KeyTransfer,
    operation_id: String,
    app: tauri::AppHandle,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    if !input.confirmed {
        return Err("Explicit approval is required to copy a private SSH key".into());
    }
    if Target::from(input.source.target.clone()) == Target::from(input.destination.target.clone())
        && input.source.username == input.destination.username
        && input.source.profile_id == input.destination.profile_id
    {
        return Err("Choose a different source and destination profile".into());
    }
    let mut progress = transfer_progress::TransferProgress::new(app, operation_id);
    progress.stage("checking", None);
    let result = async {
        provisioning::execute(
            &input.destination,
            &command(
                "check",
                &[
                    input.destination_name.clone(),
                    input.host.clone(),
                    input.user.clone(),
                ],
            ),
            &state,
        )
        .await?;
        // Zero the native export buffer on every completion/error path. It is
        // never sent to the webview, activity log, vault, argv, disk or resume cache.
        progress.stage("exporting", None);
        let payload = Zeroizing::new(
            provisioning::execute(
                &input.source,
                &command("export", &[input.source_name, input.fingerprint.clone()]),
                &state,
            )
            .await?,
        );
        if payload.len() > 512 * 1024 {
            return Err("SSH payload exceeded its size limit".into());
        }
        let digest = format!("{:x}", Sha256::digest(payload.as_bytes()));
        let args = vec![
            input.destination_name,
            input.fingerprint,
            digest,
            input.host,
            input.user,
            if input.configure { "yes" } else { "no" }.into(),
        ];
        progress.stage("transferring", Some(payload.len() as u64));
        let output = provisioning::execute_with_input(
            &input.destination,
            &command("install", &args),
            payload.as_bytes(),
            &state,
        )
        .await?;
        progress.advance(payload.len());
        serde_json::from_str(&output).map_err(|_| "Invalid SSH preparation result".into())
    }
    .await;
    progress.stage(
        if result.is_ok() {
            "completed"
        } else {
            "failed"
        },
        None,
    );
    result
}

#[tauri::command]
pub(super) async fn test_git_ssh(
    enclave: EnclaveInput,
    name: String,
    host: String,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    let output = provisioning::execute(&enclave, &command("test", &[name, host]), &state).await?;
    serde_json::from_str(&output).map_err(|_| "Invalid Git access result".into())
}

#[tauri::command]
pub(super) async fn git_ssh_host_identity(
    enclave: EnclaveInput,
    host: String,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    let output =
        provisioning::execute(&enclave, &command("host-identity", &[host]), &state).await?;
    serde_json::from_str(&output).map_err(|_| "Invalid Git host identity".into())
}

#[tauri::command]
pub(super) async fn trust_git_ssh_host(
    enclave: EnclaveInput,
    host: String,
    fingerprint: String,
    key: String,
    confirmed: bool,
    state: tauri::State<'_, ProfileState>,
) -> Result<(), String> {
    if !confirmed {
        return Err("Git host identity needs explicit approval".into());
    }
    provisioning::execute(
        &enclave,
        &command("trust-host", &[host, fingerprint, key]),
        &state,
    )
    .await
    .map(|_| ())
}
