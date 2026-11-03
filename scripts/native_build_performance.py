"""Opt-in CI resource sizing. Never changes release/optimization/signing settings."""
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess


def select_jobs(cpus, memory):
    if cpus >= 6 and memory >= 32 * 1024**3:
        return 4
    if cpus >= 4 and memory >= 24 * 1024**3:
        return 3
    return 2


def configure(root):
    root = Path(root)
    cpus = os.cpu_count() or 2
    memory = int(subprocess.check_output(['sysctl', '-n', 'hw.memsize'], text=True))
    jobs = select_jobs(cpus, memory)
    rc = root / '.bazelrc'
    text = rc.read_text(encoding='utf-8')
    assert text.count('build --jobs=2\n') == 1, 'Unexpected concurrency configuration'
    rc.write_text(text.replace('build --jobs=2\n', f'build --jobs={jobs}\n'), encoding='utf-8')
    # Keep a fixed baseline cache for this pinned toolchain: no per-run storage growth.
    context = dict(schema=1, upstream='279f89e4d4f63f17227bf877dc3d8990f22ecd58',
                   xcode=subprocess.check_output(['xcodebuild', '-version'], text=True).strip(),
                   bazel='9.2.0', arch=platform.machine(), os=platform.mac_ver()[0], configuration='release_arm64')
    context_path = Path(os.environ['RUNNER_TEMP']) / 'native-cache-context.json'
    context_path.write_text(json.dumps(context, sort_keys=True), encoding='utf-8')
    print(f'BUILD RESOURCES: logical_cpus={cpus}, memory_gib={memory / 1024**3:.1f}, jobs={jobs}')
    print('Cache baseline: encrypted, immutable, maximum 7 GiB; unavailable cache falls back to a clean build')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source')
    configure(parser.parse_args().source)
