//! Native terminal launch for local, WSL and system-SSH profiles.
use super::*;

fn scoped(instance: &Option<String>, mut args: Vec<String>) -> Result<Vec<String>, String> {
    if let Some(instance) = instance {
        enclave::validate_instance(instance)?;
        args.splice(0..0, ["--instance".into(), instance.clone()]);
    }
    Ok(args)
}

pub(super) fn attach_script(
    instance: &Option<String>,
    workspace: &str,
    host_id: Option<&str>,
    container_id: Option<&str>,
) -> Result<String, String> {
    if workspace.is_empty()
        || workspace.starts_with('-')
        || !workspace
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || "._-".contains(c))
    {
        return Err("Select a valid workspace name".into());
    }
    let attach = remote_orcan_command(&scoped(instance, vec!["attach".into(), workspace.into()])?);
    match (host_id, container_id) {
        (Some(host), Some(container)) => {
            let verify = remote_orcan_command(&scoped(
                instance,
                vec![
                    "studio".into(),
                    "target".into(),
                    "verify".into(),
                    "--expected-host-id".into(),
                    host.into(),
                    "--expected-id".into(),
                    container.into(),
                ],
            )?);
            Ok(format!("({verify}) && ({attach})"))
        }
        (None, None) => Ok(attach),
        _ => Err("Select both host and container UUIDs".into()),
    }
}

fn wsl_command(distribution: Option<&str>, argv: Vec<String>) -> Result<Vec<String>, String> {
    let mut command = vec!["wsl.exe".into()];
    if let Some(distribution) = distribution {
        validate_wsl_distribution(distribution)?;
        command.extend(["--distribution".into(), distribution.into()]);
    }
    command.push("--exec".into());
    command.extend(argv);
    Ok(command)
}

#[cfg(any(windows, test))]
fn wsl_terminal_command(argv: Vec<String>) -> Result<Vec<String>, String> {
    match argv.first().map(String::as_str) {
        Some("wsl.exe") => Ok(argv),
        Some("ssh") => wsl_command(None, argv),
        _ => Err("WSL terminal requires a WSL2 or SSH profile".into()),
    }
}

#[cfg(any(windows, test))]
fn windows_terminal_args(argv: &[String]) -> Vec<String> {
    // wt treats even quoted semicolons as action separators; escape for its parser.
    ["-w", "new", "new-tab"]
        .map(str::to_owned)
        .into_iter()
        .chain(argv.iter().map(|arg| arg.replace(';', "\\;")))
        .collect()
}

fn ssh_command(
    destination: String,
    username: Option<&str>,
    script: String,
) -> Result<Vec<String>, String> {
    if destination.is_empty()
        || destination.starts_with('-')
        || !destination
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || "._-@[]:".contains(c))
    {
        return Err("Use a hostname, IP address or SSH alias for Attach".into());
    }
    let mut argv = vec!["ssh".into(), "-tt".into()];
    if let Some(username) = username {
        if username.is_empty()
            || username.starts_with('-')
            || !username
                .chars()
                .all(|c| c.is_ascii_alphanumeric() || "._-".contains(c))
        {
            return Err("Use a valid SSH username for Attach".into());
        }
        argv.extend(["-l".into(), username.into()]);
    }
    argv.extend(["--".into(), destination, script]);
    Ok(argv)
}

