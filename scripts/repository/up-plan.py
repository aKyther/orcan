#!/usr/bin/env python3
"""Read-only startup preview. Never runs Docker, credential helpers or generators."""
from __future__ import annotations

import argparse
import json
import os
import runpy
import sys

sys.dont_write_bytecode = True
from pathlib import Path

from config_io import load_config
from host_config import host_environment, resolve_settings
from orcan.image_profile import resolve as image_profile, requirements
from orcan.plugin_registry import catalog
from path_guards import checked_project_dir

planner = runpy.run_path(str(Path(__file__).with_name('plugin-plan.py')))['plan']


def preview(config: Path, home: Path, arguments: list[str], saved_path: Path | None = None) -> dict:
    cfg = load_config(config) if config.is_file() else {}
    runtime_path = Path(os.environ.get('ORCAN_RUNTIME_DIR') or home / 'mounts') / 'runtime-config.json'
    runtime = json.loads(runtime_path.read_text()) if runtime_path.is_file() else {}
    saved = json.loads(saved_path.read_text()) if '--resume' in arguments and saved_path and saved_path.is_file() else None
    resolved = planner(cfg, arguments, saved, preview=True)
    plugins = json.loads(resolved['ORCAN_PLUGINS_JSON'])
    host = host_environment(cfg, home, runtime)
    selected = [entry['id'] for entry in catalog() if entry.get('configurable', True) and plugins[entry['id']]['enabled']]
    mounts = [
        {'source':host['ORCAN_CONFIG_HOST'], 'target':'/etc/orcan/config.json', 'read_only':True, 'purpose':'runtime configuration'},
        {'source':host['ORCAN_PROJECTS_ROOT'], 'target':host['ORCAN_PROJECTS_ROOT'], 'read_only':False, 'purpose':'managed projects'},
    ]
    # Read the existing configuration shape without generating workspace directories.
    normalize = runpy.run_path(str(Path(__file__).with_name('apply-config.py')))['normalize_workspaces_raw']
    for index,workspace in enumerate(normalize(cfg if cfg else {"workspaces": []})):
        if not isinstance(workspace,dict): raise ValueError("workspace must be an object")
        if workspace.get('enabled') is False: continue
        projects=workspace.get('projects',[])
        name = workspace.get('name') or (projects[0].get('name', f'workspace-{index+1}') if projects and isinstance(projects[0],dict) else '')
        if not isinstance(name, str) or not name or '/' in name:
            raise ValueError('workspace names must be non-empty names without slashes')
        mounts.append({'source':str(home/'workspaces'/name),'target':'/home/developer/workspaces/'+name,'read_only':False,'purpose':'workspace metadata'})
        for project in workspace.get('projects', []):
            source = project.get('path') if isinstance(project,dict) else project
            if not isinstance(source,str) or not Path(source).is_absolute():
                raise ValueError('project paths must be absolute')
            source = str(checked_project_dir(source, must_exist=False))
            # Managed projects are already covered by the stable root bind.
            if Path(source).is_relative_to(Path(host['ORCAN_PROJECTS_ROOT'])): continue
            mounts.append({'source':source,'target':source,'read_only':False,'purpose':'project'})
    if plugins['docker']['enabled']:
        mounts.append({'source':'/var/run/docker.sock','target':'/var/run/docker.sock','read_only':False,'purpose':'docker plugin'})
    if plugins['ssh']['enabled']:
        ssh = Path.home()/'.ssh'
        mounts.append({'source':str(ssh),'target':'/home/developer/.ssh','read_only':True,'purpose':'ssh plugin','conditional':'host directory exists','available':ssh.is_dir()})
        mounts.append({'source':'SSH_AUTH_SOCK','target':'/run/host-ssh-agent.sock','read_only':False,'purpose':'ssh agent','conditional':'host SSH agent socket exists'})
    ports = []
    if plugins['ttyd']['enabled']:
        ttyd = plugins['ttyd']
        ports.append({'plugin':'ttyd','bind':ttyd['bind'],'host':ttyd['host_port'],'container':ttyd['port']})
    if plugins['redis']['enabled']:
        ports.append({'plugin':'redis','bind':plugins['ttyd']['bind'],'host':plugins['redis']['port'],'container':8765})
    credentials = [{'plugin':name,'action':'resolve host login or process credential at startup; not inspected'} for name in ('github','gitlab') if plugins[name]['enabled']]
    if plugins['ttyd']['enabled'] and (plugins['ttyd']['authentication']=='basic' or resolved['with_ttyd_auth']):
        credentials.append({'plugin':'ttyd','action':'transient terminal credential required at startup; not inspected'})
    generated = [runtime_path, Path(host['ORCAN_COMPOSE_PROJECTS'])]
    needs_sync = any(not path.is_file() or config.is_file() and config.stat().st_mtime_ns > path.stat().st_mtime_ns for path in generated)
    requested_profile = image_profile(cfg) if 'build' in cfg else None
    if requested_profile is not None:
        requested_profile['agents'] = [{'name':entry['name'],'version':entry['version']} for entry in requested_profile['agents']]
    return {
        'version':1, 'read_only':True,
        'configuration':{'path':str(config),'exists':config.is_file(),'needs_sync':needs_sync},
        'blockers':[] if requested_profile else ['Choose image agents in orcan settings before startup can prepare an image.'],
        'image':{'name':host['IMAGE_LOCAL'],'requested_profile':requested_profile,'installed_profile_inspected':False},
        'plugins':plugins, 'enabled_plugins':selected,
        'plugin_help':{entry['id']:{'help':entry['help'],'examples':entry['examples']} for entry in catalog() if entry['id'] in selected},
        'requirements':requirements(requested_profile, [entry for entry in catalog() if entry['id'] in selected]),
        'resources':resolve_settings(cfg)['resources'],
        'mounts':mounts, 'ports':ports,
        'network':plugins['network']['name'] if plugins['network']['enabled'] else None,
        'credentials':credentials,
        'lifecycle':'up prepares configuration and image, validates Compose, then converges the instance; current runtime was not inspected',
        'stages':['prepare','image','preflight','start','verify','ready'],
        'checks_at_start':['Docker availability','generated configuration freshness','credentials for enabled integrations','required sockets and networks'],
        'notes':['Startup reuses an image with a matching source/profile receipt, otherwise builds it; the image was not inspected.','Preview lists managed/config/project and plugin mounts; persistent client/cache mounts follow data_root.'],
    }


