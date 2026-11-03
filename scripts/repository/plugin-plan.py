#!/usr/bin/env python3
"""Resolve bundled plugin defaults, JSON settings, CLI flags and saved startup state."""
from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'docker/rootfs/usr/local/lib'))
from config_io import load_config
from orcan.plugin_registry import aliases, catalog, resolve, validate_field, validate_selection

# Compatibility bridge for existing Compose wrappers and launch records.
VARIABLES = {'docker':'with_docker','ssh':'with_git','github':'with_github','gitlab':'with_gitlab','network':'with_network','ttyd':'with_ttyd','redis':'with_redis'}


def plan(cfg: dict, arguments: list[str], saved: dict | None = None, *, preview: bool = False) -> dict:
    entries = catalog()
    by_name = {entry['id']:entry for entry in entries}
    names = aliases(entries)
    values = resolve(cfg)
    flags = {flag:entry for entry in entries for flag in entry['flags'] if flag.startswith('--')}
    fields = {rule['flag']:(entry['id'],key,rule) for entry in entries for key,rule in entry['fields'].items() if 'flag' in rule}
    secrets = {flag:entry for entry in entries for flag in entry.get('secret_flags', [])}
    changed = set()
    explicit_fields = set()
    auth = ''
    plain = auth_selected = resume = False
    i = 0
    while i < len(arguments):
        flag = arguments[i]
        i += 1
        if flag == '--resume':
            resume = True
            continue
        if flag in ('--with','--without'):
            if i == len(arguments) or arguments[i] not in names:
                raise ValueError(flag + ' requires a bundled plugin name')
            name = names[arguments[i]]; i += 1
            if by_name[name].get('configurable') is False:
                raise ValueError(name + ' is not a startup plugin')
            values[name]['enabled'] = flag == '--with'
            changed.add(name)
            continue
        if flag == '--no-docker':
            values['docker']['enabled'] = False
            changed.add('docker')
            continue
        if flag in secrets:
            if i == len(arguments) or arguments[i].startswith('--'):
                raise ValueError(flag + ' requires user:password')
            auth = arguments[i]; i += 1
            if ':' not in auth or not all(auth.split(':',1)):
                raise ValueError('--web-terminal-auth must have non-empty USER and PASS')
            auth_selected = True
            values['ttyd']['enabled'] = True
            continue
        if flag in fields:
            name,key,rule = fields[flag]
            if i == len(arguments) or arguments[i].startswith('--'):
                raise ValueError(flag + ' requires a value')
            values[name][key] = validate_field(name,key,arguments[i],rule); i += 1
            explicit_fields.add(name)
            continue
        if flag not in flags:
            raise ValueError('unknown argument: ' + flag)
        entry = flags[flag]; name = entry['id']
        values[name]['enabled'] = True
        changed.add(name)
        if name == 'ttyd': plain = True
        if entry.get('value_flag'):
            if i == len(arguments) or arguments[i].startswith('--'):
                raise ValueError(flag + ' requires a network name')
            values[name]['name'] = validate_field(name,'name',arguments[i],entry['fields']['name']); i += 1
    if plain and auth_selected:
        raise ValueError('--web-terminal and --web-terminal-auth are mutually exclusive')
    if resume:
        if changed or explicit_fields:
            raise ValueError('--resume restores saved flags; only --web-terminal-auth may be passed with it')
        if saved is None:
            raise ValueError('no previous orcan up recorded — start with explicit flags')
        snapshot = saved.get('plugins')
        if snapshot is not None:
            # Validate saved settings with the same schema; credentials never enter it.
            values = resolve({'plugins':snapshot})
        else:
            for name,variable in VARIABLES.items():
                values[name]['enabled'] = saved.get(variable.upper(), '0') == '1'
            values['github']['hostname'] = saved.get('GITHUB_HOSTNAME') or 'github.com'
            values['gitlab']['hostname'] = saved.get('GITLAB_HOSTNAME') or 'gitlab.com'
            values['network']['name'] = saved.get('NETWORK_NAME','')
        if saved.get('WITH_TTYD_AUTH') == '1' and not auth_selected:
            if not preview:
                raise ValueError('last start used --web-terminal-auth; pass it again: orcan up --resume --web-terminal-auth USER:PASS')
            auth_selected = True
        if auth_selected: values['ttyd']['enabled'] = True
    for name in explicit_fields:
        if not values[name]['enabled']:
            raise ValueError('--' + name + '-hostname requires --' + name)
    validate_selection(values,entries)
    exports = {variable:int(values[name]['enabled']) for name,variable in VARIABLES.items()}
    exports.update(github_hostname=values['github']['hostname'],gitlab_hostname=values['gitlab']['hostname'],network_name=values['network']['name'],with_ttyd_auth=int(auth_selected),with_ttyd_opt=int(plain),ttyd_credential=auth,resume=int(resume))
    exports['ORCAN_GIT_ENABLED'] = int(values['git']['enabled'])
    if not values['git']['enabled']:
        exports['GIT_AUTHOR_NAME'] = exports['GIT_AUTHOR_EMAIL'] = ''
    exports['ORCAN_PLUGINS_JSON'] = json.dumps(values,separators=(',',':'))
    exports['ORCAN_ACTIVE_PLUGINS'] = ' '.join(name for name,value in values.items() if value['enabled'] and by_name[name].get('configurable', True))
    for entry in entries:
        for key,rule in entry['fields'].items():
            if 'env' in rule:
                value=values[entry['id']][key]
                exports[rule['env']] = int(value) if isinstance(value,bool) else value
    return exports


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--last-up',type=Path)
    parser.add_argument('--json',action='store_true')
    parser.add_argument('arguments',nargs=argparse.REMAINDER)
    args=parser.parse_args()
    cfg=load_config(args.config) if args.config.is_file() else {}
    arguments=args.arguments[1:] if args.arguments[:1]==['--'] else args.arguments
    saved=json.loads(args.last_up.read_text()) if '--resume' in arguments and args.last_up and args.last_up.is_file() else None
    result=plan(cfg,arguments,saved)
    if args.json:
        # Never expose transient credentials in a reviewable startup plan.
        print(result['ORCAN_PLUGINS_JSON'])
    else:
        for key,value in result.items(): print('export '+key+'='+shlex.quote(str(value)))


if __name__=='__main__':
    try: main()
    except (ValueError,OSError,TypeError) as error:
        raise SystemExit('orcan: '+str(error)) from None
