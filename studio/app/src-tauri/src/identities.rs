//! Installation-adjacent, versioned identity templates. Profiles/vault stay separate.
use fs2::FileExt;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};
use uuid::Uuid;

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub(crate) struct Identity {
    pub id: String,
    pub version: u32,
    pub name: String,
    pub description: String,
    pub instructions: String,
}

#[derive(Serialize, Deserialize)]
struct Metadata {
    id: String,
    version: u32,
    name: String,
    description: String,
}

impl Identity {
    fn validate(&self) -> Result<(), String> {
        if Uuid::parse_str(&self.id)
            .map_err(|_| "Invalid identity UUID")?
            .to_string()
            != self.id
        {
            return Err("Invalid identity UUID".into());
        }
        if self.version == 0 || self.version > i32::MAX as u32 {
            return Err("Invalid identity version".into());
        }
        if self.name.trim().is_empty()
            || self.name.len() > 120
            || self.name.contains(['\n', '\r', '\0'])
        {
            return Err("Identity name must be 1–120 bytes on one line".into());
        }
        if self.description.len() > 1000 || self.description.contains('\0') {
            return Err("Description must be at most 1000 bytes".into());
        }
        if self.instructions.trim().is_empty()
            || self.instructions.len() > 32768
            || self.instructions.contains('\0')
        {
            return Err("Markdown instructions must be 1–32768 bytes".into());
        }
        Ok(())
    }
}

fn error(error: impl std::fmt::Display) -> String {
    format!("Identity storage: {error}")
}

pub(crate) fn data_root(executable: &Path) -> Result<PathBuf, String> {
    let mut parent = executable
        .parent()
        .ok_or("Application location unavailable")?;
    if let Some(bundle) = executable
        .ancestors()
        .find(|path| path.extension().is_some_and(|extension| extension == "app"))
    {
        parent = bundle
            .parent()
            .ok_or("Application installation location unavailable")?;
    }
    Ok(parent.join("studio-data"))
}

fn safe_dir(path: &Path) -> Result<(), String> {
    if path
        .symlink_metadata()
        .is_ok_and(|meta| meta.file_type().is_symlink())
    {
        return Err("Identity storage cannot use symlink directories".into());
    }
    fs::create_dir_all(path).map_err(error)
}

pub(crate) fn root() -> Result<PathBuf, String> {
    // AppImage runs the binary from a temporary read-only mount.
    let executable = std::env::var_os("APPIMAGE")
        .map(PathBuf::from)
        .filter(|path| path.is_absolute())
        .unwrap_or(std::env::current_exe().map_err(error)?);
    let root = data_root(&executable)?;
    safe_dir(&root)?;
    Ok(root)
}

fn revision_dir(root: &Path, id: &str, version: u32) -> Result<PathBuf, String> {
    if Uuid::parse_str(id)
        .map_err(|_| "Invalid identity UUID")?
        .to_string()
        != id
        || version == 0
    {
        return Err("Invalid identity reference".into());
    }
    let library = root.join("identities");
    let identity = library.join(id);
    let versions = identity.join("versions");
    for path in [&library, &identity, &versions] {
        if path
            .symlink_metadata()
            .is_ok_and(|meta| meta.file_type().is_symlink())
        {
            return Err("Identity storage cannot use symlinks".into());
        }
    }
    Ok(versions.join(version.to_string()))
}

pub(crate) fn read_at(root: &Path, id: &str, version: u32) -> Result<Identity, String> {
    let directory = revision_dir(root, id, version)?;
    for path in [
        &directory,
        &directory.join("identity.json"),
        &directory.join("instructions.md"),
    ] {
        if path
            .symlink_metadata()
            .map_err(error)?
            .file_type()
            .is_symlink()
        {
            return Err("Identity storage cannot use symlinks".into());
        }
    }
    let metadata: Metadata =
        serde_json::from_str(&fs::read_to_string(directory.join("identity.json")).map_err(error)?)
            .map_err(error)?;
    let identity = Identity {
        id: metadata.id,
        version: metadata.version,
        name: metadata.name,
        description: metadata.description,
        instructions: fs::read_to_string(directory.join("instructions.md")).map_err(error)?,
    };
    identity.validate()?;
    if identity.id != id || identity.version != version {
        return Err("Identity reference does not match its files".into());
    }
    Ok(identity)
}

pub(crate) fn list_at(root: &Path) -> Result<Vec<Identity>, String> {
    let library = root.join("identities");
    safe_dir(&library)?;
    let mut identities = Vec::new();
    for entry in fs::read_dir(library).map_err(error)? {
        let entry = entry.map_err(error)?;
        let id = entry.file_name().to_string_lossy().into_owned();
        if entry.file_type().map_err(error)?.is_symlink()
            || !entry.path().is_dir()
            || Uuid::parse_str(&id).is_err()
        {
            continue;
        }
        let versions = revision_dir(root, &id, 1)?.parent().unwrap().to_path_buf();
        let mut latest = 0;
        for revision in fs::read_dir(versions).map_err(error)? {
            let revision = revision.map_err(error)?;
            if let Ok(version) = revision.file_name().to_string_lossy().parse::<u32>() {
                latest = latest.max(version);
            }
        }
        if latest > 0 {
            identities.push(read_at(root, &id, latest)?);
        }
    }
    identities.sort_by(|a, b| a.name.cmp(&b.name).then(a.id.cmp(&b.id)));
    Ok(identities)
}

