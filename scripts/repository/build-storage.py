#!/usr/bin/env python3
"""Bounded Docker storage diagnostics. Never pull, run, prune or remove anything."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import platform
import re
import socket
import shutil
import subprocess

WARNING_FREE = 2 * 1024**3


def clean(value):
    return ''.join(char for char in str(value) if char.isprintable())[:256]


def docker(*arguments):
    try:
        result=subprocess.run(['docker',*arguments],stdin=subprocess.DEVNULL,capture_output=True,text=True,errors="replace",timeout=8)
    except (OSError,subprocess.TimeoutExpired): return None
    # Do not expose raw diagnostics, which can include endpoint/auth details.
    return result.stdout[:65536] if result.returncode==0 else None


def decode(value):
    try:return json.loads(value) if value is not None else None
    except (TypeError,ValueError):return None


def filesystem(path):
    try:
        usage=shutil.disk_usage(path)
        return {'path':str(path),'free_bytes':usage.free,'total_bytes':usage.total}
    except OSError:return None


def builder_details(text):
    result={}
    nodes=[]
    for line in (text or '').splitlines():
        key,sep,value=line.partition(':')
        key=key.strip();value=value.strip()
        if sep and key=='Name' and 'name' not in result:result['name']=clean(value)
        elif sep and key=='Driver':result['driver']=clean(value)
        elif sep and key=='Endpoint':nodes.append(value)
    result['endpoints']=nodes
    return result


def daemon_is_local(endpoint, info, builder, context, *, in_container, system, hostname):
    return (system=='Linux' and not in_container and isinstance(endpoint,str)
            and endpoint.startswith('unix://') and isinstance(info,dict)
            and not any(marker in str(info.get('os','')).lower().replace(' ','').replace('-','') for marker in ('dockerdesktop','linuxkit'))
            and info.get('name')==hostname
            and builder.get('driver')=='docker'
            and builder.get('endpoints')==[context])


def inspect(root: Path):
    info=decode(docker('info','--format','{"root":{{json .DockerRootDir}},"os":{{json .OperatingSystem}},"name":{{json .Name}}}'))
    if not isinstance(info,dict):info=None
    context=(docker('context','show') or '').strip()
    # DOCKER_HOST overrides the selected context unless DOCKER_CONTEXT is set.
    endpoint=os.environ.get('DOCKER_HOST') if os.environ.get('DOCKER_HOST') and not os.environ.get('DOCKER_CONTEXT') else decode(docker('context','inspect','--format','{{json .Endpoints.docker.Host}}'))
    builder=builder_details(docker('buildx','inspect') if info else None)
    usage=[]
    for line in ((docker('system','df','--format','{{json .}}') if info else None) or '').splitlines()[:8]:
        row=decode(line)
        if isinstance(row,dict):usage.append({key:clean(row.get(source,'unknown')) for key,source in [('kind','Type'),('size','Size'),('reclaimable','Reclaimable'),('count','TotalCount'),('active','Active')]})
    cache={}
    # Default output contains cache IDs/sizes, never command descriptions.
    for line in ((docker('buildx','du') if info else None) or '').splitlines():
        match=re.fullmatch(r'(Shared|Private|Reclaimable|Total):\s*(.+)',line)
        if match:cache[match[1].lower()]=clean(match[2])
    container=Path('/.dockerenv').exists() or Path('/run/.containerenv').exists() or bool(os.environ.get('container'))
    local=daemon_is_local(endpoint,info,builder,context,in_container=container,system=platform.system(),hostname=socket.gethostname())
    daemon_disk=None
    if local and isinstance(info.get('root'),str) and Path(info['root']).is_absolute():
        daemon_disk=filesystem(info['root'])
    if info is None:status='unavailable'
    elif daemon_disk and daemon_disk['free_bytes']<WARNING_FREE:status='low'
    elif daemon_disk:status='ok'
    else:status='unknown'
    return {'version':1,'status':status,'warning_free_bytes':WARNING_FREE,
            'context':clean(context),'builder':{key:value for key,value in builder.items() if key!='endpoints'},
            'source_disk':filesystem(root),'docker_disk':daemon_disk,
            'docker_disk_unavailable_reason':None if daemon_disk else 'Daemon filesystem could not be verified locally (container, remote/VM/custom builder, permissions or unavailable daemon).',
            'daemon_root':clean(info.get('root','')) if info else None,
            'daemon_usage':usage,'builder_cache':cache,
            'notes':['Image and cache sizes overlap; do not sum them. Reclaimable values do not guarantee equivalent free disk space.',
                     'The 2 GiB warning threshold is not an estimate of required build space.',
                     'Other containerd/builder filesystems and inode availability are not verified. No data was removed.']}


def human_bytes(size):
    return f'{size/1024**3:.2f} GiB'


def render(report):
    lines=['Build storage check']
    source=report['source_disk']
    if source:lines.append('Source filesystem ('+clean(source['path'])+'): '+human_bytes(source['free_bytes'])+' free / '+human_bytes(source['total_bytes'])+' total')
    if not source:lines.append('Source filesystem: unavailable')
    if source and source['free_bytes']<WARNING_FREE and report['status']!='low':lines.append('Warning: source filesystem has less than 2 GiB free; this is not a measurement of daemon free space.')
    lines.append('Docker context: '+(report['context'] or 'unknown')+'; builder: '+report['builder'].get('name','unknown')+' ('+report['builder'].get('driver','unknown')+')')
    disk=report['docker_disk']
    if disk:lines.append('Docker filesystem ('+clean(disk['path'])+'): '+human_bytes(disk['free_bytes'])+' free / '+human_bytes(disk['total_bytes'])+' total')
    else:lines.append('Docker filesystem free space: unknown; '+report['docker_disk_unavailable_reason'])
    if not disk and report.get('daemon_root'):lines.append('Docker root (server path): '+report['daemon_root'])
    for row in report['daemon_usage']:
        lines.append(row['kind']+': '+row['size']+'; reclaimable: '+row['reclaimable']+'; active: '+row['active']+'/'+row['count'])
    if not report['daemon_usage']:lines.append('Docker disk usage: unavailable')
    cache=report['builder_cache']
    lines.append('Selected builder cache: '+('; '.join(key+'='+value for key,value in cache.items()) or 'unavailable'))
    lines.extend(report['notes'])
    if report['status']=='low':lines.append('Warning: verified Docker filesystem has less than 2 GiB free. Build may proceed; inspect storage before a large build.')
    elif report['status']=='unavailable':lines.append('Build stopped: Docker daemon information is unavailable. Check docker info and the selected context.')
    elif report['status']=='unknown':lines.append('Space check incomplete; build may proceed, but daemon free space is unverified.')
    return '\n'.join(lines)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--json',action='store_true')
    args=parser.parse_args()
    report=inspect(args.root)
    print(json.dumps(report) if args.json else render(report))
    return 2 if report['status']=='unavailable' else 0


if __name__=='__main__':raise SystemExit(main())
