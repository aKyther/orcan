//! One archive producer for profile transfers and compatibility WSL endpoints.
use super::{shell_quote, valid_image_reference};

pub(super) fn command(image: Option<&str>) -> Result<String, String> {
    let argument = match image {
        Some(image) if valid_image_reference(image) => format!(" --image {}", shell_quote(image)),
        Some(_) => return Err("invalid Docker image reference".into()),
        None => String::new(),
    };
    Ok(format!(
        "bash -c {} orcan-cli-export{argument}",
        shell_quote(include_str!("cli_export.sh"))
    ))
}

#[cfg(test)]
mod tests {
    use super::command;

    #[test]
    fn export_arguments_are_explicit_and_validated() {
        let cli = command(None).unwrap();
        assert!(cli.ends_with(" orcan-cli-export"));
        assert!(
            command(Some("orcan:dev"))
                .unwrap()
                .ends_with(" --image 'orcan:dev'")
        );
        assert!(command(Some("image; touch /tmp/unsafe")).is_err());
    }
}
