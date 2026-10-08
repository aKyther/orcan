//! Single-runtime guards shared by creation and lifecycle commands.
use super::*;

pub(super) fn validate_instance(name: &str) -> Result<(), String> {
    if name.is_empty()
        || name.len() > 48
        || !name.as_bytes()[0].is_ascii_lowercase()
        || !name
            .bytes()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == b'-')
    {
        return Err(
            "Use 1–48 lowercase letters, digits or hyphens, starting with a letter.".into(),
        );
    }
    Ok(())
}

pub(super) async fn verify_container_owner(
    enclave: &EnclaveInput,
    report: &ProbeReport,
    state: &tauri::State<'_, ProfileState>,
) -> Result<(), String> {
    if let Some(instance) = &enclave.instance {
        validate_instance(instance)?;
        if report.runtime.docker.container.name != format!("orcan-{instance}") {
            return Err("The reported container does not match the selected instance".into());
        }
        if !matches!(
            report.runtime.docker.container.state.as_str(),
            "missing" | "unavailable"
        ) {
            let owner = provisioning::execute(enclave, &format!("docker inspect --format '{{{{index .Config.Labels \"com.docker.compose.project\"}}}}' -- {}", shell_quote(&report.runtime.docker.container.name)), state).await?;
            if owner.trim() != format!("orcan-{instance}") {
                return Err("This container is not owned by the selected Orcan Compose project. No action was taken.".into());
            }
        }
    }
    Ok(())
}

