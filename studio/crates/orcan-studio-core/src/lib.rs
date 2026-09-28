//! Transport-neutral connection layer for Orcan Studio.
//!
//! The desktop UI never constructs a shell command. It selects a target and
//! asks this crate to invoke the fixed Orcan Studio protocol endpoint.

use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
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

/// Container lifecycle actions Studio may run; start and restart replay the
/// flags of the last `orcan up` through `orcan up --resume`.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RuntimeAction {
    Start,
    Stop,
    Restart,
}

/// Workspace membership changes Studio plans before applying.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MembershipAction {
    Attach,
    Detach,
}

pub fn sync_args() -> Vec<String> {
    vec!["sync".to_owned()]
}

pub fn runtime_args(action: RuntimeAction) -> Vec<String> {
    match action {
        RuntimeAction::Stop => vec!["down".to_owned()],
        RuntimeAction::Start | RuntimeAction::Restart => {
            vec!["up".to_owned(), "--resume".to_owned()]
        }
    }
}

/// `orcan studio settings` arguments; Orcan resolves its own config path.
pub fn membership_args(
    action: MembershipAction,
    workspace: &str,
    project: &str,
    apply: bool,
) -> Result<Vec<String>, StudioError> {
    if workspace.is_empty()
        || workspace.len() > 64
        || !workspace
            .chars()
            .all(|character| character.is_ascii_alphanumeric() || "._-".contains(character))
    {
        return Err(StudioError::InvalidTarget(
            "workspace names use letters, digits, dots, hyphens, or underscores".to_owned(),
        ));
    }
    if !project.starts_with('/') || project.chars().any(char::is_control) {
        return Err(StudioError::InvalidTarget(
            "project must be an absolute path on the Enclave".to_owned(),
        ));
    }
    let mode = match (action, apply) {
        (MembershipAction::Attach, false) => "project-add-plan",
        (MembershipAction::Attach, true) => "project-add-apply",
        (MembershipAction::Detach, false) => "project-detach-plan",
        (MembershipAction::Detach, true) => "project-detach-apply",
    };
    let mut args: Vec<String> = [
        "studio",
        "settings",
        mode,
        "--workspace",
        workspace,
        "--project",
        project,
    ]
    .map(str::to_owned)
    .to_vec();
    if apply {
        args.push("--yes".to_owned());
    }
    Ok(args)
}

/// Quotes an argument for the remote POSIX shell that SSH runs commands in.
fn shell_word(value: &str) -> String {
    if !value.is_empty()
        && value
            .chars()
            .all(|character| character.is_ascii_alphanumeric() || "._/@:=+-".contains(character))
    {
        value.to_owned()
    } else {
        format!("'{}'", value.replace('\'', "'\\''"))
    }
}

/// The command line an SSH session runs for `orcan <args>`.
pub fn remote_orcan_command(args: &[String]) -> String {
    std::iter::once("orcan".to_owned())
        .chain(args.iter().map(|argument| shell_word(argument)))
        .collect::<Vec<_>>()
        .join(" ")
}

impl Target {
    pub fn orcan_request(&self, args: &[String]) -> Result<ProcessRequest, StudioError> {
        let mut arguments: Vec<String> = match self {
            Self::Local => vec![],
            Self::Wsl2 { distribution } => {
                validate_identifier("WSL distribution", distribution)?;
                ["--distribution", distribution, "--exec", "orcan"]
                    .map(str::to_owned)
                    .to_vec()
            }
            Self::Ssh { destination } => {
                validate_identifier("SSH destination", destination)?;
                ["-o", "BatchMode=yes", "--", destination]
                    .map(str::to_owned)
                    .to_vec()
            }
        };
        match self {
            Self::Ssh { .. } => arguments.push(remote_orcan_command(args)),
            _ => arguments.extend(args.iter().cloned()),
        }
        Ok(ProcessRequest {
            program: match self {
                Self::Local => "orcan",
                Self::Wsl2 { .. } => "wsl.exe",
                Self::Ssh { .. } => "ssh",
            }
            .to_owned(),
            arguments,
        })
    }

