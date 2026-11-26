"""Create an explicit-allowlist source preview, without running Windows or Nuitka.

The preview requires installed Windows Python/Tk. It is NOT a tested standalone
installer. Personal settings, collections, caches and API keys are never bundled.
"""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    'deskcal.py', 'anki_api.py', 'anki_effects.py', 'anki_tab.py', 'DeskCal.bat',
    'README.md', 'README-ANKI.md', 'AGENTS.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'CHANGELOG.md',
    'docs/icon.png', 'fonts/OFL-LICENSE.txt', 'fonts/NotoSansCJKsc-Regular.otf', 'fonts/NotoSansCJKsc-Bold.otf',
    'anki_webview/card.html', 'anki_webview/CardHost.cs',
    'tools/build.py', 'tools/build_anki_host.py', 'tools/test_anki_headless.py', 'tools/package_anki_preview.py',
    'tools/make_icon.py', 'tools/requirements-build.txt',
    'tests/test_anki_api.py', 'tests/test_anki_navigation.py', 'tests/test_anki_build.py', 'tests/test_anki_update.py',
    'tests/anki_connect_headless.py', 'tests/fixtures/dark_card/__init__.py',
    'tests/fixtures/dark_card/dark.css', 'tests/fixtures/dark_card/manifest.json',
)
HOST = ('CardHost.exe', 'Microsoft.Web.WebView2.Core.dll', 'WebView2Loader.dll', 'WEBVIEW2-LICENSE.txt')
PREFIX = 'DeskCal-Anki-preview/'


def build(host, output):
    payload = {name: (ROOT/name).read_bytes() for name in SOURCE}
    payload.update({'anki_webview/'+name: (host/name).read_bytes() for name in HOST})
    assert payload['anki_webview/CardHost.exe'].startswith(b'MZ')
    private = ROOT/'data/anki-connect.json'
    if private.is_file():
        secret = json.loads(private.read_text(encoding='utf-8')).get('api_key')
        if isinstance(secret, str) and len(secret) > 12:
            assert not any(secret.encode() in content for content in payload.values()), 'Private key must not be distributed'
    hashes = {name: hashlib.sha256(content).hexdigest() for name, content in payload.items()}
    manifest = {'kind': 'source-preview-not-installer', 'fork': 'https://github.com/Z3O1/DeskCal',
                'baseline': 'e6c62fcfae19b317b66a48ba8bb89cca2da216b9',
                'windows_gui_acceptance': 'pending; no current-desktop tests permitted',
                'startup_policy': 'enabled by default on the user-authorized first normal launch',
                'update_policy': 'fork releases only', 'files': hashes}
    payload['preview-manifest.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2)+'\n').encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        for name, content in payload.items():
            assert not name.startswith(('data/', '.git/')) and '..' not in Path(name).parts
            archive.writestr(PREFIX+name, content)
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        assert all(archive.read(PREFIX+name) == content for name, content in payload.items())
    checksum = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix+'.sha256').write_text(checksum+'  '+output.name+'\n', encoding='utf-8')
    print(output)
    print(f'{len(payload)} files verified; {output.stat().st_size / 1024 / 1024:.1f} MiB; no personal configuration bundled.')
    print('SHA256:', checksum)
    print('No Windows processes, desktop tests, installation or startup registry writes were performed.')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', type=Path, default=ROOT/'build/anki-host')
    parser.add_argument('--output', type=Path, default=ROOT/'dist/DeskCal-Anki-preview-source.zip')
    args = parser.parse_args()
    build(args.host.resolve(), args.output.resolve())
