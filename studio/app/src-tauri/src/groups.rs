//! Saved manual enclaves and UUID-checked operations; no workflow executor.
use super::*;
use fs2::FileExt;
use std::{collections::HashSet, fs, path::Path};
use uuid::Uuid;

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Member {
    pub host_id: String,
    pub container_id: String,
    pub profile_id: String,
    pub instance: Option<String>,
    pub label: String,
    pub x: f64,
    pub y: f64,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Edge {
    pub id: String,
    pub source: String,
    pub target: String,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Group {
    pub id: String,
    pub revision: u64,
    pub name: String,
    pub members: Vec<Member>,
    pub edges: Vec<Edge>,
}

fn uuid(value: &str) -> Result<(), String> {
    if Uuid::parse_str(value)
        .map_err(|_| "Invalid enclave UUID")?
        .to_string()
        != value
    {
        return Err("Invalid enclave UUID".into());
    }
    Ok(())
}

fn validate(group: &Group) -> Result<(), String> {
    uuid(&group.id)?;
    if group.name.trim().is_empty()
        || group.name.len() > 120
        || group.name.contains(['\n', '\0'])
        || group.members.len() > 200
        || group.edges.len() > 1000
    {
        return Err(
            "Use a name up to 120 bytes, at most 200 containers and 1000 visual lines".into(),
        );
    }
    let mut members = HashSet::new();
    for member in &group.members {
        uuid(&member.host_id)?;
        uuid(&member.container_id)?;
        if !members.insert(member.container_id.clone())
            || member.profile_id.is_empty()
            || member.profile_id.len() > 200
            || member.label.len() > 240
            || !member.x.is_finite()
            || !member.y.is_finite()
            || member.x.abs() > 1_000_000.0
            || member.y.abs() > 1_000_000.0
        {
            return Err("Invalid or duplicate enclave member".into());
        }
        if let Some(instance) = &member.instance {
            enclave::validate_instance(instance)?;
        }
    }
    let mut edges = HashSet::new();
    for edge in &group.edges {
        uuid(&edge.id)?;
        if !edges.insert(&edge.id)
            || !members.contains(&edge.source)
            || !members.contains(&edge.target)
            || edge.source == edge.target
        {
            return Err("Visual lines must connect distinct enclave members".into());
        }
    }
    Ok(())
}

fn library(root: &Path) -> Result<std::path::PathBuf, String> {
    let path = root.join("enclaves");
    if path.is_symlink() {
        return Err("Enclave storage must not use symlinks".into());
    }
    fs::create_dir_all(&path).map_err(|error| error.to_string())?;
    Ok(path)
}

fn read(path: &Path) -> Result<Group, String> {
    if path.is_symlink() {
        return Err("Enclave records must not be symlinks".into());
    }
    let group: Group = serde_json::from_slice(&fs::read(path).map_err(|error| error.to_string())?)
        .map_err(|error| error.to_string())?;
    validate(&group)?;
    if path.file_stem().and_then(|name| name.to_str()) != Some(group.id.as_str()) {
        return Err("Enclave UUID does not match its file name".into());
    }
    Ok(group)
}

fn save_at(root: &Path, mut group: Group) -> Result<Group, String> {
    validate(&group)?;
    let library = library(root)?;
    let lock_path = library.join(".lock");
    if lock_path.is_symlink() {
        return Err("Invalid enclave storage lock".into());
    }
    let lock = fs::OpenOptions::new()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .open(lock_path)
        .map_err(|error| error.to_string())?;
    lock.try_lock_exclusive()
        .map_err(|_| "Enclave storage is busy; retry saving")?;
    let path = library.join(format!("{}.json", group.id));
    let revision = if path.exists() {
        read(&path)?.revision
    } else {
        0
    };
    if revision != group.revision {
        return Err("Enclave changed or was removed; reload before saving".into());
    }
    group.revision = revision
        .checked_add(1)
        .ok_or("Enclave revision exhausted")?;
    let pending = tempfile::NamedTempFile::new_in(&library).map_err(|error| error.to_string())?;
    fs::write(
        pending.path(),
        serde_json::to_vec_pretty(&group).map_err(|error| error.to_string())?,
    )
    .map_err(|error| error.to_string())?;
    pending.persist(path).map_err(|error| error.to_string())?;
    Ok(group)
}

#[tauri::command]
pub(super) fn list_groups() -> Result<Vec<Group>, String> {
    let path = library(&identities::root()?)?;
    let mut groups = Vec::new();
    for file in fs::read_dir(path).map_err(|error| error.to_string())? {
        let file = file.map_err(|error| error.to_string())?;
        if file
            .path()
            .extension()
            .is_some_and(|extension| extension == "json")
        {
            groups.push(read(&file.path())?);
        }
    }
    groups.sort_by(|a, b| a.name.cmp(&b.name));
    Ok(groups)
}

#[tauri::command]
pub(super) fn save_group(group: Group) -> Result<Group, String> {
    save_at(&identities::root()?, group)
}

pub(super) fn matches(
    report: &ProbeReport,
    host_id: &str,
    container_id: &str,
) -> Result<(), String> {
    uuid(host_id)?;
    uuid(container_id)?;
    let target = report
        .target
        .as_ref()
        .ok_or("Update the host CLI to verify target UUIDs")?;
    if target["state"] != "ready"
        || target["host_id"] != host_id
        || target["container_id"] != container_id
    {
        return Err("Target identity mismatch or missing configuration. Refresh or register the replacement explicitly.".into());
    }
    Ok(())
}

#[tauri::command]
pub(super) async fn register_target(
    enclave: EnclaveInput,
    state: tauri::State<'_, ProfileState>,
) -> Result<ProbeReport, String> {
    let report = probe(enclave.clone(), state.clone()).await?;
    enclave::verify_container_owner(&enclave, &report, &state).await?;
    if matches!(
        report.runtime.docker.container.state.as_str(),
        "missing" | "unavailable"
    ) {
        return Err("Create or start the existing container before registering it".into());
    }
    studio_json(
        enclave.clone(),
        vec![
            "studio".into(),
            "target".into(),
            "register".into(),
            "--yes".into(),
        ],
        state.clone(),
    )
    .await?;
    probe(enclave, state).await
}

#[tauri::command]
pub(super) async fn group_probe(
    enclave: EnclaveInput,
    host_id: String,
    container_id: String,
    state: tauri::State<'_, ProfileState>,
) -> Result<ProbeReport, String> {
    let report = probe(enclave.clone(), state.clone()).await?;
    matches(&report, &host_id, &container_id)?;
    enclave::verify_container_owner(&enclave, &report, &state).await?;
    Ok(report)
}

#[tauri::command]
pub(super) async fn group_start(
    enclave: EnclaveInput,
    host_id: String,
    container_id: String,
    state: tauri::State<'_, ProfileState>,
) -> Result<ProbeReport, String> {
    let report = group_probe(
        enclave.clone(),
        host_id.clone(),
        container_id.clone(),
        state.clone(),
    )
    .await?;
    if matches!(
        report.runtime.docker.container.state.as_str(),
        "missing" | "unavailable"
    ) {
        return Err("Container is missing or offline; enclave Start never recreates it".into());
    }
    if let Some(command) = enclave::lifecycle_command(&report, RuntimeAction::Start)? {
        provisioning::execute(&enclave, &command, &state).await?;
    }
    let verified = group_probe(enclave, host_id, container_id, state).await?;
    if verified.runtime.docker.container.state != "running" {
        return Err("Container did not become running".into());
    }
    Ok(verified)
}

#[tauri::command]
pub(super) async fn replace_container(
    enclave: EnclaveInput,
    host_id: String,
    container_id: String,
    apply: bool,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    group_probe(
        enclave.clone(),
        host_id,
        container_id.clone(),
        state.clone(),
    )
    .await?;
    let mut args = vec![
        "studio".into(),
        "target".into(),
        if apply {
            "replace-apply".into()
        } else {
            "replace-plan".into()
        },
        "--expected-id".into(),
        container_id,
    ];
    if apply {
        args.push("--yes".into());
    }
    studio_json(enclave, args, state).await
}

#[cfg(test)]
mod tests {
    use super::*;
    fn group() -> Group {
        Group {
            id: Uuid::new_v4().to_string(),
            revision: 0,
            name: "Review".into(),
            members: Vec::new(),
            edges: Vec::new(),
        }
    }
    #[test]
    fn saves_layout_and_refuses_stale_or_deleted_updates() {
        let root = tempfile::tempdir().unwrap();
        let original = group();
        let saved = save_at(root.path(), original.clone()).unwrap();
        assert_eq!(saved.revision, 1);
        assert!(save_at(root.path(), original).is_err());
        let path = root
            .path()
            .join("enclaves")
            .join(format!("{}.json", saved.id));
        fs::remove_file(path).unwrap();
        assert!(save_at(root.path(), saved).is_err());
    }
    #[test]
    fn lines_cannot_reference_non_members() {
        let mut group = group();
        group.edges.push(Edge {
            id: Uuid::new_v4().to_string(),
            source: "missing".into(),
            target: "missing".into(),
        });
        assert!(validate(&group).is_err());
    }
}
