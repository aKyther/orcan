"""Resolve JSON settings for host commands without reading dotenv files."""
from __future__ import annotations

import math
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "docker/rootfs/usr/local/lib"))
from config_io import die
from defaults import RESOURCE_DEFAULTS, TMUX_DEFAULTS, TTYD_DEFAULTS, PROCESS_DEFAULTS
from orcan.executor_config import ENVIRONMENT, resolve as resolve_executor
from orcan.plugin_registry import resolve as resolve_plugins
from path_guards import checked_project_dir

def resolve_settings(cfg: dict) -> dict:
    """The tmux / ttyd / resources sections with defaults filled and types coerced.

    Shared by build_from_config() and synthesize_from_env() so the default
    literals live only in defaults.py. Pass an empty cfg for pure defaults.
    """
    try:
        plugins = resolve_plugins(cfg)
    except ValueError as error:
        die(str(error))
    ttyd = {key:value for key,value in plugins["ttyd"].items() if key not in {"enabled", "authentication"}}
    resources = cfg.get("resources") or {}
    if not isinstance(ttyd, dict) or not isinstance(resources, dict):
        die("ttyd and resources must be objects")

    tmux_cfg = cfg.get("tmux") if isinstance(cfg.get("tmux"), dict) else {}
    history_limit = tmux_cfg.get("history_limit", TMUX_DEFAULTS["history_limit"])
    if type(history_limit) is not int or not 1000 <= history_limit <= 200000:
        die("tmux.history_limit must be an integer from 1000 to 200000")
    initial_windows = int(
        tmux_cfg.get("initial_windows", TMUX_DEFAULTS["initial_windows"])
    )
    initial_windows = max(1, min(9, initial_windows))
    window_prefix = str(
        tmux_cfg.get("window_prefix") or TMUX_DEFAULTS["window_prefix"]
    ).strip() or str(TMUX_DEFAULTS["window_prefix"])
    renderer = str(ttyd.get("renderer") or TTYD_DEFAULTS["renderer"]).strip().lower()
    if renderer not in {"webgl", "canvas"}:
        die("ttyd.renderer must be 'webgl' or 'canvas'")

    cockpit = cfg.get("cockpit", {})
    if not isinstance(cockpit, dict) or set(cockpit) - {
        "pty_read_bytes",
        "pty_read_ms",
        "pty_chunk_bytes",
        "peek_chars",
    }:
        die(
            "cockpit supports pty_read_bytes, pty_read_ms, pty_chunk_bytes and peek_chars"
        )
    for key, (minimum, maximum) in {
        "pty_read_bytes": (4096, 1048576),
        "pty_read_ms": (1, 50),
        "pty_chunk_bytes": (4096, 65536),
        "peek_chars": (256, 8192),
    }.items():
        if key in cockpit and (
            type(cockpit[key]) is not int or not minimum <= cockpit[key] <= maximum
        ):
            die("Invalid cockpit budget: " + key)
    executor = resolve_executor({key:plugins["redis"][key] for key in ENVIRONMENT})
    return {
        **({"cockpit": cockpit} if cockpit else {}),
        "executor": executor,
        "plugins": plugins,
        "tmux": {
            "initial_windows": initial_windows,
            "history_limit": history_limit,
            "window_prefix": window_prefix,
        },
        "ttyd": {
            "port": int(ttyd.get("port", TTYD_DEFAULTS["port"])),
            "host_port": int(
                ttyd.get("host_port", ttyd.get("port", TTYD_DEFAULTS["host_port"]))
            ),
            "bind": str(ttyd.get("bind") or TTYD_DEFAULTS["bind"]).strip()
            or str(TTYD_DEFAULTS["bind"]),
            "font_size": int(ttyd.get("font_size", TTYD_DEFAULTS["font_size"])),
            "font_family": str(ttyd.get("font_family") or TTYD_DEFAULTS["font_family"]),
            "renderer": renderer,
            "theme": str(ttyd.get("theme") or TTYD_DEFAULTS["theme"]),
            "ping_interval": max(
                1, int(ttyd.get("ping_interval", TTYD_DEFAULTS["ping_interval"]))
            ),
        },
        "resources": {
            "cpus": resources.get("cpus", RESOURCE_DEFAULTS["cpus"]),
            "memory": str(resources.get("memory", RESOURCE_DEFAULTS["memory"])),
            "shm_size": str(resources.get("shm_size", RESOURCE_DEFAULTS["shm_size"])),
            "tmpfs_size": str(
                resources.get("tmpfs_size", RESOURCE_DEFAULTS["tmpfs_size"])
            ),
        },
    }


