//! Fixed context protocol endpoints; no profile storage or provisioning.
use super::{EnclaveInput, ProfileState, run_on_enclave};

/// Execute a Studio helper through the selected Enclave and decode its JSON reply.
pub(super) async fn studio_json(
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
    if value["ok"] != true {
        return Err("Orcan Studio response has no valid outcome".to_owned());
    }
    Ok(value)
}

#[tauri::command]
pub(super) async fn parent_plan(
    enclave: EnclaveInput,
    path: String,
    branch: String,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    parent_command(enclave, "plan", path, branch, None, state).await
}

#[tauri::command]
pub(super) async fn import_plan(
    enclave: EnclaveInput,
    source: String,
    projects_root: String,
    parent: Option<String>,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    import_command(enclave, "plan", source, projects_root, parent, state).await
}

#[tauri::command]
pub(super) async fn import_apply(
    enclave: EnclaveInput,
    source: String,
    projects_root: String,
    parent: Option<String>,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    import_command(enclave, "apply", source, projects_root, parent, state).await
}

#[tauri::command]
pub(super) async fn directory_plan(
    enclave: EnclaveInput,
    projects_root: String,
    parent: String,
    name: String,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    studio_json(
        enclave,
        context_args(
            "directory",
            "plan",
            &[
                ("--projects-root", &projects_root),
                ("--parent", &parent),
                ("--name", &name),
            ],
        ),
        state,
    )
    .await
}

#[tauri::command]
pub(super) async fn directory_apply(
    enclave: EnclaveInput,
    projects_root: String,
    parent: String,
    name: String,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    studio_json(
        enclave,
        context_args(
            "directory",
            "apply",
            &[
                ("--projects-root", &projects_root),
                ("--parent", &parent),
                ("--name", &name),
            ],
        ),
        state,
    )
    .await
}

#[tauri::command]
pub(super) async fn worktree_branches(
    enclave: EnclaveInput,
    repo: String,
    worktrees_root: String,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    studio_json(
        enclave,
        context_args(
            "worktree",
            "branches",
            &[("--repo", &repo), ("--worktrees-root", &worktrees_root)],
        ),
        state,
    )
    .await
}

#[tauri::command]
pub(super) async fn worktree_cleanup(
    enclave: EnclaveInput,
    path: String,
    worktrees_root: String,
    remove_branch: bool,
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
    if remove_branch {
        args.push("--remove-branch".to_owned());
    }
    studio_json(enclave, args, state).await
}

#[tauri::command]
pub(super) async fn parent_apply(
    enclave: EnclaveInput,
    path: String,
    branch: String,
    expected_head: String,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    parent_command(enclave, "apply", path, branch, Some(expected_head), state).await
}

pub(super) async fn parent_command(
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
#[tauri::command]
pub(super) async fn worktree_plan(
    enclave: EnclaveInput,
    repo: String,
    branch: String,
    worktrees_root: String,
    workspaces: Vec<String>,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    studio_json(
        enclave,
        worktree_args("plan", &repo, &branch, &worktrees_root, workspaces),
        state,
    )
    .await
}

#[tauri::command]
pub(super) async fn worktree_inventory(
    enclave: EnclaveInput,
    worktrees_root: String,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    studio_json(
        enclave,
        vec![
            "studio".to_owned(),
            "worktree".to_owned(),
            "list".to_owned(),
            "--worktrees-root".to_owned(),
            worktrees_root,
        ],
        state,
    )
    .await
}

#[tauri::command]
pub(super) async fn worktree_apply(
    enclave: EnclaveInput,
    repo: String,
    branch: String,
    worktrees_root: String,
    workspaces: Vec<String>,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    studio_json(
        enclave,
        worktree_args("apply", &repo, &branch, &worktrees_root, workspaces),
        state,
    )
    .await
}

fn context_args(endpoint: &str, mode: &str, fields: &[(&str, &str)]) -> Vec<String> {
    let mut args = vec!["studio".to_owned(), endpoint.to_owned(), mode.to_owned()];
    for (flag, value) in fields {
        args.extend([flag.to_string(), value.to_string()]);
    }
    if mode == "apply" || mode == "remove-apply" {
        args.push("--yes".to_owned());
    }
    args
}

fn worktree_args(
    mode: &str,
    repo: &str,
    branch: &str,
    root: &str,
    workspaces: Vec<String>,
) -> Vec<String> {
    let mut args = context_args(
        "worktree",
        mode,
        &[
            ("--repo", repo),
            ("--branch", branch),
            ("--worktrees-root", root),
        ],
    );
    for workspace in workspaces {
        args.extend(["--workspace".to_owned(), workspace]);
    }
    args
}

async fn import_command(
    enclave: EnclaveInput,
    mode: &str,
    source: String,
    root: String,
    parent: Option<String>,
    state: tauri::State<'_, ProfileState>,
) -> Result<serde_json::Value, String> {
    let mut args = context_args(
        "import",
        mode,
        &[("--source", &source), ("--projects-root", &root)],
    );
    if let Some(parent) = parent.filter(|value| !value.trim().is_empty()) {
        args.extend(["--parent".to_owned(), parent]);
    }
    studio_json(enclave, args, state).await
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn plan_and_apply_share_flags_but_only_apply_is_approved() {
        let plan = worktree_args(
            "plan",
            "/source with space",
            "feature/auth",
            "/trees",
            vec!["one".into(), "two".into()],
        );
        let mut expected = plan.clone();
        expected[2] = "apply".into();
        expected.insert(9, "--yes".into());
        assert_eq!(
            worktree_args(
                "apply",
                "/source with space",
                "feature/auth",
                "/trees",
                vec!["one".into(), "two".into()]
            ),
            expected
        );
        assert!(!plan.iter().any(|arg| arg == "--yes"));
        assert!(plan.contains(&"/source with space".to_owned()));
    }
}
