//! Single-runtime guards shared by creation and lifecycle commands.
use super::*;

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(super) struct Readiness {
    user: String,
    docker: DockerReadiness,
    report: Option<ProbeReport>,
    orcan_error: Option<String>,
}

#[tauri::command]
pub(super) async fn enclave_readiness(
    enclave: EnclaveInput,
    state: tauri::State<'_, ProfileState>,
) -> Result<Readiness, String> {
    let user = provisioning::execute(&enclave, "id -un", &state).await?;
    let (docker, report) = tokio::join!(
        provisioning::execute(
            &enclave,
            "docker version --format '{{.Server.Version}}'",
            &state
        ),
        probe(enclave.clone(), state.clone())
    );
    let (report, orcan_error) = match report {
        Ok(report) => (Some(report), None),
        Err(error) => (None, Some(error)),
    };
    Ok(Readiness {
        user,
        docker: docker_readiness(docker),
        report,
        orcan_error,
    })
}

pub(super) fn creation_blocker(report: &ProbeReport) -> Option<String> {
    if report.context.configuration.state != "missing"
        || !matches!(
            report.runtime.docker.container.state.as_str(),
            "missing" | "unavailable"
        )
    {
        return Some("This destination already owns an Enclave or context. Open it instead of creating another.".into());
    }
    if !report.runtime.docker.available {
        return Some("Docker is not ready for this user.".into());
    }
    if !report.runtime.docker.image.present {
        return Some(format!(
            "Transfer {} to this destination before creating the Enclave.",
            report.runtime.docker.image.name
        ));
    }
    None
}

pub(super) fn lifecycle_command(
    report: &ProbeReport,
    action: RuntimeAction,
) -> Result<Option<String>, String> {
    if !report.runtime.docker.available {
        return Err("Docker is not available on this destination".into());
    }
    if let Some(operation) = report.control.operations.get("runtime_lifecycle") {
        if !operation.available {
            return Err(operation.reason.clone());
        }
    }
    let container = &report.runtime.docker.container;
    if matches!(container.state.as_str(), "missing" | "unavailable") {
        if action != RuntimeAction::Start {
            return Err("There is no container to stop or restart".into());
        }
        if !report.runtime.launch.recorded {
            return Err("No saved launch options. Set up this Enclave first.".into());
        }
        if report.runtime.launch.ttyd_auth {
            return Err("The container was removed. Supply browser-terminal credentials on the host to recreate it.".into());
        }
        if !report.runtime.docker.image.present {
            return Err("Transfer the required image before starting this Enclave.".into());
        }
        return Ok(None); // Existing Orcan resume path recreates a removed container.
    }
    let verb = match action {
        RuntimeAction::Start if container.state == "running" => {
            return Err("Container is already running".into());
        }
        RuntimeAction::Start if !matches!(container.state.as_str(), "created" | "exited") => {
            return Err("Container is not in a stopped state. Refresh its status.".into());
        }
        RuntimeAction::Start => "start",
        RuntimeAction::Stop | RuntimeAction::Restart if container.state != "running" => {
            return Err("Container is not running".into());
        }
        RuntimeAction::Stop => "stop",
        RuntimeAction::Restart => "restart",
    };
    if container.name.is_empty() {
        return Err("Orcan did not report a container name".into());
    }
    Ok(Some(format!(
        "docker {verb} -- {}",
        shell_quote(&container.name)
    )))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn report() -> ProbeReport {
        serde_json::from_value(serde_json::json!({
            "protocol": {"name":"orcan-studio","version":1,"methods":[]},
            "sandbox":{"version":"test"}, "host":{"os":"Linux","architecture":"amd64"},
            "paths":{"home":"/orcan","data":"/orcan","projects_root":"/sources","workspace_metadata_root":"/workspaces","managed_worktrees_root":"/worktrees"},
            "capabilities":{"docker":true,"git":true,"managed_projects":true,"live_reconcile":true},
            "runtime":{"config":"missing","generated":"missing","docker":{"available":true,"image":{"name":"orcan:latest","present":true},"container":{"name":"orcan-1","state":"missing"}}},
            "context":{"configuration":{"state":"missing","revision":null},"paths":{"workspace_metadata_root":"/workspaces","managed_worktrees_root":"/worktrees"},"workspaces":[],"managed_projects":[]}
        })).unwrap()
    }

    #[test]
    fn creation_requires_absent_context_container_and_present_image() {
        let mut report = report();
        assert!(creation_blocker(&report).is_none());
        report.runtime.docker.image.present = false;
        assert!(creation_blocker(&report).unwrap().contains("Transfer"));
        report.runtime.docker.image.present = true;
        report.context.configuration.state = "present".into();
        assert!(creation_blocker(&report).is_some());
        report.context.configuration.state = "missing".into();
        report.runtime.docker.container.state = "exited".into();
        assert!(creation_blocker(&report).is_some());
    }

    #[test]
    fn lifecycle_preserves_existing_container_even_with_protected_ttyd() {
        let mut report = report();
        report.runtime.docker.container.state = "running".into();
        report.runtime.launch.ttyd_auth = true;
        assert_eq!(
            lifecycle_command(&report, RuntimeAction::Restart).unwrap(),
            Some("docker restart -- 'orcan-1'".into())
        );
        assert_eq!(
            lifecycle_command(&report, RuntimeAction::Stop).unwrap(),
            Some("docker stop -- 'orcan-1'".into())
        );
        report.runtime.docker.container.state = "exited".into();
        assert_eq!(
            lifecycle_command(&report, RuntimeAction::Start).unwrap(),
            Some("docker start -- 'orcan-1'".into())
        );
        report.runtime.docker.container.state = "missing".into();
        assert!(lifecycle_command(&report, RuntimeAction::Start).is_err());
        report.runtime.launch.ttyd_auth = false;
        report.runtime.launch.recorded = true;
        assert_eq!(
            lifecycle_command(&report, RuntimeAction::Start).unwrap(),
            None
        );
    }

    #[test]
    fn unavailable_docker_and_empty_names_block_lifecycle() {
        let mut report = report();
        report.runtime.docker.available = false;
        assert!(lifecycle_command(&report, RuntimeAction::Start).is_err());
        report.runtime.docker.available = true;
        report.runtime.docker.container.state = "running".into();
        report.runtime.docker.container.name.clear();
        assert!(lifecycle_command(&report, RuntimeAction::Restart).is_err());
    }
}
