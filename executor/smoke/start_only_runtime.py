"""Exercise startup permission checks in a private, read-only runtime container."""
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[2]


def main():
    script=r'''
source /dev/stdin
mkdir -p "$HOME/.cache/external"
chmod 0555 "$HOME/.cache/external"
find() { echo UNEXPECTED_SCAN >&2; return 91; }
chown() { echo UNEXPECTED_CHOWN >&2; return 92; }
sudo() { echo UNEXPECTED_SUDO >&2; return 93; }
check_runtime_directory_permissions
[[ "$(stat -c '%a' "$HOME/.cache/external")" == 555 ]]
chmod 0555 "$HOME/.cache"
if check_runtime_directory_permissions; then exit 94; fi
[[ "$(stat -c '%a' "$HOME/.cache")" == 555 ]]
printf 'START_ONLY_PERMISSIONS_OK\n'
'''
    name='orcan-start-only-'+uuid4().hex[:12]
    try:
        result=subprocess.run(['docker','run','--rm','--name',name,'-i','--pull','never','--network','none',
            '--read-only','--user','1000:1000','--memory','96m','--cpus','0.25','--pids-limit','32',
            '--tmpfs','/work:rw,mode=1777,size=4m','--env','HOME=/work','--entrypoint','bash',
            os.environ.get('ORCAN_JSON_SMOKE_IMAGE','orcan:4.0.17'),'-ec',script],
            input=(ROOT/'docker/rootfs/usr/local/bin/docker-entrypoint').read_bytes(),
            capture_output=True,timeout=45)
    finally:
        subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15,check=False)
    if result.returncode or b'START_ONLY_PERMISSIONS_OK' not in result.stdout or b'UNEXPECTED' in result.stderr:
        raise RuntimeError(result.stderr.decode(errors='replace')[-1800:] or 'Startup permissions smoke did not complete')
    print(json.dumps({'status':'passed','checks':2,'ownership_changes':False,'live_runtime_changed':False}))


if __name__=='__main__':main()
