"""Editable settings draft with explicit review, validation and guarded JSON save."""
from __future__ import annotations

import copy
import contextlib
import io
from pathlib import Path

from config_io import dump_config, load_config
from defaults import RESOURCE_DEFAULTS, TMUX_DEFAULTS
from host_config import host_environment
from orcan.image_profile import AGENTS, IMAGES, agent_entry, resolve as image_profile
from orcan.plugin_registry import catalog, resolve as resolve_plugins, validate_field, validate_selection


def validate_host(data, home):
    # Host validators print CLI diagnostics; keep a curses screen intact and
    # surface the same bounded message in its status row instead.
    diagnostic=io.StringIO()
    try:
        with contextlib.redirect_stderr(diagnostic):
            host_environment(data, home)
    except SystemExit as error:
        raise ValueError(diagnostic.getvalue().strip() or str(error)) from None


class SettingsModel:
    def __init__(self, path: Path):
        self.path = path.resolve()
        snapshot = load_config(self.path)
        self.revision = snapshot.revision
        self.original = copy.deepcopy(dict(snapshot))
        self.data = copy.deepcopy(self.original)

    @property
    def dirty(self):
        return self.data != self.original

    def plugins(self):
        # Keep a renderable draft while related fields are edited one at a time.
        # Cross-field rules are enforced before the explicit save.
        if getattr(self, '_plugins_edited', False):
            return resolve_plugins({}) | copy.deepcopy(self.data['plugins'])
        return resolve_plugins(self.data)

    def _plugin_draft(self):
        if not getattr(self, '_plugins_edited', False):
            values = self.plugins()
            self.data['plugins'] = {entry['id']:values[entry['id']] for entry in catalog() if entry.get('configurable', True)}
            for key in ('executor','executor_port','ttyd'): self.data.pop(key,None)
            self._plugins_edited = True
        return self.data['plugins']

    def toggle_plugin(self, name):
        entry=next(entry for entry in catalog() if entry['id']==name)
        if not entry.get('configurable',True): raise ValueError('This interface is not a startup plugin')
        draft=self._plugin_draft()
        draft[name]['enabled'] = not draft[name]['enabled']

    def set_plugin(self, name, key, value):
        entry=next(entry for entry in catalog() if entry['id']==name)
        checked=validate_field(name,key,value,entry['fields'][key])
        self._plugin_draft()[name][key]=checked

    def agents(self):
        return {entry['name']:entry for entry in (agent_entry(value) for value in self.data.get('build',{}).get('agents',[]))}

    def tools(self):
        if 'build' not in self.data: return set(IMAGES)
        return {value if isinstance(value,str) else value['name'] for value in self.data['build'].get('tools',[])}

    def _build_draft(self):
        if 'build' not in self.data:
            self.data['build']={'agents':[],'tools':list(IMAGES)}
        return self.data['build']

    def toggle_agent(self, name):
        if name not in AGENTS: raise ValueError('Unknown agent')
        entries=self._build_draft().setdefault('agents',[])
        exists=any((value if isinstance(value,str) else value['name'])==name for value in entries)
        if exists:
            self.data['build']['agents']=[value for value in entries if (value if isinstance(value,str) else value['name'])!=name]
        else: entries.append(name)

    def set_agent_version(self, name, version):
        entries=self._build_draft().setdefault('agents',[])
        for index,value in enumerate(entries):
            if (value if isinstance(value,str) else value['name'])==name:
                raw={'name':value} if isinstance(value,str) else copy.deepcopy(value)
                raw['version']=version
                agent_entry(raw)  # Preserve and validate any configured custom source.
                entries[index]=raw
                return
        raise ValueError('Enable the agent before editing its version')

    def toggle_tool(self, name):
        if name not in IMAGES: raise ValueError('Unknown toolchain')
        enabled=self.tools()
        build=self._build_draft()
        if name in enabled:
            build['tools']=[value for value in build.get('tools',[]) if (value if isinstance(value,str) else value['name'])!=name]
        else: build.setdefault('tools',[]).append(name)

    def set_resource(self, key, value):
        proposed=copy.deepcopy(self.data)
        if key in ('image','timezone'): proposed[key]=value
        else: proposed.setdefault('resources',{})[key]=value
        validate_host(proposed,self.path.parent)
        self.data=proposed

    def set_tmux(self, key, value):
        if key == 'initial_windows' and (type(value) is not int or not 1 <= value <= 9):
            raise ValueError('Initial windows must be from 1 to 9')
        proposed=copy.deepcopy(self.data)
        proposed.setdefault('tmux',{})[key]=value
        validate_host(proposed,self.path.parent)
        self.data=proposed

    def validate(self):
        validate_host(self.data,self.path.parent)
        validate_selection(self.plugins())
        if 'build' in self.data: image_profile(self.data)

    def next_actions(self):
        if not self.dirty: return []
        actions=['orcan up --plan']
        actions.append('orcan up (after active background jobs finish)')
        return actions

    def review(self):
        lines=[]
        old_plugins=resolve_plugins(self.original)
        new_plugins=self.plugins()
        for entry in catalog():
            name=entry['id']
            for key,value in new_plugins[name].items():
                if old_plugins[name].get(key)!=value:
                    lines.append(f'plugins.{name}.{key}: {old_plugins[name].get(key)!r} -> {value!r}')
        if self.data.get('build')!=self.original.get('build'):
            agents=self.agents()
            lines.append('Image agents: '+(', '.join(name+'@'+entry['version'] for name,entry in agents.items()) or 'none selected'))
            lines.append('Image toolchains: '+(', '.join(sorted(self.tools())) or 'none'))
        for section,defaults in (('resources',RESOURCE_DEFAULTS),('tmux',TMUX_DEFAULTS)):
            old=defaults | self.original.get(section,{})
            new=defaults | self.data.get(section,{})
            for key,value in new.items():
                if old.get(key)!=value: lines.append(f'{section}.{key}: {old.get(key)!r} -> {value!r}')
        for key in ('image','timezone'):
            if self.original.get(key)!=self.data.get(key):lines.append(f'{key}: {self.original.get(key)!r} -> {self.data.get(key)!r}')
        if self.dirty and not lines: lines.append('Group compatibility settings into the plugins section.')
        return lines

    def save(self):
        self.validate()
        actions=self.next_actions()
        dump_config(self.path,self.data,expected=self.revision)
        self.revision=self.path.read_bytes()
        self.original=copy.deepcopy(self.data)
        return actions
