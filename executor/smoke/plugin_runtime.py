"""Verify plugin packages in an ephemeral image without models or live services."""
from __future__ import annotations

import io
import json
import os
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode='w') as archive:
        for name in ('plugins.py','plugin_registry.py','image_profile.py'):
            archive.add(ROOT/'docker/rootfs/usr/local/lib/orcan'/name, arcname='usr/local/lib/orcan/'+name)
        archive.add(ROOT/'plugins', arcname='opt/orcan/plugins')
    runner = '''import io,json,os,pathlib,subprocess,tarfile,sys,shutil
with tarfile.open(fileobj=io.BytesIO(sys.stdin.buffer.read())) as archive:
    for entry in archive:
        target=pathlib.Path('/')/entry.name
        if entry.isdir(): target.mkdir(parents=True,exist_ok=True)
        elif entry.isfile():
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(archive.extractfile(entry).read())
os.environ['ORCAN_ROOT']='/opt/orcan'
os.environ['ORCAN_REDIS_ENABLED']='0'
values=json.loads(subprocess.check_output(['orcan-plugins','list'],text=True))
assert {v['id'] for v in values}=={'git','ssh','github','gitlab','docker','network','redis','ttyd','cockpit'}
assert json.loads(subprocess.check_output(['orcan-plugins','validate'],text=True))['valid']
assert json.loads(subprocess.check_output(['orcan-plugins','doctor','--plugin','redis'],text=True))[0]['enabled'] is False
sys.path.insert(0,'/usr/local/lib')
from orcan.image_profile import BASE_COMPONENTS
commands={'python':'python3','openssh':'ssh','redis':'redis-server','supervisor':'supervisord','compose':'docker'}
for component in BASE_COMPONENTS:
    assert shutil.which(commands.get(component,component)), 'Missing required image component: '+component
subprocess.run(['docker','compose','version'],check=True,stdout=subprocess.DEVNULL)
print('PLUGIN_PACKAGES_OK')
'''
    result = subprocess.run(['docker','run','--rm','-i','--user','root','--entrypoint','python3',os.environ.get('ORCAN_JSON_SMOKE_IMAGE','orcan:4.0.17'),'-c',runner],input=payload.getvalue(),capture_output=True,timeout=90)
    if result.returncode or b'PLUGIN_PACKAGES_OK' not in result.stdout:
        raise RuntimeError(result.stderr.decode()[-2000:] or 'Plugin package smoke did not complete')
    print(json.dumps({'status':'passed','checks':4,'models_invoked':0}))


if __name__ == '__main__': main()
