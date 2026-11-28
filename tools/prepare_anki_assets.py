"""Bundle matching official Anki reviewer assets and corresponding source.

Downloads the aqt *wheel only*, without installing/importing aqt or Qt. Nothing
is launched on Windows and no collection is opened. Uses pip's normal HTTPS
package verification. Run again when changing requirements-anki.txt.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory
from urllib.request import Request, urlopen
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]


def version():
    text = (ROOT / 'requirements-anki.txt').read_text(encoding='utf-8')
    return re.search(r'^anki==([\d.]+)$', text, re.M).group(1)


def upstream_tag():
    year, month, patch = map(int, version().split('.'))
    return f'{year}.{month:02d}.{patch}'


def source_name():
    return f'anki-{upstream_tag()}-source.tar.gz'


def prepare(output, source_output, wheel=None):
    build = ROOT / 'build'
    build.mkdir(exist_ok=True)
    source_output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='anki-assets-', dir=build) as temporary:
        temp = Path(temporary)
        if wheel is None:
            subprocess.run([sys.executable, '-m', 'pip', 'download', '--disable-pip-version-check',
                            '--no-deps', '--only-binary=:all:', '--dest', str(temp),
                            'aqt==' + version()], check=True)
            wheel = next(temp.glob('aqt-*.whl'))
        with ZipFile(wheel) as archive:
            metadata = next(name for name in archive.namelist() if name.endswith('.dist-info/METADATA'))
            wheel_version = re.search(r'^Version: (.+)$', archive.read(metadata).decode(), re.M).group(1)
            if tuple(map(int, wheel_version.split('.'))) != tuple(map(int, version().split('.'))):
                raise ValueError('Reviewer assets must match the pinned Anki core version')
            staged = temp / 'assets'
            staged.mkdir()
            for info in archive.infolist():
                prefix = '_aqt/data/web/'
                if info.is_dir() or not info.filename.startswith(prefix):
                    continue
                relative = PurePosixPath(info.filename[len(prefix):])
                if relative.is_absolute() or '..' in relative.parts or '\\' in str(relative):
                    raise ValueError('Unsafe wheel path')
                target = staged.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(info))
            if not (staged / 'js/reviewer.js').is_file():
                raise ValueError('Official reviewer assets not present in this wheel')
        # Preserve a complete upstream source archive alongside the redistributable
        # assets, not merely a link to a potentially disappearing release page.
        source = source_output / source_name()
        url = 'https://codeload.github.com/ankitects/anki/tar.gz/refs/tags/' + upstream_tag()
        if not source.is_file():
            request = Request(url, headers={'User-Agent': 'DeskCal-source-bundler'})
            partial = source.with_suffix('.part')
            try:
                with urlopen(request, timeout=120) as response, partial.open('wb') as destination:
                    shutil.copyfileobj(response, destination)
                with tarfile.open(partial, 'r:gz') as archive:
                    if not any(member.name.endswith('/pylib/anki/collection.py') for member in archive):
                        raise ValueError('Unexpected Anki source archive')
                partial.replace(source)
            finally:
                partial.unlink(missing_ok=True)
        manifest = {'anki_version': version(), 'aqt_version': wheel_version,
                    'source_url': url, 'source_archive': source.name,
                    'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                    'wheel_sha256': hashlib.sha256(Path(wheel).read_bytes()).hexdigest()}
        (staged / 'deskcal-assets.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            shutil.rmtree(output)
        shutil.copytree(staged, output)
        (source_output / 'source-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print('Bundled official reviewer assets:', output)
    print('Corresponding upstream source:', source)
    print('No Qt/Anki GUI, collection, or test was started.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'anki_webview/assets')
    parser.add_argument('--source-output', type=Path, default=ROOT / 'build/anki-upstream')
    parser.add_argument('--wheel', type=Path, help='optional previously downloaded matching aqt wheel')
    args = parser.parse_args()
    prepare(args.output.resolve(), args.source_output.resolve(), args.wheel.resolve() if args.wheel else None)
