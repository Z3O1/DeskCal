"""Package embedded-core source preview without running Windows or the app.

Requires Windows x64 Python 3.14/Tk, but NOT installed Anki or AnkiConnect.
The vendor tree includes the official Anki core and its Python dependencies.
A standalone Nuitka release also bundles Python and does not use this vendor tree.
"""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from prepare_anki_assets import source_name

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    'deskcal.py', 'anki_core.py', 'anki_sync.py', 'anki_credentials.py', 'anki_settings.py',
    'anki_render.py', 'anki_tab.py', 'DeskCal.bat', 'requirements-anki.txt',
    'README.md', 'README-ANKI.md', 'AGENTS.md', 'LICENSE', 'COPYING', 'LICENSING.md',
    'THIRD_PARTY_NOTICES.md', 'CHANGELOG.md', 'licenses/Anki-LICENSE.txt',
    'docs/icon.png', 'fonts/OFL-LICENSE.txt', 'fonts/NotoSansCJKsc-Regular.otf', 'fonts/NotoSansCJKsc-Bold.otf',
    'anki_webview/card.html', 'anki_webview/CardHost.cs',
    'tools/build.py', 'tools/build_anki_host.py', 'tools/package_anki_preview.py',
    'tools/prepare_anki_assets.py', 'tools/prepare_anki_vendor.py',
    'tools/make_icon.py', 'tools/requirements-build.txt', '.github/workflows/build-windows.yml',
)
HOST = ('CardHost.exe', 'Microsoft.Web.WebView2.Core.dll', 'WebView2Loader.dll', 'WEBVIEW2-LICENSE.txt')
PREFIX = 'DeskCal-Anki-embedded/'


def build(host, output):
    payload = {name: (ROOT/name).read_bytes() for name in SOURCE}
    payload.update({'anki_webview/'+name: (host/name).read_bytes() for name in HOST})
    if not payload['anki_webview/CardHost.exe'].startswith(b'MZ'):
        raise ValueError('Missing compiled WebView2 host')
    for directory, marker in (('anki_webview/assets', 'deskcal-assets.json'), ('anki_vendor', 'deskcal-vendor.json')):
        root = ROOT / directory
        if not (root / marker).is_file():
            raise ValueError('Run the matching prepare_anki_assets/vendor tool first: ' + directory)
        for path in sorted(root.rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                payload[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    upstream = ROOT / 'build/anki-upstream'
    for name in (source_name(), 'source-manifest.json'):
        payload['source/anki-upstream/' + name] = (upstream / name).read_bytes()
    hashes = {name: hashlib.sha256(content).hexdigest() for name, content in payload.items()}
    vendor = json.loads(payload['anki_vendor/deskcal-vendor.json'])
    manifest = {'kind': 'embedded-anki-source-preview-not-standalone-installer',
                'fork': 'https://github.com/Z3O1/DeskCal',
                'backend': 'bundled official Anki core; no external Anki or AnkiConnect',
                'sync': 'manual native AnkiWeb sync; account/deck controls in gear settings',
                'credentials': 'no passwords; optional user-bound DPAPI session token, never packaged',
                'python_required': vendor['python'], 'platform': vendor['platform'],
                'personal_data': 'excluded; independent collection is created only on normal use',
                'verification': 'package hashes only; no application/runtime/GUI tests executed',
                'startup_policy': 'enabled by default on the user-authorized first normal launch',
                'update_policy': 'fork releases only', 'files': hashes}
    payload['preview-manifest.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2)+'\n').encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        for name, content in payload.items():
            if name.startswith(('data/', '.git/')) or '..' in Path(name).parts:
                raise ValueError('Private/unsafe package path')
            archive.writestr(PREFIX+name, content)
    checksum = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix+'.sha256').write_text(checksum+'  '+output.name+'\n', encoding='utf-8')
    print(output)
    print(f'{len(payload)} files; {output.stat().st_size / 1024 / 1024:.1f} MiB; personal data excluded.')
    print('SHA256:', checksum)
    print('No application, Windows process, test, installation, or startup registry write was performed.')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', type=Path, default=ROOT/'build/anki-host')
    parser.add_argument('--output', type=Path, default=ROOT/'dist/DeskCal-Anki-embedded-source.zip')
    args = parser.parse_args()
    build(args.host.resolve(), args.output.resolve())
