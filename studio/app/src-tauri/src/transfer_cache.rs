//! Crash recovery for Studio-owned transfer files. Never sweep the system temp
//! directory: only known files in this user's dedicated cache are eligible.
use fs2::FileExt;
use std::fs::{self, File, OpenOptions};
use std::io;
use std::path::{Path, PathBuf};

#[derive(Clone)]
pub(super) struct TransferCache {
    root: PathBuf,
}

pub(super) struct TransferPayload {
    pub file: tempfile::NamedTempFile,
    // Field order releases file handles before TempDir removes its directory.
    _lease: File,
    _directory: tempfile::TempDir,
}

fn regular_file(path: &Path) -> io::Result<()> {
    if !fs::symlink_metadata(path)?.file_type().is_file() {
        return Err(io::Error::other(
            "Transfer cache contains a non-regular file",
        ));
    }
    Ok(())
}

impl TransferCache {
    pub fn new(root: PathBuf) -> io::Result<Self> {
        let mut builder = fs::DirBuilder::new();
        builder.recursive(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::DirBuilderExt;
            builder.mode(0o700);
        }
        builder.create(&root)?;
        let metadata = fs::symlink_metadata(&root)?;
        if !metadata.file_type().is_dir() {
            return Err(io::Error::other("Transfer cache must be a real directory"));
        }
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            if metadata.permissions().mode() & 0o077 != 0 {
                return Err(io::Error::other(
                    "Transfer cache must have private permissions (700)",
                ));
            }
        }
        let gate = root.join(".gate");
        match OpenOptions::new().write(true).create_new(true).open(&gate) {
            Ok(_) => {}
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => regular_file(&gate)?,
            Err(error) => return Err(error),
        }
        Ok(Self { root })
    }

    // A short cache-wide lock closes the gap between creating a directory and
    // obtaining its lease, including when another Studio starts concurrently.
    fn gate(&self) -> io::Result<File> {
        let path = self.root.join(".gate");
        regular_file(&path)?;
        let gate = OpenOptions::new().read(true).write(true).open(path)?;
        gate.lock_exclusive()?;
        Ok(gate)
    }

    pub fn create(&self) -> io::Result<TransferPayload> {
        let _gate = self.gate()?;
        let directory = tempfile::Builder::new()
            .prefix("transfer-")
            .tempdir_in(&self.root)?;
        let lease = OpenOptions::new()
            .read(true)
            .write(true)
            .create_new(true)
            .open(directory.path().join(".lease"))?;
        lease.lock_exclusive()?;
        let file = tempfile::Builder::new()
            .prefix("payload-")
            .suffix(".tmp")
            .tempfile_in(directory.path())?;
        Ok(TransferPayload {
            file,
            _lease: lease,
            _directory: directory,
        })
    }

    pub fn cleanup(&self) -> io::Result<usize> {
        let _gate = self.gate()?;
        let mut removed = 0;
        for entry in fs::read_dir(&self.root)? {
            let entry = entry?;
            if !entry.file_name().to_string_lossy().starts_with("transfer-")
                || !entry.file_type()?.is_dir()
            {
                continue;
            }
            let directory = entry.path();
            let lease_path = directory.join(".lease");
            if regular_file(&lease_path).is_err() {
                continue;
            }
            let lease = OpenOptions::new()
                .read(true)
                .write(true)
                .open(&lease_path)?;
            if lease.try_lock_exclusive().is_err() {
                continue;
            }
            let mut payloads = Vec::new();
            let mut recognized = true;
            for item in fs::read_dir(&directory)? {
                let item = item?;
                let name = item.file_name();
                let name = name.to_string_lossy();
                if !item.file_type()?.is_file() {
                    recognized = false;
                    break;
                }
                if name == ".lease" {
                    continue;
                }
                if name.starts_with("payload-") && name.ends_with(".tmp") {
                    payloads.push(item.path());
                } else {
                    recognized = false;
                    break;
                }
            }
            if !recognized {
                continue;
            }
            // Exact files only; no recursive deletion or following symlinks.
            for payload in payloads {
                fs::remove_file(payload)?;
            }
            drop(lease);
            fs::remove_file(lease_path)?;
            fs::remove_dir(directory)?;
            removed += 1;
        }
        Ok(removed)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn normal_drop_removes_payload_and_directory() {
        let root = tempfile::tempdir().unwrap();
        let cache = TransferCache::new(root.path().join("transfers")).unwrap();
        let payload = cache.create().unwrap();
        let directory = payload._directory.path().to_owned();
        assert!(payload.file.path().exists());
        drop(payload);
        assert!(!directory.exists());
    }

    #[test]
    fn cleanup_skips_active_transfers_and_removes_crash_leftovers() {
        let root = tempfile::tempdir().unwrap();
        let cache = TransferCache::new(root.path().join("transfers")).unwrap();
        let active = cache.create().unwrap();
        let orphan = cache.create().unwrap();
        let TransferPayload {
            file,
            _lease: lease,
            _directory: directory,
        } = orphan;
        let (_, path) = file.keep().unwrap();
        let directory = directory.keep();
        drop(lease);
        let second_instance = TransferCache::new(cache.root.clone()).unwrap();
        assert_eq!(second_instance.cleanup().unwrap(), 1);
        assert!(!directory.exists());
        assert!(!path.exists());
        assert!(active.file.path().exists());
        assert_eq!(second_instance.cleanup().unwrap(), 0);
    }

    #[test]
    fn cleanup_preserves_unknown_files_and_directories() {
        let root = tempfile::tempdir().unwrap();
        let cache = TransferCache::new(root.path().join("transfers")).unwrap();
        let unknown = cache.root.join("user-file.tmp");
        fs::write(&unknown, "keep").unwrap();
        let directory = cache.root.join("transfer-unrecognized");
        fs::create_dir(&directory).unwrap();
        fs::write(directory.join(".lease"), "").unwrap();
        fs::write(directory.join("notes.txt"), "keep").unwrap();
        assert_eq!(cache.cleanup().unwrap(), 0);
        assert!(unknown.exists());
        assert!(directory.join("notes.txt").exists());
    }

    #[cfg(unix)]
    #[test]
    fn cleanup_does_not_follow_symlinks() {
        use std::os::unix::fs::symlink;
        let root = tempfile::tempdir().unwrap();
        let cache = TransferCache::new(root.path().join("transfers")).unwrap();
        let outside = root.path().join("outside");
        fs::create_dir(&outside).unwrap();
        fs::write(outside.join("valuable"), "keep").unwrap();
        symlink(&outside, cache.root.join("transfer-symlink")).unwrap();
        assert_eq!(cache.cleanup().unwrap(), 0);
        assert!(outside.join("valuable").exists());
        assert!(TransferCache::new(cache.root.join("transfer-symlink")).is_err());
    }

    #[cfg(unix)]
    #[test]
    fn private_permissions_and_symlink_payloads_are_preserved() {
        use std::os::unix::fs::{PermissionsExt, symlink};
        let root = tempfile::tempdir().unwrap();
        let cache = TransferCache::new(root.path().join("transfers")).unwrap();
        let payload = cache.create().unwrap();
        assert_eq!(
            fs::metadata(&cache.root).unwrap().permissions().mode() & 0o777,
            0o700
        );
        assert_eq!(
            payload
                .file
                .as_file()
                .metadata()
                .unwrap()
                .permissions()
                .mode()
                & 0o777,
            0o600
        );
        let TransferPayload {
            file,
            _lease: lease,
            _directory: directory,
        } = payload;
        drop(file);
        let directory = directory.keep();
        drop(lease);
        let outside = root.path().join("outside-file");
        fs::write(&outside, "keep").unwrap();
        symlink(&outside, directory.join("payload-link.tmp")).unwrap();
        assert_eq!(cache.cleanup().unwrap(), 0);
        assert_eq!(fs::read_to_string(outside).unwrap(), "keep");
        assert!(
            directory
                .join("payload-link.tmp")
                .symlink_metadata()
                .is_ok()
        );
    }
}