    /// Runs `orcan <args>` on this target and fails with its stderr.
    pub fn run_orcan<R: ProcessRunner>(
        &self,
        runner: &R,
        args: &[String],
    ) -> Result<ProcessOutput, StudioError> {
        let request = self.orcan_request(args)?;
        let output = runner.run(&request)?;
        if output.success {
            Ok(output)
        } else {
            // Orcan's JSON endpoints report refusals on stdout.
            let stderr = if output.stderr.trim().is_empty() {
                output.stdout
            } else {
                output.stderr
            };
            Err(StudioError::CommandFailed {
                command: request.display(),
                stderr,
            })
        }
    }

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

fn validate_record(id: &str, name: &str) -> Result<(), StudioError> {
    if id.is_empty()
        || !id.chars().all(|character| {
            character.is_ascii_alphanumeric() || character == '-' || character == '_'
        })
    {
        return Err(StudioError::InvalidProfile(
            "id must contain only ASCII letters, digits, hyphens, or underscores".to_owned(),
        ));
    }
    if name.trim().is_empty() {
        return Err(StudioError::InvalidProfile(
            "name cannot be empty".to_owned(),
        ));
    }
    Ok(())
}

/// Proof of identity (a key file or a password) that several profiles can
/// share; the profile supplies the user. Secrets live in the operating system
/// credential vault under [`SshCredential::vault_owner`].
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct SshCredential {
    pub id: String,
    pub name: String,
    pub authentication: SshAuthentication,
}

impl SshCredential {
    pub fn validate(&self) -> Result<(), StudioError> {
        validate_record(&self.id, &self.name)?;
        match &self.authentication {
            SshAuthentication::PrivateKey { path, .. } if path.is_empty() => Err(
                StudioError::InvalidProfile("private key path cannot be empty".to_owned()),
            ),
            SshAuthentication::Agent => Err(StudioError::InvalidProfile(
                "the SSH agent needs no saved credential".to_owned(),
            )),
            _ => Ok(()),
        }
    }

    pub fn vault_owner(&self) -> String {
        format!("credential:{}", self.id)
    }
}

fn validate_ssh_options(ssh: &SshProfileOptions) -> Result<(), StudioError> {
    match &ssh.authentication {
        SshAuthentication::PrivateKey { path, .. } => {
            if path.is_empty() {
                return Err(StudioError::InvalidProfile(
                    "private key path cannot be empty".to_owned(),
                ));
            }
            let username = ssh.username.as_deref().ok_or_else(|| {
                StudioError::InvalidProfile(
                    "username is required for native private-key SSH".to_owned(),
                )
            })?;
            validate_identifier("SSH username", username)
        }
        SshAuthentication::Password => {
            let username = ssh.username.as_deref().ok_or_else(|| {
                StudioError::InvalidProfile(
                    "username is required for native password SSH".to_owned(),
                )
            })?;
            validate_identifier("SSH username", username)
        }
        SshAuthentication::Agent => {
            if let Some(username) = &ssh.username {
                validate_identifier("SSH username", username)?;
            }
            Ok(())
        }
    }
}

/// A reconnectable target stored by Studio. It intentionally contains no
/// passwords, private keys, passphrases, or SSH agent material.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct ConnectionProfile {
    pub id: String,
    pub name: String,
    pub target: Target,
    /// Inline SSH options, kept for profiles saved before shared credentials.
    #[serde(default)]
    pub ssh: SshProfileOptions,
    /// Shared [`SshCredential`] used with `ssh.username` instead of
    /// `ssh.authentication` when set.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub credential_id: Option<String>,
}

impl ConnectionProfile {
    pub fn validate(&self) -> Result<(), StudioError> {
        validate_record(&self.id, &self.name)?;
        self.target.probe_request().map(|_| ())?;
        if self.credential_id.is_some() {
            return match (&self.target, &self.ssh) {
                (
                    Target::Ssh { .. },
                    SshProfileOptions {
                        username: Some(username),
                        authentication: SshAuthentication::Agent,
                    },
                ) => validate_identifier("SSH username", username),
                (Target::Ssh { .. }, _) => Err(StudioError::InvalidProfile(
                    "a profile with a shared credential needs a username and no inline authentication"
                        .to_owned(),
                )),
                _ => Err(StudioError::InvalidProfile(
                    "shared credentials require an SSH target".to_owned(),
                )),
            };
        }
        match (&self.target, &self.ssh.authentication) {
            (Target::Ssh { .. }, _) => validate_ssh_options(&self.ssh),
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
    #[serde(default)]
    credentials: Vec<SshCredential>,
}

/// SSH options a probe should use, and the vault entry that holds their secret.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ResolvedSsh {
    pub vault_owner: String,
    pub ssh: SshProfileOptions,
}

impl ProfileStore {
    pub fn new(path: impl Into<PathBuf>) -> Self {
        Self { path: path.into() }
    }

