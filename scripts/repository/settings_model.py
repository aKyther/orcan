"""Editable settings draft with explicit review, validation and guarded JSON save."""
from __future__ import annotations

import copy
import contextlib
import io
from pathlib import Path

from config_io import dump_config, load_config
from defaults import RESOURCE_DEFAULTS, TMUX_DEFAULTS, PROCESS_DEFAULTS
from host_config import host_environment
from orcan.image_profile import AGENTS, TOOLS, PYTHONS, agent_entry, tool_entry, requirements, resolve as image_profile
from orcan.plugin_registry import catalog, resolve as resolve_plugins, validate_field, validate_selection, change_selection


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
        self.data['plugins'] = change_selection(draft, name, not draft[name]['enabled'])

    def set_plugin(self, name, key, value):
        entry=next(entry for entry in catalog() if entry['id']==name)
        checked=validate_field(name,key,value,entry['fields'][key])
        self._plugin_draft()[name][key]=checked

    def agents(self):
        return {entry['name']:entry for entry in (agent_entry(value) for value in self.data.get('build',{}).get('agents',[]))}

    def tools(self):
        if 'build' not in self.data: return set(TOOLS)
        return {value if isinstance(value,str) else value['name'] for value in self.data['build'].get('tools',[])}

    def _build_draft(self):
        if 'build' not in self.data:
            self.data['build']={'agents':[],'tools':sorted(TOOLS),'python':['3.13']}
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
        if name not in TOOLS: raise ValueError('Unknown toolchain')
        enabled=self.tools()
        build=self._build_draft()
        if name in enabled:
            build['tools']=[value for value in build.get('tools',[]) if (value if isinstance(value,str) else value['name'])!=name]
        else: build.setdefault('tools',[]).append(name)

    def set_tool_image(self, name, image):
        value = tool_entry({'name':name, 'image':image})
        if name not in self.tools(): raise ValueError('Enable the toolchain first')
        build = self._build_draft()
        build['tools'] = [value if (entry if isinstance(entry,str) else entry['name']) == name else entry
                          for entry in build['tools']]

    def requirements(self):
        # Drafts may temporarily contain no agent while the selection is edited.
        profile = {'agents':list(self.agents().values()),
                   'python':self.python_versions(), 'tools':[tool_entry(value) for value in self.data.get('build',{}).get('tools',sorted(TOOLS))]}
        plugins = self.plugins()
        return requirements(profile, [entry for entry in catalog() if plugins[entry['id']]['enabled']])

    def set_tool_version(self, name, version):
        value=tool_entry({'name':name,'version':version})
        if name not in self.tools(): raise ValueError('Enable the toolchain first')
        build=self._build_draft()
        build['tools']=[value if (entry if isinstance(entry,str) else entry['name'])==name else entry for entry in build['tools']]

    def python_versions(self):
        return self.data.get('build',{}).get('python',[] if 'build' in self.data else ['3.13'])

    def toggle_python(self, version):
        if version not in PYTHONS: raise ValueError('Unsupported Python version')
        selected=list(self.python_versions())
        if version in selected: selected.remove(version)
        else: selected.append(version)
        self._build_draft()['python']=selected

    def default_python(self, version):
        if version not in self.python_versions(): raise ValueError('Enable this Python version first')
        self._build_draft()['python']=[version]+[entry for entry in self.python_versions() if entry!=version]

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

    @staticmethod
    def _effective_config(data, plugins):
        effective = copy.deepcopy(data)
        effective['resources'] = RESOURCE_DEFAULTS | PROCESS_DEFAULTS | data.get('resources', {})
        effective['tmux'] = TMUX_DEFAULTS | data.get('tmux', {})
        effective['image'] = data.get('image', 'orcan:latest')
        effective['timezone'] = data.get('timezone', 'UTC')
        effective['plugins'] = plugins
        for legacy in ('executor', 'executor_port', 'ttyd'):
            effective.pop(legacy, None)
        return effective

    @property
    def effective_dirty(self):
        return self._effective_config(self.data, self.plugins()) != self._effective_config(self.original, resolve_plugins(self.original))

    def next_actions(self):
        if not self.dirty: return []
        old = self._effective_config(self.original, resolve_plugins(self.original))
        new = self._effective_config(self.data, self.plugins())
        # Even representation-only saves change file freshness. Sync prepares
        # those files, but no build/startup action follows unchanged values.
        if old == new: return ['orcan sync']
        actions=['orcan sync']
        build_changed = new.get('build') != old.get('build')
        if build_changed: actions.append('orcan build')
        startup_changed = build_changed or any(
            new.get(key) != old.get(key)
            for key in ('image', 'timezone', 'resources', 'workspaces', 'plugins')
        )
        if startup_changed:
            actions += ['orcan up --plan', 'orcan up (after active background jobs finish)']
        return actions

    def application_notes(self):
        notes = ['Reviewing a draft; saving writes desired configuration only. Running state is not inspected.']
        if (TMUX_DEFAULTS | self.data.get('tmux', {})) != (TMUX_DEFAULTS | self.original.get('tmux', {})):
            notes.append('Tmux defaults changed; existing sessions are not restarted or reconfigured by saving.')
        if self.dirty and not self.effective_dirty:
            notes.append('Only explicit defaults or configuration layout changed; sync refreshes prepared files without build or startup.')
        elif self.next_actions() == ['orcan sync']:
            notes.append('No startup/image change in this draft; a container restart is not prescribed.')
        return notes

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
            lines.append('Project Python (first is default): '+(', '.join(self.python_versions()) or 'none; core runtimes remain'))
            lines.append('Image toolchains: '+(', '.join(entry['name']+'@'+entry.get('image',entry.get('version','')) for entry in self.requirements()['optional_toolchains']) or 'none'))
        for section,defaults in (('resources',RESOURCE_DEFAULTS | PROCESS_DEFAULTS),('tmux',TMUX_DEFAULTS)):
            old=defaults | self.original.get(section,{})
            new=defaults | self.data.get(section,{})
            for key,value in new.items():
                if old.get(key)!=value:
                    lines.append(f'{section}.{key}: {old.get(key)!r} -> {value!r}')
                elif (key in self.original.get(section, {})) != (key in self.data.get(section, {})):
                    before = 'explicit' if key in self.original.get(section, {}) else 'default'
                    after = 'explicit' if key in self.data.get(section, {}) else 'default'
                    lines.append(f'{section}.{key}: {before} {value!r} -> {after} {value!r} (effective value unchanged)')
        for key in ('image','timezone'):
            if self.original.get(key)!=self.data.get(key):lines.append(f'{key}: {self.original.get(key)!r} -> {self.data.get(key)!r}')
        if self.dirty and not lines: lines.append('Configuration representation changed; effective settings are unchanged.' if not self.effective_dirty else 'Configuration changed; review the apply steps.')
        return lines

    def save(self):
        self.validate()
        actions=self.next_actions()
        dump_config(self.path,self.data,expected=self.revision)
        self.revision=self.path.read_bytes()
        self.original=copy.deepcopy(self.data)
        return actions
