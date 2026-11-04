"""Layer isolation, dependency caching, and scoped installation cleanup."""
import os
from pathlib import Path
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[2]


def test_sdk_stages_are_independent_of_source_versions_and_host_ids():
    recipe=(ROOT/'Dockerfile').read_text()
    core=recipe.split(' AS core',1)[1].split('FROM core AS jvm-installer',1)[0]
    assert 'COPY docker/rootfs/' not in core
    assert 'USER_UID' not in core
    for tool,var in [('jdk','JAVA'),('gradle','GRADLE'),('maven','MAVEN'),('kotlin','KOTLIN'),('scala','SCALA'),('sbt','SBT')]:
        stage=recipe.split(' AS '+tool+'-tools',1)[1].split('\nFROM ',1)[0]
        assert 'ARG '+var+'_VERSION=' in stage
        assert '/usr/local/libexec/orcan-install-jvm '+tool in stage
        assert 'COPY cockpit/' not in stage
    assert recipe.count('downloads/glab_')==1
    assert 'COPY --from=runtime / /' not in recipe


def test_dependency_stages_install_locks_before_runtime_source():
    recipe=(ROOT/'Dockerfile').read_text()
    for name in ('cockpit','executor'):
        stage=recipe.split(' AS '+name+'-deps',1)[1].split('\nFROM ',1)[0]
        assert f'COPY {name}/pyproject.toml {name}/uv.lock' in stage
        assert '--no-install-project' in stage
        assert 'type=cache,id=orcan-' in stage
        assert f'COPY {name}/ /' not in stage


@pytest.mark.integration
@pytest.mark.parametrize('component',['jdk','gradle','maven','kotlin','scala','sbt'])
def test_disabled_sdk_never_downloads_or_leaves_archives(tmp_path,component):
    script='''set -Eeuo pipefail
curl() { echo UNEXPECTED_DOWNLOAD >&2; return 99; }
export -f curl
bash "$INSTALLER" "$COMPONENT" 0 21 "$DESTINATION"
'''
    destination=tmp_path/'sdk'
    result=subprocess.run(['bash','-c',script],env={**os.environ,'INSTALLER':str(ROOT/'docker/installers/install-jvm.sh'),'COMPONENT':component,'DESTINATION':str(destination)},capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert list(destination.iterdir())==[]


@pytest.mark.integration
def test_failed_sdk_download_cleans_only_its_own_temporary_directory(tmp_path):
    survivor=tmp_path/'keep';survivor.write_text('user data')
    script='''set -Eeuo pipefail
curl() { return 42; }
export -f curl
bash "$INSTALLER" gradle 1 8.11 "$DESTINATION"
'''
    result=subprocess.run(['bash','-c',script],env={**os.environ,'INSTALLER':str(ROOT/'docker/installers/install-jvm.sh'),'DESTINATION':str(tmp_path/'sdk'),'TMPDIR':str(tmp_path)},capture_output=True,text=True)
    assert result.returncode==42
    assert survivor.read_text()=='user data'
    assert not list(tmp_path.glob('tmp.*'))
