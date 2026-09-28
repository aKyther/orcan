//! Transport-neutral connection layer for Orcan Studio.
//!
//! The desktop UI never constructs a shell command. It selects a target and
//! asks this crate to invoke the fixed Orcan Studio protocol endpoint.

use serde::{Deserialize, Serialize};
use std::fmt;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

pub const PROTOCOL_NAME: &str = "orcan-studio";
pub const PROTOCOL_VERSION: u32 = 1;

/// A UI-safe lifecycle shared by every asynchronous Studio operation.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum JobState {
    Queued,
    Running,
    NeedsApproval,
    Succeeded,
    Failed,
    Cancelled,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct StudioJob {
    pub id: String,
    pub operation: String,
    pub state: JobState,
    pub stage: String,
    #[serde(default)]
    pub log: Vec<String>,
}

/// A mutation is always described before it can be approved and scheduled.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct OperationPlan {
    pub id: String,
    pub operation: String,
    pub summary: String,
    #[serde(default)]
    pub changes: Vec<String>,
    #[serde(default)]
    pub blockers: Vec<String>,
}

impl OperationPlan {
    pub fn ready(&self) -> bool {
        self.blockers.is_empty()
    }
    pub fn approved_job(&self) -> Result<StudioJob, StudioError> {
        if !self.ready() {
            return Err(StudioError::PlanBlocked);
        }
        Ok(StudioJob {
            id: self.id.clone(),
            operation: self.operation.clone(),
            state: JobState::Queued,
            stage: "approved plan queued".to_owned(),
            log: vec![self.summary.clone()],
        })
    }
}