def render(report: dict) -> str:
    lines=['Orcan startup plan (read-only)', 'Configuration: '+report['configuration']['path'],
           'Image: '+report['image']['name'], 'Enabled plugins: '+(', '.join(report['enabled_plugins']) or 'none')]
    profile=report['image']['requested_profile']
    lines.append('Agents requested for image: '+(', '.join(entry['name']+'@'+entry['version'] for entry in profile['agents']) if profile else 'not configured; installed image not inspected'))
    for blocker in report['blockers']: lines.append('Required: '+blocker)
    if report['configuration']['needs_sync']: lines.append('Startup will synchronize generated configuration')
    if profile:
        lines.append('Project tools: '+(', '.join(entry['name']+'@'+entry.get('image',entry.get('version','')) for entry in profile['tools']) or 'none'))
        lines.append('Project Python (first is default): '+(', '.join(profile.get('python',[])) or 'none'))
        lines.append(report['requirements']['core_python'])
        lines.append('Omitted project tools: '+(', '.join(report['requirements']['omitted_toolchains']) or 'none'))
        for name,deps in report['requirements']['tool_dependencies'].items():
            if deps: lines.append(name+' requires: '+', '.join(deps))
    lines.append('Stages: ' + ' -> '.join(report['stages']))
    lines.append('Runtime: '+report['lifecycle'])
    for port in report['ports']: lines.append(f"Port ({port['plugin']}): {port['bind']}:{port['host']} -> {port['container']}")
    for mount in report['mounts']: lines.append(f"Mount: {mount['source']} -> {mount['target']} ({'read-only' if mount['read_only'] else 'read/write'})" + (' [conditional]' if 'conditional' in mount else ''))
    for name, required in report['requirements']['agents'].items():
        lines.append('Agent requirements ('+name+'): '+', '.join(required)+' [included in base]')
    for name, required in report['requirements']['plugins'].items():
        if required['image']: lines.append('Plugin image requirements ('+name+'): '+', '.join(required['image'])+' [included in base]')
        if required['host']: lines.append('Plugin host requirements ('+name+'): '+', '.join(required['host']))
        if required['plugins']: lines.append('Required plugins ('+name+'): '+', '.join(required['plugins']))
        if required['conflicts']: lines.append('Conflicts ('+name+'): '+', '.join(required['conflicts']))
    if report['network']: lines.append('External network: '+report['network'])
    for name,help in report['plugin_help'].items():
        lines.append('Setup ('+name+'): orcan plugins help --plugin '+name)
    for entry in report['credentials']: lines.append('Authentication ('+entry['plugin']+'): '+entry['action'])
    lines.append('No credentials acquired; no files, containers or services changed.')
    return '\n'.join(''.join(character if character.isprintable() else ' ' for character in line) for line in lines)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--home',type=Path,required=True)
    parser.add_argument('--last-up',type=Path)
    parser.add_argument('--json',action='store_true')
    parser.add_argument('arguments',nargs=argparse.REMAINDER)
    args=parser.parse_args()
    arguments=args.arguments[1:] if args.arguments[:1]==['--'] else args.arguments
    report=preview(args.config,args.home,arguments,args.last_up)
    print(json.dumps(report,indent=2) if args.json else render(report))


if __name__=='__main__':
    try: main()
    except (ValueError,OSError,TypeError) as error:
        raise SystemExit('orcan: '+str(error)) from None
