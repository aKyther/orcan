"""Validate the frozen, additive instruction template selected at creation."""

from __future__ import annotations

from uuid import UUID


def validate_identity(value: object) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {
        "id",
        "version",
        "name",
        "description",
        "instructions",
    }:
        raise ValueError(
            "identity requires id, version, name, description and instructions"
        )
    try:
        if str(UUID(value["id"])) != value["id"]:
            raise ValueError("identity id must be a canonical UUID")
    except (ValueError, TypeError, AttributeError) as error:
        raise ValueError("identity id must be a canonical UUID") from error
    if type(value["version"]) is not int or not 1 <= value["version"] <= 2147483647:
        raise ValueError("identity version must be a positive integer")
    for field, limit in (("name", 120), ("description", 1000), ("instructions", 32768)):
        text = value[field]
        if (
            not isinstance(text, str)
            or len(text.encode("utf-8")) > limit
            or "\0" in text
        ):
            raise ValueError(f"invalid identity {field}")
        if field != "description" and not text.strip():
            raise ValueError(f"identity {field} is required")
    if any(char in value["name"] for char in "\r\n"):
        raise ValueError("identity name must be one line")
    return dict(value)