impl StudioJob {
    pub fn transition(
        &mut self,
        state: JobState,
        stage: impl Into<String>,
    ) -> Result<(), StudioError> {
        let allowed = matches!(
            (&self.state, &state),
            (JobState::Queued, JobState::Running | JobState::Cancelled)
                | (
                    JobState::Running,
                    JobState::NeedsApproval
                        | JobState::Succeeded
                        | JobState::Failed
                        | JobState::Cancelled
                )
                | (
                    JobState::NeedsApproval,
                    JobState::Running | JobState::Cancelled
                )
        );
        if !allowed {
            return Err(StudioError::InvalidJobTransition);
        }
        self.state = state;
        self.stage = stage.into();
        Ok(())
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Target {
    /// Orcan is installed on the same Linux or macOS host as Studio.
    Local,
    /// Studio runs on Windows and Orcan runs in a named WSL2 distribution.
    Wsl2 { distribution: String },
    /// Orcan is reached through the user's OpenSSH configuration.
    Ssh { destination: String },
}

impl Target {
    pub fn probe_request(&self) -> Result<ProcessRequest, StudioError> {
        let orcan_args = ["studio", "probe", "--json"];
        match self {
            Self::Local => Ok(ProcessRequest::new("orcan", &orcan_args)),
            Self::Wsl2 { distribution } => {
                validate_identifier("WSL distribution", distribution)?;
                Ok(ProcessRequest::new(
                    "wsl.exe",
                    &[
                        "--distribution",
                        distribution,
                        "--exec",
                        "orcan",
                        "studio",
                        "probe",
                        "--json",
                    ],
                ))
            }
            Self::Ssh { destination } => {
                validate_identifier("SSH destination", destination)?;
                Ok(ProcessRequest::new(
                    "ssh",
                    &[
                        "-o",
                        "BatchMode=yes",
                        "--",
                        destination,
                        "orcan",
                        "studio",
                        "probe",
                        "--json",
                    ],
                ))
            }
        }
    }

    pub fn probe<R: ProcessRunner>(&self, runner: &R) -> Result<ProbeReport, StudioError> {
        let request = self.probe_request()?;
        let output = runner.run(&request)?;
        if !output.success {
            return Err(StudioError::CommandFailed {
                command: request.display(),
                stderr: output.stderr,
            });
        }

        parse_probe_report(&output.stdout)
    }
}

/// Decode the fixed, read-only response returned by `orcan studio probe`.
/// Native transports use this after collecting command output without invoking a shell.
pub fn parse_probe_report(output: &str) -> Result<ProbeReport, StudioError> {
    let report: ProbeReport = serde_json::from_str(output)
        .map_err(|error| StudioError::InvalidReport(error.to_string()))?;
    if report.protocol.name != PROTOCOL_NAME || report.protocol.version != PROTOCOL_VERSION {
        return Err(StudioError::IncompatibleProtocol {
            name: report.protocol.name,
            version: report.protocol.version,
        });
    }
    if !report
        .protocol
        .methods
        .iter()
        .any(|method| method == "probe")
    {
        return Err(StudioError::InvalidReport(
            "protocol report does not advertise probe".to_owned(),
        ));
    }
    Ok(report)
}

fn validate_identifier(label: &str, value: &str) -> Result<(), StudioError> {
    if value.is_empty() || value.chars().any(char::is_whitespace) {
        return Err(StudioError::InvalidTarget(format!(
            "{label} must be non-empty and cannot contain whitespace"
        )));
    }
    Ok(())
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ProcessRequest {
    pub program: String,
    pub arguments: Vec<String>,
}

impl ProcessRequest {
    fn new(program: &str, arguments: &[&str]) -> Self {
        Self {
            program: program.to_owned(),
            arguments: arguments
                .iter()
                .map(|argument| (*argument).to_owned())
                .collect(),
        }
    }

    fn display(&self) -> String {
        std::iter::once(self.program.as_str())
            .chain(self.arguments.iter().map(String::as_str))
            .collect::<Vec<_>>()
            .join(" ")
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ProcessOutput {
    pub success: bool,
    pub stdout: String,
    pub stderr: String,
}

pub trait ProcessRunner {
    fn run(&self, request: &ProcessRequest) -> Result<ProcessOutput, StudioError>;
}

pub struct SystemRunner;

impl ProcessRunner for SystemRunner {
    fn run(&self, request: &ProcessRequest) -> Result<ProcessOutput, StudioError> {
        let output = Command::new(&request.program)
            .args(&request.arguments)
            .output()
            .map_err(|error| StudioError::Launch {
                command: request.display(),
                reason: error.to_string(),
            })?;
        Ok(ProcessOutput {
            success: output.status.success(),
            stdout: String::from_utf8_lossy(&output.stdout).into_owned(),
            stderr: String::from_utf8_lossy(&output.stderr).into_owned(),
        })
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum StudioError {
    InvalidTarget(String),
    Launch { command: String, reason: String },
    CommandFailed { command: String, stderr: String },
    InvalidReport(String),
    IncompatibleProtocol { name: String, version: u32 },
    InvalidProfile(String),
    InvalidProfileStore(String),
    InvalidJobTransition,
    PlanBlocked,
    Io { path: PathBuf, reason: String },
}

impl fmt::Display for StudioError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidTarget(reason) => write!(formatter, "invalid target: {reason}"),
            Self::Launch { command, reason } => {
                write!(formatter, "cannot start {command}: {reason}")
            }
            Self::CommandFailed { command, stderr } => {
                write!(formatter, "{command} failed: {}", stderr.trim())
            }
            Self::InvalidReport(reason) => write!(formatter, "invalid Sandbox report: {reason}"),
            Self::IncompatibleProtocol { name, version } => {
                write!(formatter, "unsupported Sandbox protocol {name} v{version}")
            }
            Self::InvalidProfile(reason) => {
                write!(formatter, "invalid connection profile: {reason}")
            }
            Self::InvalidProfileStore(reason) => {
                write!(formatter, "invalid profile store: {reason}")
            }
            Self::InvalidJobTransition => write!(formatter, "invalid Studio job state transition"),
            Self::PlanBlocked => write!(formatter, "Studio operation plan has blockers"),
            Self::Io { path, reason } => {
                write!(formatter, "cannot access {}: {reason}", path.display())
            }
        }
    }
}

impl std::error::Error for StudioError {}

#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct SshProfileOptions {
    pub username: Option<String>,
    #[serde(default)]
    pub authentication: SshAuthentication,
}

#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum SshAuthentication {
    #[default]
    Agent,
    /// The actual password lives in the operating system credential vault.
    Password,
    /// The key path is stored; an optional passphrase lives in the credential vault.
    PrivateKey { path: String, has_passphrase: bool },
}

/// A reconnectable target stored by Studio. It intentionally contains no
/// passwords, private keys, passphrases, or SSH agent material.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct ConnectionProfile {
    pub id: String,
    pub name: String,
    pub target: Target,
    #[serde(default)]
    pub ssh: SshProfileOptions,
}

impl ConnectionProfile {
    pub fn validate(&self) -> Result<(), StudioError> {
        if self.id.is_empty()
            || !self.id.chars().all(|character| {
                character.is_ascii_alphanumeric() || character == '-' || character == '_'
            })
        {
            return Err(StudioError::InvalidProfile(
                "id must contain only ASCII letters, digits, hyphens, or underscores".to_owned(),
            ));
        }
        if self.name.trim().is_empty() {
            return Err(StudioError::InvalidProfile(
                "name cannot be empty".to_owned(),
            ));
        }
        self.target.probe_request().map(|_| ())?;
        match (&self.target, &self.ssh.authentication) {
            (Target::Ssh { .. }, SshAuthentication::PrivateKey { path, .. }) => {
                if path.is_empty() {
                    return Err(StudioError::InvalidProfile(
                        "private key path cannot be empty".to_owned(),
                    ));
                }
                let username = self.ssh.username.as_deref().ok_or_else(|| {
                    StudioError::InvalidProfile(
                        "username is required for native private-key SSH".to_owned(),
                    )
                })?;
                validate_identifier("SSH username", username)
            }
            (Target::Ssh { .. }, SshAuthentication::Password) => {
                let username = self.ssh.username.as_deref().ok_or_else(|| {
                    StudioError::InvalidProfile(
                        "username is required for native password SSH".to_owned(),
                    )
                })?;
                validate_identifier("SSH username", username)
            }
            (Target::Ssh { .. }, SshAuthentication::Agent) => {
                if let Some(username) = &self.ssh.username {
                    validate_identifier("SSH username", username)?;
                }
                Ok(())
            }
            (_, SshAuthentication::Agent) => Ok(()),
            _ => Err(StudioError::InvalidProfile(
                "SSH authentication options require an SSH target".to_owned(),
            )),
        }
    }
}

#[derive(Clone, Debug)]
pub struct ProfileStore {
    path: PathBuf,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
struct ProfileDocument {
    version: u32,
    profiles: Vec<ConnectionProfile>,
}

impl ProfileStore {
    pub fn new(path: impl Into<PathBuf>) -> Self {
        Self { path: path.into() }
    }

