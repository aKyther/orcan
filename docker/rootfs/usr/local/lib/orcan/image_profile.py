"""Validated, declarative image contents. Source settings never become shell code."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

PACKAGES = {
    "codex": "@openai/codex",
    "gemini": "@google/gemini-cli",
    "copilot": "@github/copilot",
}
INSTALLERS = {
    "claude": "https://claude.ai/install.sh",
    "cursor": "https://cursor.com/install",
}
IMAGES = {"go": "golang:1.27-bookworm", "rust": "rust:1-bookworm"}
AGENTS = set(PACKAGES) | set(INSTALLERS)


def https_url(value: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) > 2000
        or any(c.isspace() for c in value)
    ):
        raise ValueError("Source URL must be bounded HTTPS text")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise ValueError("Source URL must use HTTPS without embedded credentials")
    return value


def agent_entry(value: str | dict) -> dict:
    entry = {"name": value} if isinstance(value, str) else value
    if not isinstance(entry, dict) or set(entry) - {"name", "version", "source"}:
        raise ValueError("Agent entries support name, version and source")
    name = entry.get("name")
    if not isinstance(name, str) or name not in AGENTS:
        raise ValueError("Unknown agent")
    version = entry.get("version", "latest")
    if not isinstance(version, str) or len(version) > 100:
        raise ValueError("Invalid agent version")
    if not (
        version == "latest"
        or name == "claude"
        and version == "stable"
        or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?", version)
        or name == "cursor"
        and re.fullmatch(r"[0-9]{4}\.[0-9]{2}\.[0-9]{2}-[a-z0-9]+", version)
    ):
        raise ValueError("Use latest or an exact version (Claude also supports stable)")
    source = entry.get("source")
    if name in PACKAGES:
        source = source or {"type": "npm", "package": PACKAGES[name]}
        if (
            not isinstance(source, dict)
            or set(source) - {"type", "package", "registry"}
            or source.get("type", "npm") != "npm"
        ):
            raise ValueError("npm agents support package and optional HTTPS registry")
        package = source.get("package", PACKAGES[name])
        if not isinstance(package, str) or not re.fullmatch(
            r"(?:@[a-z0-9._-]+/)?[a-z0-9][a-z0-9._-]{0,150}", package
        ):
            raise ValueError("Invalid npm package name")
        source = {
            "type": "npm",
            "package": package,
            **(
                {"registry": https_url(source["registry"])}
                if "registry" in source
                else {}
            ),
        }
    elif source is None:
        if name == "cursor" and version != "latest":
            source = {
                "type": "archive",
                "url": f"https://downloads.cursor.com/lab/{version}/linux/{{arch}}/agent-cli-package.tar.gz",
            }
        else:
            source = {"type": "installer", "url": INSTALLERS[name]}
    else:
        if not isinstance(source, dict) or set(source) - {"type", "url", "sha256"}:
            raise ValueError("Native source supports type, url and sha256")
        kind = source.get("type", "installer")
        if kind not in (
            {"installer", "archive"} if name == "cursor" else {"installer"}
        ):
            raise ValueError("Unsupported native source type")
        builtin = agent_entry({"name": name, "version": version})["source"]
        if (
            source.get("url") == builtin.get("url")
            and kind == builtin["type"]
            and not source.get("sha256")
        ):
            return {"name": name, "version": version, "source": builtin}
        checksum = source.get("sha256", "")
        if not isinstance(checksum, str) or not re.fullmatch(
            r"[a-fA-F0-9]{64}", checksum
        ):
            raise ValueError("A custom native source requires a SHA-256 checksum")
        source = {
            "type": kind,
            "url": https_url(source.get("url", "")),
            "sha256": checksum.lower(),
        }
        if name == "cursor" and kind == "installer" and version != "latest":
            raise ValueError("Pinned Cursor versions use an archive source")
    return {"name": name, "version": version, "source": source}


def tool_entry(value: str | dict) -> dict:
    entry = {"name": value} if isinstance(value, str) else value
    if not isinstance(entry, dict) or set(entry) - {"name", "version", "image"}:
        raise ValueError("Tool entries support name, version or image")
    name = entry.get("name")
    if not isinstance(name, str) or name not in IMAGES:
        raise ValueError("Supported optional tools: go, rust")
    if "version" in entry and "image" in entry:
        raise ValueError("Choose a tool version or a complete image reference")
    image = entry.get("image", IMAGES[name])
    if "version" in entry:
        version = entry["version"]
        if not isinstance(version, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]{0,100}", version
        ):
            raise ValueError("Invalid tool image version")
        image = ("golang" if name == "go" else "rust") + ":" + version
    if (
        not isinstance(image, str)
        or len(image) > 300
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/:@-]*", image)
    ):
        raise ValueError("Invalid tool image reference")
    return {"name": name, "image": image}


def unique(entries: list[dict]) -> list[dict]:
    result = {}
    for entry in entries:
        name = entry["name"]
        if name in result and result[name] != entry:
            raise ValueError("Conflicting entries for " + name)
        result[name] = entry
    return list(result.values())


def resolve(config: dict, override: str = "") -> dict:
    if not isinstance(config, dict):
        raise TypeError("Configuration must be an object")
    profile = config.get("build", {})
    if not isinstance(profile, dict) or set(profile) - {"agents", "tools"}:
        raise ValueError("build supports agents and tools")
    agents = profile.get("agents", [])
    tools = profile.get("tools", [] if "build" in config else list(IMAGES))
    if (
        not isinstance(agents, list)
        or not isinstance(tools, list)
        or len(agents) > 20
        or len(tools) > 10
    ):
        raise ValueError("build.agents and build.tools must be bounded lists")
    agents = unique([agent_entry(value) for value in agents])
    if override:
        configured = {entry["name"]: entry for entry in agents}
        agents = unique(
            [
                configured[name] if name in configured else agent_entry(name)
                for name in override.split("+")
            ]
        )
    if not agents:
        raise ValueError(
            "choose at least one agent: --agent NAME, --all-agents or build.agents"
        )
    return {"agents": agents, "tools": unique([tool_entry(value) for value in tools])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="")
    parser.add_argument("--agents", default="")
    args = parser.parse_args()
    try:
        config = json.loads(Path(args.config).read_text()) if args.config else {}
        print(json.dumps(resolve(config, args.agents)))
    except (ValueError, OSError, TypeError) as error:
        print("Invalid image profile: " + str(error), file=sys.stderr)
        return 2
    return 0
