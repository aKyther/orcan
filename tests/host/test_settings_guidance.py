"""Package-owned configuration help and dependency-aware image selections."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import pytest
from ._scripts_loader import load_script
ui=load_script('settings_tui.py')
from orcan.image_profile import resolve, build_environment
from orcan.plugin_registry import catalog
ROOT=Path(__file__).resolve().parents[2]


def test_all_plugins_have_setup_and_valid_configuration_examples():
    for entry in catalog():
        assert entry['help'] and entry['examples']
        for example in entry['examples']:
            assert isinstance(json.loads(example),dict)


def test_plugin_help_wraps_in_narrow_terminal_without_editing_settings(tmp_path):
    path=tmp_path/'orcan.config.json';path.write_text('{"workspaces":[]}')
    model=ui.SettingsModel(path)
    rows=ui.rows(model,'help:plugin:ssh',width=45)
    assert all(key is None for key, _, _ in rows)
    assert all(len(label)<=43 for key,label,value in rows if key is None)
    text=' '.join(label for key,label,value in rows)
    assert 'SSH_AUTH_SOCK' in text and 'private key' in text
    assert not model.dirty


def test_gradle_closure_keeps_unneeded_compilers_out():
    profile=resolve({'build':{'agents':['codex'],'tools':['gradle']}})
    assert {entry['name'] for entry in profile['tools']}=={'gradle','jdk'}
    env=build_environment(profile)
    assert env['INSTALL_JAVA']==env['INSTALL_GRADLE']=='1'
    assert all(env['INSTALL_'+name]=='0' for name in ['KOTLIN','SCALA','SBT','GO','RUST','MAVEN'])
    assert env['GO_IMAGE']==env['RUST_IMAGE']=='debian:bookworm-slim'


@pytest.mark.parametrize('versions',[[],['3.13'],['3.11','3.12','3.13']])
def test_project_python_selection_is_preserved(versions):
    profile=resolve({'build':{'agents':['codex'],'tools':[],'python':versions}})
    assert profile['python']==versions
    assert build_environment(profile)['ORCAN_PYTHON_VERSIONS']==' '.join(versions)


def test_python_selection_and_default_are_reviewed_before_save(tmp_path):
    path=tmp_path/'orcan.config.json';path.write_text('{"build":{"agents":["codex"],"tools":[],"python":["3.11"]}}')
    model=ui.SettingsModel(path);model.toggle_python('3.13');model.default_python('3.13')
    assert model.python_versions()==['3.13','3.11']
    assert any('3.13, 3.11' in line for line in model.review())
    model.save()
    assert json.loads(path.read_text())['build']['python']==['3.13','3.11']


@pytest.mark.integration
def test_cli_help_and_plan_reuse_package_documentation(tmp_path):
    path=tmp_path/'orcan.config.json';path.write_text('{"workspaces":[],"plugins":{"ssh":{"enabled":true}}}')
    env={**os.environ,'ORCAN_HOME':str(tmp_path),'CONFIG':str(path)}
    result=subprocess.run(['bash',str(ROOT/'bin/orcan'),'plugins','help','--plugin','ssh'],env=env,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    entry=next(entry for entry in catalog() if entry['id']=='ssh')
    assert all(line in result.stdout for line in entry['help'])
    assert all(example in result.stdout for example in entry['examples'])
    planner=load_script('up-plan.py')
    report=planner.preview(path,tmp_path,[])
    assert report['plugin_help']['ssh']=={'help':entry['help'],'examples':entry['examples']}
    assert not (tmp_path/'mounts').exists()


@pytest.fixture
def executable_directory():
    # /tmp is deliberately noexec in the sandbox; keep these fake binaries private.
    with tempfile.TemporaryDirectory(prefix='.orcan-test.',dir=ROOT) as directory:
        yield Path(directory)


def docker_run_section(start,end):
    text=(ROOT/'Dockerfile').read_text()
    block=text[text.index(start):text.index(end)]
    return block[block.index('RUN ')+4:].replace('\\\n','\n').strip()


@pytest.mark.integration
def test_jvm_install_step_downloads_only_selected_tools_and_cleans_temp(executable_directory):
    tmp_path=executable_directory
    profile=resolve({'build':{'agents':['codex'],'tools':['gradle']}})
    env=build_environment(profile)
    script=(ROOT/'docker/installers/install-jvm.sh').read_text()
    calls=tmp_path/'downloads'
    fake=r'''
curl() { echo "$*" >> "$CALLS"; }
tar() {
    local dest=""
    while (( $# )); do if [[ "$1" == -C ]]; then dest="$2"; break; fi; shift; done
    mkdir -p "$dest/bin"
    printf '#!/bin/sh\nexit 0\n' > "$dest/bin/java"
    chmod +x "$dest/bin/java"
}
unzip() { mkdir -p "$4/gradle-8.11"; }
'''
    outputs=[]
    for name,version,destination in [('jdk','21','java'),('gradle','8.11','gradle')]:
        result=subprocess.run(['bash','-euc',fake+script,'_',name,'1',version,str(tmp_path/'opt'/destination)],env={**os.environ,**env,'CALLS':str(calls),'TMPDIR':str(tmp_path)},capture_output=True,text=True)
        outputs.append(result)
    assert all(output.returncode==0 for output in outputs), [output.stderr[-1000:] for output in outputs]
    downloaded=calls.read_text()
    assert 'adoptium' in downloaded and 'gradle' in downloaded
    assert all(tool not in downloaded for tool in ['kotlin','scala','sbt','maven'])
    assert (tmp_path/'opt/gradle').is_dir()
    assert not list(tmp_path.glob('tmp.*'))


@pytest.mark.integration
@pytest.mark.parametrize('versions',[[],['3.13'],['3.11','3.12','3.13']])
def test_project_python_install_step_links_only_requested_versions(executable_directory,versions):
    tmp_path=executable_directory
    script=docker_run_section('ARG ORCAN_PYTHON_VERSIONS=','# JVM:')
    install=tmp_path/'python';bin_dir=tmp_path/'bin';bin_dir.mkdir()
    script=script.replace('/opt/project-python',str(install)).replace('/usr/local/bin',str(bin_dir))
    fake=r'''
uv() {
    mkdir -p "$4/fake-$5/bin"
    printf '#!/bin/sh\nexit 0\n' > "$4/fake-$5/bin/python$5"
    chmod +x "$4/fake-$5/bin/python$5"
}
'''
    result=subprocess.run(['bash','-euc',fake+script],env={**os.environ,'ORCAN_PYTHON_VERSIONS':' '.join(versions)},capture_output=True,text=True)
    assert result.returncode==0,result.stderr[-1200:]
    for version in ['3.11','3.12','3.13']:
        assert (bin_dir/('python'+version)).exists()==(version in versions)
    if versions: assert ('fake-'+versions[0]) in str((bin_dir/'python3').resolve())


@pytest.mark.integration
def test_cli_build_passes_the_resolved_selection_to_compose(tmp_path):
    path=tmp_path/'orcan.config.json'
    path.write_text('{"build":{"agents":["codex"],"tools":["gradle"],"python":["3.12"]}}')
    script='''set -Eeuo pipefail
source cli/lib/common.sh
source cli/commands/build.sh
orcan_require_docker() { :; }; orcan_require_config_for_build() { :; }; orcan_load_config() { :; }
orcan_build_storage_check() { :; }
orcan_image_build_is_current() { return 1; }; orcan_image_record_build() { :; }
orcan_image_build_local() { printf '%s:%s:%s:%s:%s:%s' "$INSTALL_JAVA" "$INSTALL_GRADLE" "$INSTALL_SBT" "$INSTALL_GO" "$INSTALL_RUST" "$ORCAN_PYTHON_VERSIONS"; }
orcan_cmd_build
'''
    result=subprocess.run(['bash','-euc',script],cwd=ROOT,env={**os.environ,'CONFIG':str(path),'ORCAN_HOME':str(tmp_path)},capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert result.stdout=='1:1:0:0:0:3.12'


def test_tui_distinguishes_required_jdk_from_direct_selection(tmp_path):
    path=tmp_path/'orcan.config.json'
    path.write_text('{"build":{"agents":["codex"],"tools":["gradle"]}}')
    model=ui.SettingsModel(path)
    assert ('tool:jdk','[+] jdk','21') in ui.rows(model,'agents')
    assert 'jdk' not in model.tools()