    pub fn list(&self) -> Result<Vec<ConnectionProfile>, StudioError> {
        Ok(self.read()?.profiles)
    }

    pub fn upsert(&self, profile: ConnectionProfile) -> Result<(), StudioError> {
        profile.validate()?;
        let mut document = self.read()?;
        if let Some(existing) = document
            .profiles
            .iter_mut()
            .find(|existing| existing.id == profile.id)
        {
            *existing = profile;
        } else {
            document.profiles.push(profile);
        }
        document
            .profiles
            .sort_by(|left, right| left.name.cmp(&right.name));
        self.write(&document)
    }

    pub fn delete(&self, id: &str) -> Result<(), StudioError> {
        let mut document = self.read()?;
        document.profiles.retain(|profile| profile.id != id);
        self.write(&document)
    }

    fn read(&self) -> Result<ProfileDocument, StudioError> {
        if !self.path.exists() {
            return Ok(ProfileDocument {
                version: 1,
                profiles: Vec::new(),
            });
        }
        let contents = fs::read_to_string(&self.path).map_err(|error| StudioError::Io {
            path: self.path.clone(),
            reason: error.to_string(),
        })?;
        let document = serde_json::from_str::<ProfileDocument>(&contents)
            .map_err(|error| StudioError::InvalidProfileStore(error.to_string()))?;
        if document.version != 1 {
            return Err(StudioError::InvalidProfileStore(format!(
                "unsupported profile store version {}",
                document.version
            )));
        }
        for profile in &document.profiles {
            profile.validate()?;
        }
        Ok(document)
    }