    pub fn list(&self) -> Result<Vec<ConnectionProfile>, StudioError> {
        Ok(self.read()?.profiles)
    }

    pub fn list_credentials(&self) -> Result<Vec<SshCredential>, StudioError> {
        Ok(self.read()?.credentials)
    }

    pub fn upsert_credential(&self, credential: SshCredential) -> Result<(), StudioError> {
        credential.validate()?;
        let mut document = self.read()?;
        document
            .credentials
            .retain(|existing| existing.id != credential.id);
        document.credentials.push(credential);
        document
            .credentials
            .sort_by(|left, right| left.name.cmp(&right.name));
        self.write(&document)
    }

    /// Removes a credential that no profile references any more.
    pub fn delete_credential(&self, id: &str) -> Result<(), StudioError> {
        let mut document = self.read()?;
        let users: Vec<&str> = document
            .profiles
            .iter()
            .filter(|profile| profile.credential_id.as_deref() == Some(id))
            .map(|profile| profile.name.as_str())
            .collect();
        if !users.is_empty() {
            return Err(StudioError::InvalidProfile(format!(
                "credential is used by: {}",
                users.join(", ")
            )));
        }
        document
            .credentials
            .retain(|credential| credential.id != id);
        self.write(&document)
    }

    /// Resolves the SSH options for a saved profile, or for an unsaved
    /// `username` + shared credential pair (connection test before saving).
    pub fn resolve_ssh(
        &self,
        profile_id: Option<&str>,
        credential_id: Option<&str>,
        username: Option<&str>,
    ) -> Result<Option<(Option<ConnectionProfile>, ResolvedSsh)>, StudioError> {
        let document = self.read()?;
        let profile = match profile_id {
            Some(id) => Some(
                document
                    .profiles
                    .iter()
                    .find(|profile| profile.id == id)
                    .cloned()
                    .ok_or_else(|| {
                        StudioError::InvalidProfile("selected profile no longer exists".to_owned())
                    })?,
            ),
            None => None,
        };
        let credential_id = credential_id.or(profile
            .as_ref()
            .and_then(|profile| profile.credential_id.as_deref()));
        let resolved = match (credential_id, &profile) {
            (Some(id), _) => {
                let credential = document
                    .credentials
                    .iter()
                    .find(|credential| credential.id == id)
                    .ok_or_else(|| {
                        StudioError::InvalidProfile(
                            "selected credential no longer exists".to_owned(),
                        )
                    })?;
                let username = username.map(str::to_owned).or_else(|| {
                    profile
                        .as_ref()
                        .and_then(|profile| profile.ssh.username.clone())
                });
                ResolvedSsh {
                    vault_owner: credential.vault_owner(),
                    ssh: SshProfileOptions {
                        username,
                        authentication: credential.authentication.clone(),
                    },
                }
            }
            (None, Some(profile)) => ResolvedSsh {
                vault_owner: profile.id.clone(),
                ssh: profile.ssh.clone(),
            },
            (None, None) => return Ok(None),
        };
        Ok(Some((profile, resolved)))
    }

