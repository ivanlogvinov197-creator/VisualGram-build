"""Parse every changed or newly added Swift file in the official checkout."""
from collections import defaultdict
from pathlib import Path
import re
import subprocess
import sys


def validate_launch_presentation(root):
    path = Path(root) / 'submodules/TelegramUI/Sources/TelegramRootController.swift'
    source = path.read_text(encoding='utf-8')
    if re.search(r'\bself\.present\([^;{}]*?\banimated\s*:', source, re.DOTALL):
        raise RuntimeError('TelegramRootController inherits a trapping UIKit present(_:animated:) override')
    print('PASS: root controller avoids the trapping UIKit presentation API')


def validate(root):
    root = Path(root).resolve()
    validate_launch_presentation(root)
    changed = subprocess.check_output(['git', '-C', str(root), 'diff', '--name-only', 'HEAD', '--', '*.swift'], text=True).splitlines()
    added = subprocess.check_output(['git', '-C', str(root), 'ls-files', '--others', '--exclude-standard', '--', '*.swift'], text=True).splitlines()
    files = sorted(set(changed + added))
    if not files:
        raise RuntimeError('No patched Swift files found')
    by_name = defaultdict(list)
    for relative in files:
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise RuntimeError('Invalid patched file: ' + relative)
        by_name[path.name].append(path)
    # The parser rejects duplicate basenames in one invocation, even across modules.
    for index in range(max(map(len, by_name.values()))):
        group = [str(paths[index]) for paths in by_name.values() if len(paths) > index]
        subprocess.run(['xcrun', 'swiftc', '-frontend', '-parse', *group], check=True)
    print(f'PASS: Swift syntax parsed for all {len(files)} changed/added files')


if __name__ == '__main__':
    validate(sys.argv[1])