    fn write(&self, document: &ProfileDocument) -> Result<(), StudioError> {
        let parent = self.path.parent().unwrap_or_else(|| Path::new("."));
        fs::create_dir_all(parent).map_err(|error| StudioError::Io {
            path: parent.to_path_buf(),
            reason: error.to_string(),
        })?;
        let contents = serde_json::to_string_pretty(document)
            .map_err(|error| StudioError::InvalidProfileStore(error.to_string()))?;
        let temporary = self.path.with_extension("json.tmp");
        fs::write(&temporary, contents).map_err(|error| StudioError::Io {
            path: temporary.clone(),
            reason: error.to_string(),
        })?;
        if self.path.exists() {
            fs::remove_file(&self.path).map_err(|error| StudioError::Io {
                path: self.path.clone(),
                reason: error.to_string(),
            })?;
        }
        fs::rename(&temporary, &self.path).map_err(|error| StudioError::Io {
            path: self.path.clone(),
            reason: error.to_string(),
        })
    }
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct ProbeReport {
    pub protocol: Protocol,
    pub sandbox: Sandbox,
    pub host: Host,
    pub paths: Paths,
    pub capabilities: Capabilities,
    pub runtime: Runtime,
    pub context: ContextSnapshot,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Protocol {
    pub name: String,
    pub version: u32,
    pub methods: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Sandbox {
    pub version: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Host {
    pub os: String,
    pub architecture: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Paths {
    pub home: String,
    pub data: String,
    pub projects_root: String,
    pub workspace_metadata_root: String,
    pub managed_worktrees_root: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Capabilities {
    pub docker: bool,
    pub git: bool,
    pub managed_projects: bool,
    pub live_reconcile: bool,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Runtime {
    pub config: String,
    pub generated: String,
    pub docker: Docker,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Docker {
    pub available: bool,
    pub image: Image,
    pub container: Container,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Image {
    pub name: String,
    pub present: bool,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Container {
    pub name: String,
    pub state: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct ContextSnapshot {
    pub configuration: ConfigurationState,
    pub paths: ContextPaths,
    pub workspaces: Vec<Workspace>,
    pub managed_projects: Vec<ManagedProject>,
    #[serde(default)]
    pub repositories: Vec<Repository>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct ConfigurationState {
    pub state: String,
    pub revision: Option<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct ContextPaths {
    pub workspace_metadata_root: String,
    pub managed_worktrees_root: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Workspace {
    pub name: String,
    pub projects: Vec<ManagedProject>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct ManagedProject {
    pub name: Option<String>,
    pub path: String,
    pub kind: String,
    pub writable: bool,
    pub repository_id: Option<String>,
    pub git_common_dir: Option<String>,
    pub origin_url: Option<String>,
    pub branch: Option<String>,
    #[serde(default)]
    pub dirty: bool,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Repository {
    pub repository_id: String,
    pub origin_url: Option<String>,
    pub git_common_dir: Option<String>,
    pub bindings: Vec<RepositoryBinding>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct RepositoryBinding {
    pub workspace: String,
    pub project: Option<String>,
    pub path: String,
    pub kind: String,
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::RefCell;
    use std::time::{SystemTime, UNIX_EPOCH};

    const REPORT: &str = r#"{
        "protocol":{"name":"orcan-studio","version":1,"methods":["probe"]},
        "sandbox":{"version":"4.0.0"},
        "host":{"os":"linux","architecture":"x86_64"},
        "paths":{"home":"/home/user/.config/orcan","data":"/home/user/.config/orcan","projects_root":"/home/user/.config/orcan/sandbox","workspace_metadata_root":"/home/user/.config/orcan/workspaces","managed_worktrees_root":"/home/user/.config/orcan/sandbox/.worktrees"},
        "capabilities":{"docker":true,"git":true,"managed_projects":true,"live_reconcile":true},
        "runtime":{"config":"present","generated":"present","docker":{"available":true,"image":{"name":"orcan:latest","present":true},"container":{"name":"orcan-1","state":"running"}}},
        "context":{"configuration":{"state":"present","revision":"abc"},"paths":{"workspace_metadata_root":"/home/user/.config/orcan/workspaces","managed_worktrees_root":"/home/user/.config/orcan/sandbox/.worktrees"},"workspaces":[],"managed_projects":[]}
    }"#;

    struct FakeRunner {
        requests: RefCell<Vec<ProcessRequest>>,
    }

    impl FakeRunner {
        fn new() -> Self {
            Self {
                requests: RefCell::new(Vec::new()),
            }
        }
    }

    impl ProcessRunner for FakeRunner {
        fn run(&self, request: &ProcessRequest) -> Result<ProcessOutput, StudioError> {
            self.requests.borrow_mut().push(request.clone());
            Ok(ProcessOutput {
                success: true,
                stdout: REPORT.to_owned(),
                stderr: String::new(),
            })
        }
    }

    #[test]
    fn local_probe_uses_the_installed_orcan_binary() {
        let runner = FakeRunner::new();
        let report = Target::Local.probe(&runner).expect("probe succeeds");

        assert_eq!(report.host.os, "linux");
        assert_eq!(
            runner.requests.borrow()[0],
            ProcessRequest::new("orcan", &["studio", "probe", "--json"])
        );
    }

    #[test]
    fn wsl_probe_stays_inside_the_selected_distribution() {
        let request = Target::Wsl2 {
            distribution: "Ubuntu-24.04".to_owned(),
        }
        .probe_request()
        .expect("valid WSL target");

        assert_eq!(request.program, "wsl.exe");
        assert_eq!(
            request.arguments,
            [
                "--distribution",
                "Ubuntu-24.04",
                "--exec",
                "orcan",
                "studio",
                "probe",
                "--json",
            ]
        );
    }

    #[test]
    fn ssh_probe_uses_batch_mode_and_the_fixed_protocol_command() {
        let request = Target::Ssh {
            destination: "build-host".to_owned(),
        }
        .probe_request()
        .expect("valid SSH target");

        assert_eq!(request.program, "ssh");
        assert_eq!(
            request.arguments,
            [
                "-o",
                "BatchMode=yes",
                "--",
                "build-host",
                "orcan",
                "studio",
                "probe",
                "--json",
            ]
        );
    }

    #[test]
    fn targets_reject_whitespace_in_user_controlled_identifiers() {
        let error = Target::Ssh {
            destination: "host bad".to_owned(),
        }
        .probe_request()
        .expect_err("whitespace is unsafe in an SSH destination");

        assert!(error.to_string().contains("cannot contain whitespace"));
    }

    #[test]
    fn profile_store_persists_only_reconnect_metadata() {
        let filename = format!(
            "orcan-studio-profiles-{}.json",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("clock after Unix epoch")
                .as_nanos()
        );
        let path = std::env::temp_dir().join(filename);
        let store = ProfileStore::new(&path);
        let profile = ConnectionProfile {
            id: "work-ssh".to_owned(),
            name: "Work server".to_owned(),
            target: Target::Ssh {
                destination: "work-server".to_owned(),
            },
            ssh: SshProfileOptions {
                username: Some("developer".to_owned()),
                authentication: SshAuthentication::PrivateKey {
                    path: "/home/developer/.ssh/id_ed25519".to_owned(),
                    has_passphrase: true,
                },
            },
        };

        store.upsert(profile.clone()).expect("profile saves");
        assert_eq!(store.list().expect("profile loads"), vec![profile]);
        let persisted = fs::read_to_string(&path).expect("profile document reads");
        assert!(persisted.contains("id_ed25519"));
        // Only the fact that a vault entry exists is profile metadata; a secret
        // such as this must never be serializable through ConnectionProfile.
        assert!(!persisted.contains("super-secret-passphrase"));
        store.delete("work-ssh").expect("profile deletes");
        assert!(store.list().expect("empty profile list").is_empty());
        fs::remove_file(path).expect("test profile store is removed");
    }

    #[test]
    fn profile_rejects_ssh_password_options_for_a_local_target() {
        let profile = ConnectionProfile {
            id: "local".to_owned(),
            name: "Local".to_owned(),
            target: Target::Local,
            ssh: SshProfileOptions {
                username: Some("developer".to_owned()),
                authentication: SshAuthentication::Password,
            },
        };

        assert!(profile.validate().is_err());
    }

    #[test]
    fn native_ssh_authentication_requires_a_username() {
        let profile = ConnectionProfile {
            id: "remote".to_owned(),
            name: "Remote".to_owned(),
            target: Target::Ssh {
                destination: "remote.example".to_owned(),
            },
            ssh: SshProfileOptions {
                username: None,
                authentication: SshAuthentication::Password,
            },
        };

        assert!(profile.validate().is_err());
    }

    #[test]
    fn approved_plan_becomes_a_queued_job_but_blocked_plan_cannot_run() {
        let plan = OperationPlan {
            id: "parent-update".to_owned(),
            operation: "parent_update".to_owned(),
            summary: "Fast-forward parent".to_owned(),
            changes: vec!["git pull --ff-only".to_owned()],
            blockers: vec![],
        };
        assert_eq!(
            plan.approved_job().expect("ready plan").state,
            JobState::Queued
        );
        let blocked = OperationPlan {
            blockers: vec!["dirty checkout".to_owned()],
            ..plan
        };
        assert!(blocked.approved_job().is_err());
    }
}