    pub fn upsert(&self, profile: ConnectionProfile) -> Result<(), StudioError> {
        profile.validate()?;
        let mut document = self.read()?;
        if let Some(id) = &profile.credential_id
            && !document
                .credentials
                .iter()
                .any(|credential| &credential.id == id)
        {
            return Err(StudioError::InvalidProfile(
                "selected credential no longer exists".to_owned(),
            ));
        }
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
                credentials: Vec::new(),
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
        for credential in &document.credentials {
            credential.validate()?;
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
    #[serde(default)]
    pub resources: Resources,
    #[serde(default)]
    pub launch: Launch,
}

/// Flags of the last `orcan up`, replayed by `RuntimeAction::Start`/`Restart`.
#[derive(Clone, Debug, Default, Deserialize, Serialize)]
pub struct Launch {
    pub recorded: bool,
    #[serde(default)]
    pub docker: bool,
    #[serde(default)]
    pub git: bool,
    pub network: Option<String>,
    #[serde(default)]
    pub ttyd: bool,
    #[serde(default)]
    pub ttyd_auth: bool,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
pub struct Resources {
    pub cpus: Option<serde_json::Value>,
    pub memory: Option<String>,
    pub shm_size: Option<String>,
    pub tmpfs_size: Option<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Docker {
    pub available: bool,
    pub image: Image,
    pub container: Container,
    /// Agent CLIs baked into the selected Sandbox image; Orcan does not pick models.
    #[serde(default)]
    pub agents: BTreeMap<String, bool>,
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
        "runtime":{"config":"present","generated":"present","docker":{"available":true,"image":{"name":"orcan:latest","present":true},"container":{"name":"orcan-1","state":"running"},"agents":{"codex":true,"claude":false}},"resources":{"cpus":4,"memory":"8g"},"launch":{"recorded":true,"git":true,"network":null,"ttyd":true}},
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
        assert_eq!(report.runtime.resources.memory.as_deref(), Some("8g"));
        assert_eq!(report.runtime.docker.agents.get("codex"), Some(&true));
        assert!(report.runtime.launch.git && !report.runtime.launch.ttyd_auth);
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
    fn runtime_actions_replay_the_last_up_flags() {
        let target = Target::Ssh {
            destination: "build-host".to_owned(),
        };
        let restart = target
            .orcan_request(&runtime_args(RuntimeAction::Restart))
            .expect("valid");
        assert_eq!(
            restart.arguments,
            [
                "-o",
                "BatchMode=yes",
                "--",
                "build-host",
                "orcan up --resume"
            ]
        );
        assert_eq!(
            Target::Local
                .orcan_request(&runtime_args(RuntimeAction::Stop))
                .expect("valid"),
            ProcessRequest::new("orcan", &["down"])
        );
        assert_eq!(
            Target::Wsl2 {
                distribution: "Ubuntu".to_owned()
            }
            .orcan_request(&runtime_args(RuntimeAction::Start))
            .expect("valid")
            .arguments,
            [
                "--distribution",
                "Ubuntu",
                "--exec",
                "orcan",
                "up",
                "--resume"
            ]
        );
    }

    #[test]
    fn membership_changes_are_validated_and_shell_quoted_for_ssh() {
        let args = membership_args(MembershipAction::Attach, "org-dev", "/srv/My Repo's", true)
            .expect("valid membership change");
        assert_eq!(
            remote_orcan_command(&args),
            "orcan studio settings project-add-apply --workspace org-dev --project '/srv/My Repo'\\''s' --yes"
        );
        assert!(membership_args(MembershipAction::Detach, "a;rm", "/srv/x", false).is_err());
        assert!(membership_args(MembershipAction::Detach, "dev", "relative/x", false).is_err());
        assert!(membership_args(MembershipAction::Detach, "dev", "/srv/x\nid", false).is_err());
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
            credential_id: None,
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
    fn profiles_share_a_credential_that_cannot_be_deleted_while_used() {
        let path = std::env::temp_dir().join(format!(
            "orcan-studio-credentials-{}.json",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("clock after Unix epoch")
                .as_nanos()
        ));
        let store = ProfileStore::new(&path);
        let credential = SshCredential {
            id: "work-key".to_owned(),
            name: "Work key".to_owned(),
            authentication: SshAuthentication::Password,
        };
        let profile = |id: &str, host: &str| ConnectionProfile {
            id: id.to_owned(),
            name: id.to_owned(),
            target: Target::Ssh {
                destination: host.to_owned(),
            },
            ssh: SshProfileOptions {
                username: Some(format!("{id}-user")),
                authentication: SshAuthentication::Agent,
            },
            credential_id: Some("work-key".to_owned()),
        };

        assert!(
            store.upsert(profile("a", "host-a")).is_err(),
            "credential must exist"
        );
        store
            .upsert_credential(credential.clone())
            .expect("credential saves");
        store
            .upsert(profile("a", "host-a"))
            .expect("first profile saves");
        store
            .upsert(profile("b", "host-b"))
            .expect("second profile reuses it");

        let (_, resolved) = store
            .resolve_ssh(Some("b"), None, None)
            .expect("resolves")
            .expect("has SSH options");
        assert_eq!(resolved.vault_owner, "credential:work-key");
        assert_eq!(resolved.ssh.username.as_deref(), Some("b-user"));
        assert_eq!(resolved.ssh.authentication, SshAuthentication::Password);
        let (_, unsaved) = store
            .resolve_ssh(None, Some("work-key"), Some("tester"))
            .expect("resolves")
            .expect("has SSH options");
        assert_eq!(unsaved.ssh.username.as_deref(), Some("tester"));
        let error = store
            .delete_credential("work-key")
            .expect_err("still in use");
        assert!(error.to_string().contains("a, b"));

        store.delete("a").expect("profile deletes");
        store.delete("b").expect("profile deletes");
        store
            .delete_credential("work-key")
            .expect("unused credential deletes");
        fs::remove_file(path).expect("test store is removed");
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
            credential_id: None,
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
            credential_id: None,
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