pub(super) async fn open(
    enclave: EnclaveInput,
    workspace: String,
    launcher: TerminalLauncher,
    host_id: Option<String>,
    container_id: Option<String>,
    state: tauri::State<'_, ProfileState>,
) -> Result<(), String> {
    let report = probe(enclave.clone(), state.clone()).await?;
    if let (Some(host), Some(container)) = (&host_id, &container_id) {
        groups::matches(&report, host, container)?;
    } else if host_id.is_some() || container_id.is_some() {
        return Err("Select both target UUIDs".into());
    }
    enclave::verify_container_owner(&enclave, &report, &state).await?;
    if report.runtime.docker.container.state != "running" {
        return Err("Start the existing container explicitly before Attach".into());
    }
    if !report
        .context
        .workspaces
        .iter()
        .any(|ws| ws.name == workspace)
    {
        return Err("Workspace is missing; refresh before Attach".into());
    }
    let script = attach_script(
        &enclave.instance,
        &workspace,
        host_id.as_deref(),
        container_id.as_deref(),
    )?;
    let argv = match &enclave.target {
        TargetInput::Local => {
            if cfg!(windows) {
                return Err("Choose a WSL profile for local Windows containers".into());
            }
            vec!["bash".into(), "-lc".into(), script]
        }
        TargetInput::Wsl2 { distribution } => {
            validate_wsl_distribution(distribution)?;
            if !cfg!(windows) {
                return Err("WSL terminal launch requires Windows".into());
            }
            wsl_command(
                Some(distribution),
                vec!["bash".into(), "-lc".into(), script],
            )?
        }
        TargetInput::Ssh { .. } => {
            let resolved = state
                .0
                .lock()
                .map_err(|_| "Profile store unavailable")?
                .resolve_ssh(
                    enclave.profile_id.as_deref(),
                    enclave.credential_id.as_deref(),
                    enclave.username.as_deref(),
                )
                .map_err(|error| error.to_string())?
                .ok_or("Select a saved SSH profile")?;
            // Probe can use the vault; the interactive terminal authenticates independently.
            // Pass only its destination and username, never passwords or private keys.
            let profile = resolved.0.ok_or("Select a saved SSH profile")?;
            let Target::Ssh { destination } = profile.target else {
                return Err("Select an SSH profile".into());
            };
            ssh_command(destination, resolved.1.ssh.username.as_deref(), script)?
        }
    };
    launch(argv, launcher)
}

