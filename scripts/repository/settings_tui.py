#!/usr/bin/env python3
"""Stdlib terminal settings UI. Edit a draft, review, then explicitly save JSON."""
from __future__ import annotations

import argparse
import curses
import subprocess
import sys
import textwrap
from pathlib import Path

from settings_model import SettingsModel
from context_tui import _init_curses_session, _prompt_line
from defaults import RESOURCE_DEFAULTS, TMUX_DEFAULTS, PROCESS_DEFAULTS
from orcan.image_profile import AGENTS, IMAGES, TOOLS, PYTHONS, TOOL_HELP
from orcan.plugin_registry import catalog


def safe_text(text):
    return ''.join(character if character.isprintable() else ' ' for character in str(text))


def guidance_rows(lines, width):
    result=[]
    for line in lines:
        for part in textwrap.wrap(safe_text(line), max(12, width-2), break_long_words=True, break_on_hyphens=False):
            result.append((None,part,''))
    return result


def detail_rows(model, page, width=100):
    if page=='plugins':
        values=model.plugins()
        return [(entry['id'],f"{entry['group'].capitalize()} / [{'x' if values[entry['id']]['enabled'] else ' '}] {entry['title']}",entry['id']+(' requires: '+', '.join(entry['requires']) if entry.get('requires') else '')+(' conflicts: '+', '.join(entry['conflicts']) if entry.get('conflicts') else '')) for entry in catalog() if entry.get('configurable',True)]
    if page.startswith('plugin:'):
        name=page.split(':',1)[1]
        entry=next(entry for entry in catalog() if entry['id']==name)
        values=model.plugins()[name]
        result=[('__enabled__','Enabled',str(values['enabled']))]
        for key,rule in entry['fields'].items():
            result.append((key,rule['label'],str(values[key])))
            limits=[]
            if 'choices' in rule: limits.append('Choices: '+', '.join(map(str,rule['choices'])))
            if 'minimum' in rule: limits.append('Range: '+str(rule['minimum'])+' to '+str(rule['maximum']))
            result.extend(guidance_rows(([rule['help']] if rule.get('help') else [])+limits,width))
        result.extend(guidance_rows(['Settings: plugins.'+name+' in orcan.config.json','Copyable help/examples: orcan plugins help --plugin '+name]+entry.get('help',[])+['Example JSON: '+example for example in entry['examples']],width))
        return result
    if page=='agents':
        agents=model.agents(); tools=model.tools()
        dependencies=model.requirements()
        effective={entry['name']:entry for entry in dependencies['optional_toolchains']}
        return [('agent:'+name,f"[{'x' if name in agents else ' '}] {name}",agents[name]['version'] if name in agents else 'not selected') for name in sorted(AGENTS)]+[('tool:'+name,f"[{'x' if name in tools else '+' if name in effective else ' '}] {name}",effective.get(name,{}).get('image',effective.get(name,{}).get('version','not selected'))) for name in sorted(TOOLS)]+[('python:'+version,f"[{'x' if version in model.python_versions() else ' '}] Python {version}",'default for projects' if model.python_versions()[:1]==[version] else 'optional project runtime') for version in PYTHONS]+[(None,'Required runtimes (included in base)',', '.join(sorted({dep for deps in dependencies['agents'].values() for dep in deps})))]+[(None,'Python dependencies','cockpit/executor lockfiles')]+guidance_rows([
            'Project tools: [x] direct selection, [+] required by another selected tool. Orcan core stays installed.',
            'Example Java/Gradle: choose gradle; JDK is included automatically. Kotlin, sbt, Go and Rust are not needed for this selection.',
            'build.gradle.kts uses the Kotlin DSL bundled with Gradle; a standalone Kotlin compiler is not required for that alone.',
            'If your projects do not use Go or Rust, leave them unselected to avoid installing their toolchains.',
            'Python: Space selects one or several project runtimes; Enter makes an enabled version the default. Internal service runtimes remain separate.',
            'Saving changes JSON only. run sync for configuration, build for image changes, then up to start. build --plan shows requirements.',
            'Inspect build storage with orcan build --check-space. Low verified Docker free space warns; nothing is deleted.',
            'Inspect host image/cache usage with docker system df. --prune removes only dangling Orcan images; it does not clear BuildKit cache.',
            *[name+': '+TOOL_HELP[name] for name in sorted(TOOLS)]
        ],width)
    if page=='container':
        resources=RESOURCE_DEFAULTS | PROCESS_DEFAULTS | model.data.get('resources',{})
        return [('image','Docker image',model.data.get('image','orcan:latest')),('timezone','Timezone',model.data.get('timezone','UTC'))]+[(key,key.replace('_',' ').capitalize(),str(value)) for key,value in resources.items()]+guidance_rows(['Image: local Docker tag for Orcan. Image contents are selected in Agents and image.', 'CPU and memory are shared by all processes and executor workers in this container, not assigned per worker.', 'Memory accepts Docker sizes, for example 4g. shm_size and tmpfs_size are separate size limits.', 'Changing these settings can recreate the container on the next up and interrupt attached sessions. Saving settings alone does not restart anything.'],width)
    if page=='tmux':
        values=TMUX_DEFAULTS | model.data.get('tmux',{})
        return [(key,key.replace('_',' ').capitalize(),str(value)) for key,value in values.items()]
    if page=='workspaces':
        workspaces=model.data.get('workspaces',[])
        return [('manage','Open workspace manager','Save or discard this draft first' if model.dirty else 'Workspace changes have their own review/save')]+[(None,ws.get('name','unnamed'),str(len(ws.get('projects',[])))+' projects') for ws in workspaces]
    if page=='review':
        actions = [('save', 'Save reviewed settings', 'Enter or s'),
                   ('back', 'Back to editing', 'Keep this draft'),
                   ('discard', 'Discard changes and close', 'Confirmation required')]
        return actions + [(None,line,'') for line in model.review()] + guidance_rows(model.application_notes(),width)
    return []


