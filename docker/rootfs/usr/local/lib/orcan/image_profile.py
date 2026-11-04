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
TOOL_VERSIONS = {'jdk':'21','gradle':'8.11','maven':'3.9.9','kotlin':'2.1.0','scala':'3.5.2','sbt':'1.10.5'}
TOOLS = set(IMAGES) | set(TOOL_VERSIONS)
TOOL_REQUIRES = {name:['jdk'] for name in TOOL_VERSIONS if name!='jdk'}
TOOL_HELP = {
 'go':'Go compiler and standard tools. Leave disabled for projects that do not use Go.',
 'rust':'Rust compiler, Cargo and toolchain data. Leave disabled unless your project needs Rust.',
 'jdk':'JDK for Java compilation and JVM tools. Required by Gradle, Maven, Kotlin, Scala and sbt.',
 'gradle':'Standalone Gradle; requires JDK. A project with ./gradlew can use its wrapper with JDK alone. build.gradle.kts does not require standalone Kotlin.',
 'maven':'Standalone Maven; requires JDK. A project with ./mvnw may use its wrapper with JDK alone.',
 'kotlin':'Standalone Kotlin compiler; requires JDK. Optional for Java-only projects and for Gradle Kotlin DSL configuration.',
 'scala':'Standalone Scala compiler; requires JDK. sbt projects can download their own Scala compiler without this optional installation.',
 'sbt':'sbt build tool for Scala/Java; requires JDK. Not needed for a Gradle/Maven-only project.',
}
PYTHONS = ('3.11','3.12','3.13')
AGENTS = set(PACKAGES) | set(INSTALLERS)


# Components already supplied by the standard Dockerfile. Optional Go/Rust
# toolchains are independent of the runtimes needed by installed agent clients.
BASE_COMPONENTS = {'node', 'npm', 'python', 'uv', 'git', 'openssh', 'docker',
                   'compose', 'gh', 'glab', 'redis', 'supervisor', 'curl', 'tar', 'ttyd'}
AGENT_REQUIRES = {name: ['node', 'npm'] for name in PACKAGES} | {
    'claude': ['curl'], 'cursor': ['curl', 'tar']}


def requirements(profile: dict | None, plugins: list[dict] = ()) -> dict:
    """Explain requirements, without selecting additional user toolchains."""
    effective_tools=resolve_tools((profile or {}).get('tools',[]))
    return {
        'provided_by_base': sorted(BASE_COMPONENTS),
        'agents': {entry['name']: AGENT_REQUIRES[entry['name']]
                   for entry in (profile or {}).get('agents', [])},
        'plugins': {entry['id']: {
            'plugins': entry.get('requires', []),
            'image': entry.get('image_requires', []),
            'host': entry.get('host_requires', []),
            'conflicts': entry.get('conflicts', []),
        } for entry in plugins},
        'optional_toolchains': effective_tools,
        'omitted_toolchains': sorted(TOOLS-{entry['name'] for entry in effective_tools}),
        'tool_help': {entry['name']:TOOL_HELP[entry['name']] for entry in effective_tools},
        'build_policy': {'layers':'local runtime target; dependencies shared across stages', 'temporary_downloads':'cleaned in installation layer', 'docker_cache':'preserved; no automatic global prune'},
        'python_locks': ['cockpit/uv.lock', 'executor/uv.lock'],
        'tool_dependencies': {entry['name']:TOOL_REQUIRES.get(entry['name'],[]) for entry in (profile or {}).get('tools',[])},
        'project_python': (profile or {}).get('python',[]),
        'core_python': 'System Python and private service runtimes are retained for Orcan itself.',
    }


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
    if not isinstance(name, str) or name not in TOOLS:
        raise ValueError("Supported optional tools: " + ", ".join(sorted(TOOLS)))
    if "version" in entry and "image" in entry:
        raise ValueError("Choose a tool version or a complete image reference")
    if name in TOOL_VERSIONS:
        if 'image' in entry: raise ValueError('JVM tools use version, not image')
        version=entry.get('version',TOOL_VERSIONS[name])
        if name=='jdk' and (not isinstance(version,str) or not re.fullmatch(r'[0-9]{1,3}',version)): raise ValueError('JDK version is a major release, for example 21')
        if not isinstance(version,str) or not re.fullmatch(r'[0-9]+(?:[.][0-9]+){0,3}(?:[-+][A-Za-z0-9.-]+)?',version):
            raise ValueError('Invalid tool version')
        return {'name':name,'version':version}
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


def resolve_tools(values):
    tools=unique([tool_entry(value) for value in values])
    if any(entry['name'] in TOOL_REQUIRES for entry in tools) and not any(entry['name']=='jdk' for entry in tools):
        tools.append(tool_entry('jdk'))
    return tools


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
    if not isinstance(profile, dict) or set(profile) - {"agents", "tools", "python"}:
        raise ValueError("build supports agents, tools and python")
    agents = profile.get("agents", [])
    tools = profile.get("tools", [] if "build" in config else sorted(TOOLS))
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
    tools=resolve_tools(tools)
    versions=profile.get('python', ['3.13'] if 'build' not in config else [])
    if not isinstance(versions,list) or len(versions)>3 or len(set(map(str,versions)))!=len(versions) or any(version not in PYTHONS for version in versions):
        raise ValueError('build.python must list distinct versions from 3.11, 3.12, 3.13; first is default')
    return {"agents": agents, "tools": tools, 'python':versions}


def build_environment(profile):
    result={}
    tools={entry['name']:entry for entry in profile['tools']}
    for name in TOOLS: result['INSTALL_'+('JAVA' if name=='jdk' else name.upper())]=str(int(name in tools))
    for name,default in TOOL_VERSIONS.items(): result[('JAVA' if name=='jdk' else name.upper())+'_VERSION']=tools.get(name,{}).get('version',default)
    result['GO_IMAGE']=tools.get('go',{}).get('image','debian:bookworm-slim')
    result['RUST_IMAGE']=tools.get('rust',{}).get('image','debian:bookworm-slim')
    result['ORCAN_PYTHON_VERSIONS']=' '.join(profile.get('python',[]))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="")
    parser.add_argument("--agents", default="")
    parser.add_argument("--explain", action="store_true")
    parser.add_argument("--environment", action="store_true")
    args = parser.parse_args()
    try:
        config = json.loads(Path(args.config).read_text()) if args.config else {}
        profile = resolve({'build':json.load(sys.stdin)}) if args.environment else resolve(config, args.agents)
        if args.environment:
            import shlex
            for key,value in build_environment(profile).items(): print('export '+key+'='+shlex.quote(value))
            return 0
        print(json.dumps(profile | {"requirements": requirements(profile)} if args.explain else profile))
    except (ValueError, OSError, TypeError) as error:
        print("Invalid image profile: " + str(error), file=sys.stderr)
        return 2
    return 0