#[tauri::command]
pub(super) async fn list_instances(
    mut enclave: EnclaveInput,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    enclave.instance = None;
    let output = run_on_enclave(
        enclave,
        vec!["studio".into(), "instances".into(), "--json".into()],
        state,
    )
    .await?;
    serde_json::from_str(&output).map_err(|error| format!("Invalid runtime inventory: {error}"))
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(super) struct Readiness {
    user: String,
    docker: DockerReadiness,
    report: Option<ProbeReport>,
    orcan_error: Option<String>,
    capacity: Option<serde_json::Value>,
    images: Vec<String>,
    project_roots: Vec<String>,
}

pub(super) async fn creation_choices(
    enclave: &EnclaveInput,
    report: &ProbeReport,
    state: &tauri::State<'_, ProfileState>,
) -> Result<(Vec<String>, Vec<String>), String> {
    let output = provisioning::execute(enclave, "docker image ls --filter 'label=org.opencontainers.image.title=Orcan' --format '{{.Repository}}:{{.Tag}}'", state).await.unwrap_or_default();
    let images = image_choices(&output);
    let mut roots = vec![report.paths.projects_root.clone()];
    let inventory = list_instances(enclave.clone(), state.clone())
        .await
        .unwrap_or_default();
    if let Some(instances) = inventory["instances"].as_array() {
        for instance in instances {
            let mut connection = enclave.clone();
            connection.instance = instance["instance"].as_str().map(str::to_owned);
            if connection.instance == enclave.instance {
                continue;
            }
            if let Ok(existing) = probe(connection, state.clone()).await {
                roots.push(existing.paths.projects_root);
            }
        }
    }
    roots.retain(|root| root.starts_with('/') && !root.contains(['\n', '\r', '$', '`']));
    roots.sort();
    roots.dedup();
    Ok((images, roots))
}

fn image_choices(output: &str) -> Vec<String> {
    let mut images: Vec<String> = output
        .lines()
        .filter(|line| {
            line.as_bytes()
                .first()
                .is_some_and(u8::is_ascii_alphanumeric)
                && !line.contains("<none>")
                && valid_image_reference(line)
        })
        .map(str::to_owned)
        .collect();
    images.sort();
    images.dedup();
    images
}

#[tauri::command]
pub(super) async fn server_capacity(
    enclave: EnclaveInput,
    path: Option<String>,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    let disk_command = match &path {
        Some(path) if path.starts_with('/') => format!(
            "p={}; while [ ! -d \"$p\" ] && [ \"$p\" != / ]; do p=$(dirname \"$p\"); done; df -Pk \"$p\"",
            shell_quote(path)
        ),
        _ => "df -Pk \"$HOME\"".into(),
    };
    let (engine, disk) = tokio::join!(
        provisioning::execute(
            &enclave,
            "docker info --format '{{.NCPU}} {{.MemTotal}}'",
            &state
        ),
        provisioning::execute(&enclave, &disk_command, &state)
    );
    let mut capacity = serde_json::json!({"diskPath":path});
    if let Ok(engine) = engine {
        let fields = engine.split_whitespace().collect::<Vec<_>>();
        if fields.len() == 2 {
            capacity["cpus"] = fields[0].parse::<u64>().ok().into();
            capacity["memoryBytes"] = fields[1].parse::<u64>().ok().into();
        }
    }
    if let Ok(disk) = disk {
        if let Some(line) = disk.lines().last() {
            let fields = line.split_whitespace().collect::<Vec<_>>();
            if fields.len() >= 6 {
                capacity["diskTotalBytes"] = fields[1]
                    .parse::<u64>()
                    .ok()
                    .and_then(|n| n.checked_mul(1024))
                    .into();
                capacity["diskFreeBytes"] = fields[3]
                    .parse::<u64>()
                    .ok()
                    .and_then(|n| n.checked_mul(1024))
                    .into();
            }
        }
    }
    Ok(capacity)
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
    let (images, project_roots) = if let Some(report) = report.as_ref() {
        creation_choices(&enclave, report, &state).await?
    } else {
        (Vec::new(), Vec::new())
    };
    let capacity = server_capacity(
        enclave,
        report
            .as_ref()
            .map(|report| report.paths.projects_root.clone()),
        state,
    )
    .await
    .ok();
    Ok(Readiness {
        user,
        docker: docker_readiness(docker),
        report,
        orcan_error,
        capacity,
        images,
        project_roots,
    })
}

pub(super) fn creation_blocker(report: &ProbeReport) -> Option<String> {
    if report.context.configuration.state != "missing"
        || !matches!(
            report.runtime.docker.container.state.as_str(),
            "missing" | "unavailable"
        )
    {
        return Some("This container name already has a configuration or container. Choose another name or open it.".into());
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
    if action == RuntimeAction::Down {
        if matches!(container.state.as_str(), "missing" | "unavailable") {
            return Err("There is no container to remove".into());
        }
        return Ok(None); // Scoped Compose down; never removes shared data.
    }
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
        RuntimeAction::Down => unreachable!(),
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

    #[test]
    fn image_choices_are_sorted_unique_and_never_shell_arguments() {
        assert_eq!(
            image_choices(
                "orcan:tester\norcan:latest\norcan:tester\n<none>:<none>\n--option\norcan:latest;id\n"
            ),
            vec!["orcan:latest", "orcan:tester"]
        );
        assert!(image_choices("").is_empty());
    }

    #[test]
    fn instance_names_cannot_escape_paths_or_inject_commands() {
        for name in ["developer", "tester-2", "a"] {
            assert!(validate_instance(name).is_ok());
        }
        for name in [
            "",
            "../tester",
            "DEV",
            "-tester",
            "tester;rm",
            "with space",
            "a/b",
        ] {
            assert!(validate_instance(name).is_err());
        }
        assert!(validate_instance(&"a".repeat(49)).is_err());
    }

    #[test]
    fn down_removes_the_scoped_stack_even_when_stopped_but_keeps_data() {
        let mut report = report();
        report.runtime.docker.container.state = "exited".into();
        assert_eq!(
            lifecycle_command(&report, RuntimeAction::Down).unwrap(),
            None
        );
        assert_eq!(runtime_args(RuntimeAction::Down), vec!["down"]);
        report.runtime.docker.container.state = "missing".into();
        assert!(lifecycle_command(&report, RuntimeAction::Down).is_err());
    }

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