def rows(model, page, width=100):
    """Keep setup choices short; full package guidance is a separate view."""
    if page.startswith('help:'):
        source = page.removeprefix('help:')
        return [(None, label, value) for _, label, value in detail_rows(model, source, width)]
    if page == 'home':
        return [
            ('workspaces', 'Workspaces and projects', 'Choose where you work'),
            ('agents', 'Agents and tools', 'Choose what is installed'),
            ('container', 'Resources', 'CPU, memory and container settings'),
            ('plugins', 'Optional services', 'Enable and configure integrations'),
            ('tmux', 'Terminal layout', 'Windows and history'),
            ('review', 'Review and save', 'Changes and next steps'),
            ('reload', 'Reload configuration', 'Discard this draft'),
        ]
    result = detail_rows(model, page, width)
    if page.startswith('plugin:'):
        name = page.split(':', 1)[1]
        editable = [row for row in result if row[0] is not None]
        # Disabled services retain their configured values without displaying a form.
        if not model.plugins()[name]['enabled']:
            editable = editable[:1]
        return editable + [('help:' + page, 'Setup help and examples', 'Open details')]
    if page == 'agents':
        return [row for row in result if row[0] is not None] + [
            ('help:agents', 'Tool descriptions and build help', 'Open details')]
    return result


def parent_page(page):
    if page.startswith('help:'):
        return page.removeprefix('help:')
    return 'plugins' if page.startswith('plugin:') else 'home'


def confirm(screen,label):
    answer=_prompt_line(screen,label+' [y/N]','')
    return answer is not None and answer.lower() in ('y','yes')


def draw(screen,model,page,selected,message):
    screen.erase()
    height,width=screen.getmaxyx()
    def text(row,value,attr=0):
        if 0<=row<height and width>1:
            try: screen.addnstr(row,0,safe_text(value),width-1,attr)
            except curses.error: pass
    text(0,'Orcan settings  /  '+page.replace('plugin:','Plugin: ')+('  * unsaved' if model.dirty else ''),curses.A_BOLD)
    text(1,str(model.path))
    if page=='agents': text(2,'Image contents only. Saving does not install or start agents; use orcan sync, orcan build, then orcan up.')
    elif page=='review': text(2,'Enter: selected action  s: save  Esc: back  | Next: '+' -> '.join(model.next_actions()))
    elif page.startswith('help:'):text(2,'Up/Down: scroll  Esc: back to settings')
    elif page=='home':text(2,'Enter: open  q: exit  r: review  s: review/save')
    else:text(2,'Space: toggle  Enter: edit/open  Esc: back  r: review  s: review/save')
    items=rows(model,page,width)
    selected=max(0,min(selected,max(0,len(items)-1)))
    visible=max(1,height-6)
    start=max(0,selected-visible+1)
    for index,(_,label,value) in enumerate(items[start:start+visible],start):
        text(4+index-start,f'{label}'+('  '+value if value else ''),curses.A_REVERSE if index==selected else 0)
    text(height-2,message)
    text(height-1,'Nothing runs on save. JSON is the only settings file; credentials stay outside it.')
    screen.refresh()
    return selected,items


