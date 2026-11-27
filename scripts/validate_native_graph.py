"""Analyze the full signed-device target without executing compilation actions."""
import os
from pathlib import Path
import subprocess
import sys


def validate(root):
    root = Path(root).resolve()
    rc = root / '.bazelrc'
    original = rc.read_bytes()
    temporary = Path(os.environ['RUNNER_TEMP'])
    try:
        rc.write_bytes(original + b'\nbuild --nobuild\n')
        subprocess.run([
            sys.executable, 'build-system/Make/Make.py',
            '--cacheDir', str(temporary / 'telegram-bazel-cache'),
            'build', '--continueOnError',
            '--configurationPath', str(temporary / 'native-configuration.json'),
            '--codesigningInformationPath', str(temporary / 'native-signing'),
            '--buildNumber', str(1000 + int(os.environ['GITHUB_RUN_NUMBER'])),
            '--configuration', 'release_arm64',
        ], cwd=root, check=True)
    finally:
        rc.write_bytes(original)
    print('PASS: full Telegram arm64 Bazel dependency analysis (no compilation actions)')


if __name__ == '__main__':
    validate(sys.argv[1])