fn launch(argv: Vec<String>, launcher: TerminalLauncher) -> Result<(), String> {
    #[cfg(windows)]
    let mut command = match launcher {
        TerminalLauncher::Wsl => {
            use std::os::windows::process::CommandExt;
            let argv = wsl_terminal_command(argv)?;
            let mut c = Command::new("wsl.exe");
            c.creation_flags(0x0000_0010).args(&argv[1..]);
            c
        }
        TerminalLauncher::WindowsTerminal => {
            let mut c = Command::new("wt.exe");
            c.args(windows_terminal_args(&argv));
            c
        }
        TerminalLauncher::PowerShell | TerminalLauncher::CommandPrompt => {
            use std::os::windows::process::CommandExt;
            let script = format!(
                "& {}",
                argv.iter()
                    .map(|arg| format!("'{}'", arg.replace('\'', "''")))
                    .collect::<Vec<_>>()
                    .join(" ")
            );
            let mut c = Command::new(if matches!(launcher, TerminalLauncher::CommandPrompt) {
                "cmd.exe"
            } else {
                "powershell.exe"
            });
            c.creation_flags(0x0000_0010);
            if matches!(launcher, TerminalLauncher::CommandPrompt) {
                c.args(["/K", "powershell.exe", "-NoProfile", "-Command", &script]);
            } else {
                c.args(["-NoExit", "-Command", &script]);
            }
            c
        }
        _ => return Err("Choose a Windows terminal".into()),
    };
    #[cfg(target_os = "macos")]
    let mut command = match launcher {
        TerminalLauncher::MacTerminal => {
            let shell = format!(
                "exec {}",
                argv.iter()
                    .map(|arg| shell_quote(arg))
                    .collect::<Vec<_>>()
                    .join(" ")
            );
            let mut c = Command::new("/usr/bin/osascript");
            c.args([
                "-e",
                &format!(
                    "tell application \"Terminal\" to do script {}",
                    serde_json::to_string(&shell).map_err(|error| error.to_string())?
                ),
            ]);
            c
        }
        _ => return Err("Choose Terminal on macOS".into()),
    };
    #[cfg(all(unix, not(target_os = "macos")))]
    let mut command = match launcher {
        TerminalLauncher::LinuxTerminal => {
            let mut c = Command::new("x-terminal-emulator");
            c.arg("-e").args(&argv);
            c
        }
        _ => return Err("Choose Default Linux terminal".into()),
    };
    command
        .spawn()
        .map_err(|error| format!("Could not open terminal: {error}"))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn wsl_attach_and_remote_ssh_keep_transport_and_script_intact() {
        let script = attach_script(&Some("tester".into()), "review", None, None).unwrap();
        let local = wsl_command(
            Some("Ubuntu-24.04"),
            vec!["bash".into(), "-lc".into(), script.clone()],
        )
        .unwrap();
        assert_eq!(
            &local[..6],
            &[
                "wsl.exe",
                "--distribution",
                "Ubuntu-24.04",
                "--exec",
                "bash",
                "-lc"
            ]
        );
        assert_eq!(local[6], script);
        assert_eq!(wsl_terminal_command(local.clone()).unwrap(), local);
        let remote = ssh_command("server-alias".into(), Some("developer"), script.clone()).unwrap();
        assert_eq!(
            &remote[..6],
            &["ssh", "-tt", "-l", "developer", "--", "server-alias"]
        );
        assert_eq!(remote[6], script);
        let remote_wsl = wsl_terminal_command(remote.clone()).unwrap();
        assert_eq!(&remote_wsl[..2], &["wsl.exe", "--exec"]);
        assert_eq!(&remote_wsl[2..], remote);
        assert!(wsl_terminal_command(vec!["bash".into()]).is_err());
        assert!(ssh_command("-oProxyCommand=bad".into(), None, script.clone()).is_err());
        assert!(ssh_command("server".into(), Some("bad user"), script).is_err());
    }

    #[test]
    fn windows_terminal_does_not_split_the_attach_script_into_tabs() {
        let script = attach_script(
            &Some("tester".into()),
            "review",
            Some("host"),
            Some("container"),
        )
        .unwrap();
        assert!(script.contains(';'));
        let argv = wsl_command(
            Some("Ubuntu"),
            vec!["bash".into(), "-lc".into(), script.clone()],
        )
        .unwrap();
        let args = windows_terminal_args(&argv);
        assert_eq!(&args[..3], &["-w", "new", "new-tab"]);
        // Windows Terminal removes this escaping before launching wsl.exe.
        assert_eq!(args.last().unwrap().replace("\\;", ";"), script);
        assert_eq!(
            args.last().unwrap().matches("\\;").count(),
            script.matches(';').count()
        );
    }

    #[test]
    fn target_check_precedes_attach_and_both_commands_use_the_instance() {
        let script = attach_script(
            &Some("tester".into()),
            "review",
            Some("host"),
            Some("container"),
        )
        .unwrap();
        assert!(script.contains("verify"));
        assert!(script.find("verify").unwrap() < script.find("attach").unwrap());
        assert_eq!(script.matches("--instance tester").count(), 2);
        assert!(attach_script(&None, "a; touch /tmp/test", None, None).is_err());
        assert!(attach_script(&None, "valid", Some("host"), None).is_err());
    }
    #[cfg(unix)]
    #[test]
    fn failed_terminal_target_verification_never_attaches() {
        let temp = tempfile::tempdir().unwrap();
        let marker = temp.path().join("attached");
        let script = attach_script(
            &Some("tester".into()),
            "review",
            Some("host"),
            Some("container"),
        )
        .unwrap();
        let shell = format!(
            "orcan() {{ case \"$*\" in *verify*) return 1 ;; *attach*) touch {} ;; esac; }}; {script}",
            shell_quote(marker.to_str().unwrap())
        );
        let status = Command::new("bash").args(["-c", &shell]).status().unwrap();
        assert!(!status.success());
        assert!(!marker.exists());
    }
}