def host_environment(cfg: dict, home: Path, runtime: dict | None = None) -> dict[str, str]:
    """Map known JSON fields to process variables; never accept arbitrary exports."""
    settings = resolve_settings(cfg)
    for section in ("ttyd", "resources", "executor"):
        if section in cfg and not isinstance(cfg[section], dict):
            die(section + " must be an object")
    for field in ("port", "host_port"):
        value = settings["ttyd"][field]
        if not 1 <= value <= 65535:
            die("ttyd." + field + " must be from 1 to 65535")
    cpus = settings["resources"]["cpus"]
    if isinstance(cpus, bool) or not isinstance(cpus, (int, float)) or not math.isfinite(cpus) or cpus <= 0:
        die("resources.cpus must be a positive number")
    port = settings["plugins"]["redis"]["port"]
    if type(port) is not int or not 1 <= port <= 65535:
        die("executor_port must be an integer from 1 to 65535")
    if not isinstance(cfg.get("timezone", "UTC"), str):
        die("timezone must be a string")
    data = cfg.get("data_root") or os.environ.get("ORCAN_DATA") or str(Path.home() / ".config/orcan")
    projects = cfg.get("projects_root") or os.environ.get("ORCAN_PROJECTS_ROOT") or str(Path(data) / "sandbox")
    for value in (data, projects):
        if not isinstance(value, str) or not Path(value).is_absolute() or any(c in value for c in "\n\r$`"):
            die("data_root and projects_root must be absolute paths without shell expansions")
        checked_project_dir(value, must_exist=False)
    image = cfg.get("image", "orcan:latest")
    if not isinstance(image, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._/:@-]*", image):
        die("invalid configured Docker image reference")
    registry = cfg.get("registry", {})
    if not isinstance(registry, dict) or set(registry) - {"host", "repository", "tag"}:
        die("registry supports host, repository and tag")
    if any(not isinstance(value, str) or any(c.isspace() for c in value) for value in registry.values()):
        die("registry values must be strings without whitespace")
    root = Path(os.environ.get("ORCAN_RUNTIME_DIR") or home / "mounts")
    workspaces = (runtime or {}).get("workspaces", [])
    ws = next((ws for ws in workspaces if ws.get("enabled") is not False), {})
    result = {
        "IMAGE_LOCAL": image,
        "IMAGE_REGISTRY": registry.get("host", "ghcr.io"),
        "IMAGE_REPOSITORY": registry.get("repository", "akyther/orcan"),
        "IMAGE_TAG": registry.get("tag", ""),
        "ORCAN_DATA": data, "ORCAN_PROJECTS_ROOT": projects,
        "PROJECT_DIR": str(home),
        "CONTAINER_PROJECT_DIR": ws.get("root", "/home/developer"),
        "ORCAN_CONFIG_HOST": str(root / "runtime-config.json"),
        "ORCAN_CONFIG": "/etc/orcan/config.json",
        "ORCAN_COMPOSE_PROJECTS": str(root / "compose-projects.generated.yml"),
        "ORCAN_WORKSPACE_MANIFEST": str(home / "workspaces/index.json"),
        "WORKSPACE_ROOT": ws.get("root", "/home/developer"),
        "WORKSPACE_NAME": ws.get("name", ""),
        "WORKSPACE_META_PATH": ws.get("meta_path", ""),
        "TMUX_HISTORY_LIMIT": settings["tmux"]["history_limit"],
        "USER_UID": os.getuid(), "USER_GID": os.getgid(),
        "DOCKER_GID": Path("/var/run/docker.sock").stat().st_gid if Path("/var/run/docker.sock").exists() else 999,
        "TZ": cfg.get("timezone", "UTC"),
        "ORCAN_EXECUTOR_PORT": settings["plugins"]["redis"]["port"],
    }
    for key, value in settings["ttyd"].items():
        result["TTYD_" + key.upper()] = value
    for key, variable in {"cpus": "CPUS", "memory": "MEMORY", "shm_size": "SHM_SIZE", "tmpfs_size": "TMPFS_SIZE"}.items():
        result[variable] = settings["resources"][key]
    resources = cfg.get("resources", {})
    for key, default in PROCESS_DEFAULTS.items():
        value = resources.get(key, default)
        if type(value) is not int or value < 1024:
            die("resources." + key + " must be an integer >= 1024")
        result["ULIMIT_" + key.upper()] = value
    for key, variable in ENVIRONMENT.items():
        value = settings["executor"][key]
        result[variable] = int(value) if isinstance(value, bool) else value
    for key, value in result.items():
        if not isinstance(value, (str, int, float)) or isinstance(value, bool) or "\x00" in str(value):
            die("invalid host setting: " + key)
    return {key: str(value) for key, value in result.items()}
