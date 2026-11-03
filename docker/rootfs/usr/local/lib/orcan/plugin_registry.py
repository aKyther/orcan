"""Shared rules for bundled plugins: data-only discovery, settings and selection."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path


def catalog_root() -> Path:
    # Resolve from the installed code, never from a user configuration path.
    for parent in Path(__file__).resolve().parents:
        if (parent / 'cli/orcan.sh').is_file() and (parent / 'plugins').is_dir():
            return parent / 'plugins'
    return Path('/opt/orcan/plugins')


def catalog(root: Path | None = None) -> list[dict]:
    root = root or catalog_root()
    entries = []
    flags = set()
    for path in sorted(root.glob('*/plugin.json')):
        value = json.loads(path.read_text())
        name = value.get('id', '')
        if not re.fullmatch('[a-z][a-z0-9-]*', name) or path.parent.name != name or value.get('version') != 1:
            raise ValueError('Invalid bundled plugin descriptor: ' + str(path))
        if value.get('group') not in {'access', 'services', 'interface'} or type(value.get('enabled')) is not bool or not isinstance(value.get('fields'), dict):
            raise ValueError('Invalid grouped plugin settings: ' + name)
        for key, rule in value['fields'].items():
            if not re.fullmatch('[a-z][a-z0-9_]*', key) or rule.get('type') not in {'boolean', 'integer', 'string'} or not isinstance(rule.get('label'), str):
                raise ValueError('Invalid plugin field: ' + name + '.' + key)
            if 'env' in rule and not re.fullmatch('[A-Z][A-Z0-9_]*', rule['env']):
                raise ValueError('Invalid plugin process variable: ' + name)
        if 'compose' in value and (Path(value['compose']).name != value['compose'] or not (path.parent / value['compose']).is_file()):
            raise ValueError('Invalid package Compose overlay: ' + name)
        for flag in value.get('flags', []) + value.get('secret_flags', []):
            if flag in flags:
                raise ValueError('Duplicate plugin flag: ' + flag)
            flags.add(flag)
        entries.append(value)
    if not entries:
        raise ValueError('Bundled plugin catalog is missing')
    names = {entry['id'] for entry in entries}
    for entry in entries:
        for target in entry.get('requires', []) + entry.get('conflicts', []):
            if target not in names or target == entry['id']:
                raise ValueError('Invalid plugin dependency/conflict: ' + entry['id'])
    return entries


def aliases(entries: list[dict]) -> dict[str, str]:
    result = {entry['id']: entry['id'] for entry in entries}
    for entry in entries:
        for alias in entry.get('aliases', []):
            if alias in result:
                raise ValueError('Duplicate plugin alias: ' + alias)
            result[alias] = entry['id']
    return result


def validate_field(plugin: str, key: str, value, rule: dict):
    expected = {'boolean': bool, 'integer': int, 'string': str}[rule['type']]
    if type(value) is not expected:
        raise ValueError(f'plugins.{plugin}.{key} must be {rule["type"]}')
    if isinstance(value, str) and '\x00' in value:
        raise ValueError(f'plugins.{plugin}.{key} must not contain control characters')
    if rule['type'] == 'integer' and not rule.get('minimum', value) <= value <= rule.get('maximum', value):
        raise ValueError(f'plugins.{plugin}.{key} is outside the supported range')
    if 'choices' in rule and value not in rule['choices']:
        raise ValueError(f'plugins.{plugin}.{key} must be one of {rule["choices"]}')
    if rule.get('format') == 'hostname':
        value = value.lower()
        if len(value) > 253 or not re.fullmatch(r'([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)*[a-z0-9]([a-z0-9-]*[a-z0-9])?', value):
            raise ValueError(f'plugins.{plugin}.{key} requires a hostname without a URL, path or port')
    if rule.get('format') == 'network' and value and not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]*', value):
        raise ValueError('Invalid Docker network name')
    return value


def resolve(cfg: dict, *, check_selection: bool = False) -> dict:
    entries = catalog()
    names = aliases(entries)
    raw = cfg.get('plugins', {})
    if not isinstance(raw, dict):
        raise ValueError('plugins must be an object')
    configured = {}
    for key, value in raw.items():
        if key not in names:
            raise ValueError('Unknown bundled plugin: ' + key)
        name = names[key]
        if name in configured:
            raise ValueError('Plugin configured twice: ' + name)
        if not isinstance(value, dict):
            raise ValueError('plugins.' + key + ' must be an object')
        configured[name] = value
    result = {}
    for entry in entries:
        name = entry['id']
        values = configured.get(name, {})
        fields = entry['fields']
        if set(values) - (fields.keys() | {'enabled'}):
            raise ValueError('Unknown settings for plugins.' + name)
        if entry.get('configurable') is False and values and values != {'enabled':entry['enabled']}:
            raise ValueError(name + ' is a built-in interface, not a startup plugin')
        enabled = values.get('enabled', entry['enabled'])
        if type(enabled) is not bool:
            raise ValueError('plugins.' + name + '.enabled must be boolean')
        legacy = cfg.get(entry.get('legacy_section', ''), {})
        if not isinstance(legacy, dict):
            raise ValueError(entry['legacy_section'] + ' must be an object')
        resolved = {'enabled': enabled}
        for key, rule in fields.items():
            fallback = cfg.get(rule['legacy_key'], rule['default']) if 'legacy_key' in rule else legacy.get(key, rule['default'])
            # Legacy ttyd.port implied host_port when no host_port was supplied.
            if name == 'ttyd' and key == 'host_port' and 'host_port' not in legacy:
                fallback = legacy.get('port', fallback)
            resolved[key] = validate_field(name, key, values.get(key, fallback), rule)
        if name == 'redis' and resolved['split_lanes'] and resolved['workers'] != 1:
            raise ValueError('plugins.redis.workers must be 1 when split_lanes is enabled')
        result[name] = resolved
    if check_selection:
        validate_selection(result, entries)
    return result


def validate_selection(values: dict, entries: list[dict] | None = None):
    for entry in entries or catalog():
        name = entry['id']
        if not values[name]['enabled']:
            continue
        for other in entry.get('requires', []):
            if not values[other]['enabled']:
                raise ValueError(f'Plugin {name} requires {other}')
        for other in entry.get('conflicts', []):
            if values[other]['enabled']:
                raise ValueError(f'Plugins {name} and {other} are mutually exclusive')
        if name == 'network' and not values[name]['name']:
            raise ValueError('Enabled network plugin requires a network name')


def configuration_schema() -> dict:
    """Generate the user-facing plugins section from the package-owned fields."""
    properties = {}
    for entry in catalog():
        if not entry.get('configurable', True):
            continue
        fields = {'enabled': {'type':'boolean','default':entry['enabled']}}
        for key, rule in entry['fields'].items():
            field = {name:rule[name] for name in ('type','default','minimum','maximum') if name in rule}
            if 'choices' in rule: field['enum'] = rule['choices']
            field['description'] = rule['label']
            fields[key] = field
        value = {'type':'object','additionalProperties':False,'properties':fields}
        properties[entry['id']] = value
        for alias in entry.get('aliases', []): properties[alias] = value
    return {'type':'object','additionalProperties':False,'properties':properties}
