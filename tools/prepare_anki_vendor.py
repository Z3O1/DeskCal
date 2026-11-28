"""Bundle Windows Anki core wheels for a source preview, without executing them.

Standalone Nuitka releases bundle their own matching Python/core instead.
The default source preview targets Windows x64 Python 3.14. Different Python
versions may install requirements-anki.txt or regenerate this vendor directory.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]


def prepare(output, python_version='3.14', platform='win_amd64'):
    build = ROOT / 'build'
    build.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix='anki-wheels-', dir=build) as directory:
        temporary = Path(directory)
        wheels = temporary / 'wheels'
        wheels.mkdir()
        abi = 'cp' + python_version.replace('.', '')
        subprocess.run([sys.executable, '-m', 'pip', 'download', '--disable-pip-version-check',
                        '--only-binary=:all:', '--platform', platform, '--python-version', python_version,
                        '--implementation', 'cp', '--abi', abi, '--abi', 'abi3', '--abi', 'none',
                        '--dest', str(wheels), '-r', str(ROOT / 'requirements-anki.txt')], check=True)
        staged = temporary / 'vendor'
        staged.mkdir()
        hashes = {}
        for wheel in sorted(wheels.glob('*.whl')):
            hashes[wheel.name] = hashlib.sha256(wheel.read_bytes()).hexdigest()
            with ZipFile(wheel) as archive:
                for info in archive.infolist():
                    if info.is_dir():
                        continue
                    path = PurePosixPath(info.filename)
                    if path.is_absolute() or '..' in path.parts or '\\' in str(path):
                        raise ValueError('Unsafe wheel path')
                    parts = path.parts
                    if parts[0].endswith('.data'):
                        if len(parts) < 3 or parts[1] not in ('purelib', 'platlib'):
                            continue
                        parts = parts[2:]
                    destination = staged.joinpath(*parts)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(archive.read(info))
        manifest = {'python': python_version, 'platform': platform, 'wheels': hashes,
                    'note': 'Official core and dependencies only; no personal collection or Anki GUI.'}
        (staged / 'deskcal-vendor.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            shutil.rmtree(output)
        shutil.copytree(staged, output)
    print('Bundled core/dependencies:', output)
    print(f'Target: Windows {platform}, Python {python_version}; no runtime or test was executed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'anki_vendor')
    parser.add_argument('--python-version', default='3.14')
    parser.add_argument('--platform', choices=('win_amd64', 'win_arm64'), default='win_amd64')
    args = parser.parse_args()
    prepare(args.output.resolve(), args.python_version, args.platform)
