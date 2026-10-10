//! Operation controls shared by system and native SSH transports.

use std::collections::BTreeMap;
use std::sync::{
    Arc, Mutex, OnceLock,
    atomic::{AtomicBool, Ordering},
};

fn controls() -> &'static Mutex<BTreeMap<String, Arc<AtomicBool>>> {
    static CONTROLS: OnceLock<Mutex<BTreeMap<String, Arc<AtomicBool>>>> = OnceLock::new();
    CONTROLS.get_or_init(Default::default)
}

pub(super) struct OperationControl {
    id: Option<String>,
    pub cancelled: Arc<AtomicBool>,
}

impl OperationControl {
    pub fn register(id: Option<String>) -> Result<Self, String> {
        let cancelled = Arc::new(AtomicBool::new(false));
        if let Some(id) = &id {
            uuid::Uuid::parse_str(id).map_err(|_| "invalid operation ID")?;
            let mut entries = controls()
                .lock()
                .map_err(|_| "operation registry unavailable")?;
            if entries.contains_key(id) {
                return Err("operation already running".to_owned());
            }
            entries.insert(id.clone(), cancelled.clone());
        }
        Ok(Self { id, cancelled })
    }
}

impl Drop for OperationControl {
    fn drop(&mut self) {
        if let Some(id) = &self.id {
            if let Ok(mut entries) = controls().lock() {
                entries.remove(id);
            }
        }
    }
}

#[tauri::command]
pub(super) fn cancel_operation(operation_id: String) -> Result<bool, String> {
    let entries = controls()
        .lock()
        .map_err(|_| "operation registry unavailable")?;
    if let Some(cancelled) = entries.get(&operation_id) {
        cancelled.store(true, Ordering::Relaxed);
        Ok(true)
    } else {
        Ok(false)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn controls_are_unique_and_removed_after_completion() {
        let id = uuid::Uuid::new_v4().to_string();
        let control = OperationControl::register(Some(id.clone())).unwrap();
        assert!(OperationControl::register(Some(id.clone())).is_err());
        assert!(cancel_operation(id.clone()).unwrap());
        assert!(control.cancelled.load(Ordering::Relaxed));
        drop(control);
        assert!(!cancel_operation(id).unwrap());
    }
}
