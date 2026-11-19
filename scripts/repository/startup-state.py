#!/usr/bin/env python3
"""Content fingerprints and atomic, credential-free startup receipts."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

# Explicit image inputs only: never walk a checkout/config root or client data.
INPUTS = ('Dockerfile', '.dockerignore', 'docker/installers', 'docker/rootfs',
          'plugins', 'requirements-actions.txt', 'VERSION')


def input_files(root: Path, path: Path) -> list[Path]:
    if not path.is_dir():
        return [path]
    result = []
    generated = {'.venv', '.venv-docs', '__pycache__', '.pytest_cache', '.ruff_cache',
                 '.mypy_cache', 'node_modules', '.git'}
    for current, directories, files in os.walk(path, followlinks=False):
        directory = Path(current)
        relative = directory.relative_to(root).parts
        excluded = generated | ({'tests', 'smoke'} if len(relative) == 2 and relative[0] == 'plugins' else set())
        directories[:] = sorted(name for name in directories if name not in excluded)
        result.extend(directory / name for name in directories if (directory / name).is_symlink())
        result.extend(directory / name for name in files
                      if not name.endswith('.pyc') and name != '.env' and not name.startswith('.env.'))
    return sorted(result)


def fingerprint(root: Path, profile: str, identity: str) -> str:
    digest = hashlib.sha256((profile + '\n' + identity).encode())
    for name in INPUTS:
        path = root / name
        paths = input_files(root, path)
        for entry in paths:
            if '__pycache__' in entry.parts or entry.suffix == '.pyc':
                continue
            relative = str(entry.relative_to(root))
            if entry.is_symlink():
                value = os.readlink(entry).encode()
            elif entry.is_file():
                value = entry.read_bytes()
            else:
                continue
            digest.update(relative.encode() + b'\0' + str(entry.lstat().st_mode).encode() + b'\0')
            digest.update(hashlib.sha256(value).digest())
    return digest.hexdigest()


def write(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(value, stream)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    hash_parser = sub.add_parser('fingerprint')
    hash_parser.add_argument('--root', type=Path, required=True)
    hash_parser.add_argument('--profile', required=True)
    hash_parser.add_argument('--identity', required=True)
    for name in ('matches', 'record'):
        command = sub.add_parser(name)
        command.add_argument('--file', type=Path, required=True)
        command.add_argument('--fingerprint', required=True)
        command.add_argument('--image-id', required=True)
    status = sub.add_parser('status')
    status.add_argument('--file', type=Path, required=True)
    status.add_argument('--stage', choices=('prepare', 'image', 'preflight', 'start', 'verify', 'ready'), required=True)
    args = parser.parse_args()
    if args.action == 'fingerprint':
        print(fingerprint(args.root, args.profile, args.identity))
    elif args.action == 'record':
        write(args.file, {'version': 1, 'fingerprint': args.fingerprint, 'image_id': args.image_id})
    elif args.action == 'status':
        write(args.file, {'version': 1, 'stage': args.stage})
    else:
        try: receipt = json.loads(args.file.read_text())
        except (OSError, ValueError): raise SystemExit(1) from None
        raise SystemExit(not (receipt.get('fingerprint') == args.fingerprint and receipt.get('image_id') == args.image_id))


if __name__ == '__main__': main()