pub(crate) fn save_at(
    root: &Path,
    id: Option<String>,
    expected: Option<u32>,
    name: String,
    description: String,
    instructions: String,
) -> Result<Identity, String> {
    safe_dir(root)?;
    let library = root.join("identities");
    safe_dir(&library)?;
    let lock_path = library.join(".lock");
    if lock_path
        .symlink_metadata()
        .is_ok_and(|meta| meta.file_type().is_symlink())
    {
        return Err("Invalid storage lock".into());
    }
    let lock = fs::OpenOptions::new()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .open(lock_path)
        .map_err(error)?;
    lock.try_lock_exclusive()
        .map_err(|_| "Identity library is busy. Retry saving.".to_string())?;
    let (id, version) = match id {
        Some(id) => {
            let latest = list_at(root)?
                .into_iter()
                .find(|item| item.id == id)
                .ok_or("Identity was removed; reload the library")?;
            if expected != Some(latest.version) {
                return Err("Identity changed; reload before editing".into());
            }
            (
                id,
                latest
                    .version
                    .checked_add(1)
                    .ok_or("Identity version exhausted")?,
            )
        }
        None => (Uuid::new_v4().to_string(), 1),
    };
    let identity = Identity {
        id,
        version,
        name: name.trim().into(),
        description,
        instructions,
    };
    identity.validate()?;
    let destination = revision_dir(root, &identity.id, version)?;
    let parent = destination.parent().unwrap();
    safe_dir(&library.join(&identity.id))?;
    safe_dir(parent)?;
    let pending = tempfile::Builder::new()
        .prefix(".pending-")
        .tempdir_in(parent)
        .map_err(error)?;
    let metadata = Metadata {
        id: identity.id.clone(),
        version,
        name: identity.name.clone(),
        description: identity.description.clone(),
    };
    fs::write(
        pending.path().join("identity.json"),
        serde_json::to_string_pretty(&metadata).map_err(error)?,
    )
    .map_err(error)?;
    fs::write(
        pending.path().join("instructions.md"),
        &identity.instructions,
    )
    .map_err(error)?;
    fs::rename(pending.path(), destination).map_err(error)?;
    Ok(identity)
}

#[tauri::command]
pub(crate) fn list_identities() -> Result<serde_json::Value, String> {
    let root = root()?;
    Ok(serde_json::json!({"path": root, "identities": list_at(&root)?}))
}

#[tauri::command]
pub(crate) fn save_identity(
    id: Option<String>,
    expected_version: Option<u32>,
    name: String,
    description: String,
    instructions: String,
) -> Result<Identity, String> {
    save_at(
        &root()?,
        id,
        expected_version,
        name,
        description,
        instructions,
    )
}

#[tauri::command]
pub(crate) fn open_studio_data() -> Result<(), String> {
    let path = root()?;
    let command = if cfg!(target_os = "windows") {
        "explorer.exe"
    } else if cfg!(target_os = "macos") {
        "open"
    } else {
        "xdg-open"
    };
    std::process::Command::new(command)
        .arg(path)
        .spawn()
        .map_err(error)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn revisions_are_immutable_and_stale_edits_fail() {
        let dir = tempfile::tempdir().unwrap();
        let first = save_at(
            dir.path(),
            None,
            None,
            "Tester".into(),
            "Checks".into(),
            "Test changes".into(),
        )
        .unwrap();
        let next = save_at(
            dir.path(),
            Some(first.id.clone()),
            Some(1),
            "Tester".into(),
            "Checks".into(),
            "Test edge cases".into(),
        )
        .unwrap();
        assert_eq!(next.version, 2);
        assert_eq!(read_at(dir.path(), &first.id, 1).unwrap(), first);
        assert_eq!(list_at(dir.path()).unwrap(), vec![next]);
        assert!(
            save_at(
                dir.path(),
                Some(first.id),
                Some(1),
                "Tester".into(),
                "".into(),
                "stale".into()
            )
            .is_err()
        );
        assert!(read_at(dir.path(), "../escape", 1).is_err());
    }
    #[test]
    fn data_is_next_to_installation_outside_macos_bundle() {
        assert_eq!(
            data_root(Path::new("/opt/Studio/studio")).unwrap(),
            Path::new("/opt/Studio/studio-data")
        );
        assert_eq!(
            data_root(Path::new("/Applications/Studio.app/Contents/MacOS/studio")).unwrap(),
            Path::new("/Applications/studio-data")
        );
    }
    #[test]
    fn malformed_markdown_or_metadata_is_not_overwritten() {
        let dir = tempfile::tempdir().unwrap();
        let identity = save_at(
            dir.path(),
            None,
            None,
            "Developer".into(),
            "".into(),
            "Finish tasks".into(),
        )
        .unwrap();
        let file = revision_dir(dir.path(), &identity.id, 1)
            .unwrap()
            .join("identity.json");
        fs::write(&file, "broken").unwrap();
        assert!(list_at(dir.path()).is_err());
        assert_eq!(fs::read_to_string(file).unwrap(), "broken");
    }
}
