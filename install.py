#!/usr/bin/env python3
"""Install the bundled skill locally, without overwriting an existing skill."""
import argparse
import os
import shutil
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--skills-dir', type=Path, help='Override the local skills directory')
args = parser.parse_args()
codex_root = Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex')
root = args.skills_dir or codex_root / 'skills'
source = Path(__file__).resolve().parent / 'skills' / 'cat-photo-stickers'
target = root.expanduser().resolve() / source.name
if target.exists():
    parser.exit(2, f'Already installed: {target}\nMove the existing folder aside before updating.\n')
target.parent.mkdir(parents=True, exist_ok=True)
shutil.copytree(source, target, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.DS_Store'))
print(f'Installed: {target}')
print('Python dependency: install the installed skill requirements.txt in your Python environment.')