def run_screen(screen,model):
    _init_curses_session()
    try:curses.curs_set(0)
    except curses.error:pass
    screen.keypad(True)
    page='home'; selected=0; message=''
    while True:
        selected,items=draw(screen,model,page,selected,message)
        try:key=screen.get_wch()
        except curses.error:continue
        if key==curses.KEY_RESIZE:continue
        if key in (curses.KEY_DOWN,'j'):selected=min(max(0,len(items)-1),selected+1);continue
        if key in (curses.KEY_UP,'k'):selected=max(0,selected-1);continue
        if key in ('q','\x03'):
            if not model.dirty or confirm(screen,'Discard unsaved changes?'):return 'cancel',[]
            continue
        if key in ('\x1b',curses.KEY_LEFT):
            page=parent_page(page);selected=0;message='';continue
        if key=='r':page='review';selected=0;continue
        save_selected = (
            page == 'review' and key in ('\n','\r',curses.KEY_ENTER,' ')
            and items and items[selected][0] == 'save'
        )
        if key=='s' or save_selected:
            if page!='review':page='review';selected=0;continue
            if not model.dirty:message='No changes to save.';continue
            try:
                model.validate()
                if confirm(screen,'Save the reviewed settings?'):
                    return 'saved',model.save()
            except (ValueError,OSError,SystemExit) as error:message=str(error)
            continue
        if key not in (' ','\n','\r',curses.KEY_ENTER,'e') or not items:continue
        item=items[selected][0]
        if item is None:continue
        try:
            if page == 'review':
                if item == 'back': page='home';selected=0;message='';continue
                if item == 'discard':
                    if not model.dirty or confirm(screen,'Discard unsaved changes?'): return 'cancel',[]
                    continue
            if item.startswith('help:'):
                page=item;selected=0;message='';continue
            if page=='home':
                if item=='reload':
                    if not model.dirty or confirm(screen,'Discard this draft and reload?'): return 'reload',[]
                    continue
                page=item;selected=0;message='';continue
            if page=='plugins':
                if key==' ':model.toggle_plugin(item)
                else:page='plugin:'+item;selected=0
            elif page.startswith('plugin:'):
                name=page.split(':',1)[1]
                if item=='__enabled__':
                    model.toggle_plugin(name)
                    continue
                rule=next(entry for entry in catalog() if entry['id']==name)['fields'][item]
                current=model.plugins()[name][item]
                if rule['type']=='boolean':model.set_plugin(name,item,not current)
                else:
                    value=_prompt_line(screen,rule['label'],str(current))
                    if value is not None:model.set_plugin(name,item,int(value) if rule['type']=='integer' else value)
            elif page=='agents':
                kind,name=item.split(':',1)
                if kind=='tool':
                    if key==' ' or name not in model.tools(): model.toggle_tool(name)
                    else:
                        current=next(entry.get('image',entry.get('version','')) for entry in model.requirements()['optional_toolchains'] if entry['name']==name)
                        value=_prompt_line(screen,('Source image for ' if name in IMAGES else 'Version for ')+name,current)
                        if value is not None:
                            if name in IMAGES:model.set_tool_image(name,value)
                            else:model.set_tool_version(name,value)
                elif kind=='python':
                    if key==' ' or name not in model.python_versions():model.toggle_python(name)
                    else:model.default_python(name)
                elif key==' ' or name not in model.agents():model.toggle_agent(name)
                else:
                    value=_prompt_line(screen,'Version for '+name,model.agents()[name]['version'])
                    if value is not None:model.set_agent_version(name,value)
            elif page in ('container','tmux'):
                current=items[selected][2]
                value=_prompt_line(screen,items[selected][1],current)
                if value is not None:
                    if page=='tmux':model.set_tmux(item,int(value) if item in ('initial_windows','history_limit') else value)
                    else:model.set_resource(item,float(value) if item=='cpus' else int(value) if item in PROCESS_DEFAULTS else value)
            elif page=='workspaces' and item=='manage':
                if model.dirty:message='Save or discard this settings draft before opening the workspace manager.'
                else:return 'workspaces',[]
        except (ValueError,OSError,SystemExit) as error:message=str(error)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    args=parser.parse_args()
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise SystemExit('orcan settings needs a terminal; use --cli for the sequential wizard')
    while True:
        model=SettingsModel(args.config)
        try:action,steps=curses.wrapper(run_screen,model)
        except KeyboardInterrupt:action,steps='cancel',[]
        if action=='reload': continue
        if action=='workspaces':
            subprocess.run([sys.executable,str(Path(__file__).with_name('context_tui.py')),'--config',str(model.path)],check=False)
            continue
        if action=='saved':
            print('Saved '+str(model.path))
            print('Desired configuration saved; running state was not changed or checked.')
            for step in steps:print('Next: '+step)
        else:print('Settings closed without saving.')
        return


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,curses.error) as error:raise SystemExit('orcan: '+str(error)) from None
