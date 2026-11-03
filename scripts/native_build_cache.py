"""Authenticated encrypted Bazel disk-cache baseline; only ciphertext goes to Actions cache.

The random existing export secret is domain-separated into independent cipher and MAC keys.
An untrusted cache is authenticated before OpenSSL or tar reads it. No credentials/IPA,
output trees, arbitrary paths, or symlinks are selected from the runner filesystem.
"""
import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile

MAX_ENCRYPTED = 7 * 1024**3
MAX_EXPANDED = 20 * 1024**3
MAX_FILES = 300_000
BLOCK = 1024**2


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def keys():
    secret = os.environ.get('IPA_EXPORT_PASSWORD', '').encode()
    if len(secret) < 32:
        raise ValueError('Cache secret is unavailable')
    return tuple(hmac.digest(secret, label, 'sha256') for label in
                 (b'VisualGram/BazelCache/v1/cipher', b'VisualGram/BazelCache/v1/auth'))


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(BLOCK), b''):
            result.update(block)
    return result.hexdigest()


def valid_name(name):
    parts = PurePosixPath(name).parts
    return (len(parts) in (2, 3) and parts[0] in ('ac', 'cas') and
            all(re.fullmatch('[a-f0-9]{2,128}', part) is not None for part in parts[1:]))


def cipher(source, destination, decrypt=False):
    enc, _ = keys()
    env = {**os.environ, 'VG_CACHE_CIPHER': enc.hex()}
    args = [os.environ.get('VG_OPENSSL', 'openssl'), 'enc', '-aes-256-cbc',
            '-salt', '-saltlen', '8', '-pbkdf2', '-iter', '200000', '-md', 'sha256',
            '-pass', 'env:VG_CACHE_CIPHER']
    if decrypt:
        args.append('-d')
    with source.open('rb') as src, destination.open('wb') as dst:
        subprocess.run(args, stdin=src, stdout=dst, stderr=subprocess.DEVNULL, env=env, check=True)


def seal(cache, bundle, context, max_encrypted=MAX_ENCRYPTED, max_expanded=MAX_EXPANDED):
    cache, bundle = Path(cache), Path(bundle)
    files = []
    total = 0
    for folder in ('ac', 'cas'):
        base = cache / folder
        if base.is_symlink():
            raise ValueError('Cache directory is a symlink')
        for path in sorted(base.rglob('*')):
            if path.is_symlink():
                raise ValueError('Cache contains symlink')
            if not path.is_file():
                continue
            name = path.relative_to(cache).as_posix()
            if not valid_name(name):
                continue
            total += path.stat().st_size
            files.append((path, name))
    if not files or total > max_expanded or len(files) > MAX_FILES:
        print('CACHE: baseline not saved (empty or above local size limit)')
        return False
    bundle.mkdir(parents=True, exist_ok=True)
    blob = bundle / 'cache.enc'
    with tempfile.TemporaryDirectory(prefix='vg-cache-seal-', dir=bundle.parent) as temporary:
        archive = Path(temporary) / 'cache.tar.gz'
        with tarfile.open(archive, 'w:gz', compresslevel=1) as tar:
            for path, name in files:
                tar.add(path, arcname=name, recursive=False)
        if archive.stat().st_size + 128 > max_encrypted:
            print('CACHE: baseline not saved (encrypted archive would exceed 7 GiB)')
            return False
        cipher(archive, blob)
    metadata = dict(schema=1, context=context, bytes=blob.stat().st_size,
                    expanded_bytes=total, files=len(files), sha256=digest(blob))
    _, mac = keys()
    manifest = dict(metadata=metadata, tag=hmac.digest(mac, canonical(metadata), 'sha256').hex())
    (bundle / 'manifest.json').write_bytes(canonical(manifest))
    print(f'CACHE: sealed {len(files)} files, raw={total}, encrypted={metadata["bytes"]}')
    return True


def restore(cache, bundle, context, max_encrypted=MAX_ENCRYPTED, max_expanded=MAX_EXPANDED):
    cache, bundle = Path(cache), Path(bundle)
    blob, manifest_path = bundle / 'cache.enc', bundle / 'manifest.json'
    if not blob.is_file() or not manifest_path.is_file():
        print('CACHE: no encrypted baseline; clean build')
        return False
    if blob.is_symlink() or manifest_path.is_symlink() or manifest_path.stat().st_size > 8192:
        raise ValueError('Invalid cache envelope')
    manifest = json.loads(manifest_path.read_bytes())
    metadata = manifest['metadata']
    _, mac = keys()
    if not hmac.compare_digest(hmac.digest(mac, canonical(metadata), 'sha256').hex(), manifest['tag']):
        raise ValueError('Cache authentication failed')
    if metadata['schema'] != 1 or metadata['context'] != context:
        raise ValueError('Cache toolchain differs')
    if (not 0 < blob.stat().st_size == metadata['bytes'] <= max_encrypted or
            not 0 <= metadata['expanded_bytes'] <= max_expanded or
            not 0 < metadata['files'] <= MAX_FILES or digest(blob) != metadata['sha256']):
        raise ValueError('Cache size or digest differs')
    # Do not merge into a live cache or overwrite existing runner files.
    if cache.exists() and (cache.is_symlink() or any(cache.iterdir())):
        raise ValueError('Destination cache is not empty')
    cache.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='vg-cache-restore-', dir=cache.parent) as temporary:
        staging = Path(temporary) / 'disk-cache'
        staging.mkdir()
        archive = Path(temporary) / 'cache.tar.gz'
        cipher(blob, archive, decrypt=True)
        with tarfile.open(archive, 'r:gz') as tar:
            entries = tar.getmembers()
            names = set()
            total = 0
            for entry in entries:
                if not entry.isfile() or not valid_name(entry.name) or entry.name in names:
                    raise ValueError('Unsafe cache archive member')
                names.add(entry.name)
                total += entry.size
                if total > max_expanded or len(names) > MAX_FILES:
                    raise ValueError('Cache archive exceeds limits')
            if total != metadata['expanded_bytes'] or len(entries) != metadata['files']:
                raise ValueError('Cache archive totals differ')
            if shutil.disk_usage(cache.parent).free < total + 1024**3:
                raise ValueError('Not enough disk space for cache')
            for entry in entries:
                target = staging.joinpath(*PurePosixPath(entry.name).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(entry) as src, target.open('wb') as dst:
                    shutil.copyfileobj(src, dst, length=BLOCK)
                os.chmod(target, 0o600)
        if cache.exists():
            cache.rmdir()  # Verified empty above; never recursive-delete an existing cache.
        staging.replace(cache)
    print(f'CACHE: authenticated and restored {len(entries)} files ({total} bytes)')
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['seal', 'restore'])
    parser.add_argument('cache', type=Path)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('context', type=Path)
    args = parser.parse_args()
    context = json.loads(args.context.read_bytes())
    try:
        result = globals()[args.command](args.cache, args.bundle, context)
        if args.command == 'seal' and os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
                output.write(f'ready={str(result).lower()}\n')
    except (ValueError, OSError, KeyError, TypeError, tarfile.TarError, subprocess.CalledProcessError):
        # Cache is optional. Never print file contents, secrets or parser diagnostics.
        print('CACHE: unavailable or rejected; clean build will be used')
        if args.command == 'seal':
            raise SystemExit(1)
