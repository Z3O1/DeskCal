"""Repackage a successful Windows artifact and compile its per-user Inno Setup.

Never execute the application or installer. Runtime sources must match the input
binary's included sources exactly; packaging-only changes may be added. Original
build provenance is preserved, with separate installer/package provenance.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
from zipfile import ZIP_DEFLATED, ZipFile

from package_anki_preview import SOURCE

ROOT = Path(__file__).resolve().parents[1]
# These files affect runtime behavior or its external assets, not only packaging.
RUNTIME_SOURCES = (
    'deskcal.py', 'anki_core.py', 'anki_sync.py', 'anki_credentials.py', 'anki_settings.py',
    'anki_render.py', 'anki_tab.py', 'requirements-anki.txt',
    'anki_webview/card.html', 'anki_webview/CardHost.cs', 'docs/icon.png',
    'fonts/NotoSansCJKsc-Regular.otf', 'fonts/NotoSansCJKsc-Bold.otf',
)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as file:
        for chunk in iter(lambda: file.read(1048576), b''):
            result.update(chunk)
    return result.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def checksum(path):
    value = digest(path)
    path.with_name(path.name+'.sha256').write_text(value+'  '+path.name+'\n', encoding='utf-8')
    return value


def find_compiler(configured):
    if configured:
        path = Path(configured)
    else:
        path = Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) / 'Inno Setup 6/ISCC.exe'
    require(path.is_file(), 'Inno Setup compiler missing: '+str(path))
    return path


def prepare(package, run_id, source_commit, compiler=None):
    require(re.fullmatch(r'\d+', run_id), 'Invalid source run id')
    require(re.fullmatch(r'[0-9a-f]{40}', source_commit), 'Invalid source commit')
    text = (ROOT/'deskcal.py').read_text(encoding='utf-8')
    version = re.search(r'^__version__ = "([\d.]+)"', text, re.M).group(1)
    expected_name = f'DeskCal-{version}-windows-x64.zip'
    require(package.name == expected_name, 'Artifact version/name does not match the current source')
    expected = package.with_name(package.name+'.sha256').read_text(encoding='utf-8').split()[0]
    original_hash = digest(package)
    require(original_hash == expected, 'Input ZIP checksum mismatch')
    stage = ROOT/'build/setup'
    with ZipFile(package) as archive:
        require(sum(item.file_size for item in archive.infolist()) < 2*1024**3, 'Unexpected artifact size')
        names = set(archive.namelist())
        info = json.loads(archive.read('DeskCal/build-info.json'))
        require(info['version'] == version and info['commit'] == source_commit and info['run_id'] == run_id,
                'Artifact build provenance differs from the selected successful run')
        require(info['repository'] == 'https://github.com/Z3O1/DeskCal', 'Unexpected artifact repository')
        for name in RUNTIME_SOURCES:
            bundled, current = archive.read('DeskCal/source/deskcal/'+name), (ROOT/name).read_bytes()
            if Path(name).suffix in ('.py', '.cs', '.html', '.txt'):
                # Git on Windows checks text out as CRLF; this is not a source change.
                bundled, current = bundled.replace(b'\r\n', b'\n'), current.replace(b'\r\n', b'\n')
            require(bundled == current,
                    'Runtime source changed; perform a fresh Windows compile before releasing: '+name)
        require(any(name.endswith('anki/_rsbridge.pyd') for name in names), 'Missing native Anki backend')
        stage.mkdir(parents=True, exist_ok=False)
        for item in archive.infolist():
            relative = PurePosixPath(item.filename)
            require(not relative.is_absolute() and '..' not in relative.parts
                    and '\\' not in item.filename and ':' not in item.filename
                    and relative.parts[0] == 'DeskCal', 'Unsafe archive path')
            require(not item.filename.startswith('DeskCal/data/')
                    and not item.filename.endswith(('collection.anki2', 'ankiweb-auth.bin')),
                    'Personal data must never be packaged')
            destination = stage.joinpath(*relative.parts)
            if item.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item) as source, destination.open('wb') as target:
                    shutil.copyfileobj(source, target)
    app = stage/'DeskCal'
    # Refresh packaging docs/recipes, never compiled runtime code. Preserve all
    # original Anki/Python dependency notices and the exact upstream source archive.
    for name in SOURCE:
        destination = app/'source/deskcal'/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/name, destination)
    for name in ('README.md', 'README-ANKI.md', 'CHANGELOG.md', 'LICENSE', 'COPYING',
                 'LICENSING.md', 'THIRD_PARTY_NOTICES.md'):
        shutil.copy2(ROOT/name, app/name)
    for path in (ROOT/'licenses').glob('*'):
        if path.is_file():
            shutil.copy2(path, app/'licenses'/path.name)
    if compiler:
        compiler_license = compiler.parent/'license.txt'
        require(compiler_license.is_file(), 'The Inno Setup license must accompany the installer')
        shutil.copy2(compiler_license, app/'licenses/InnoSetup-LICENSE.txt')
        shutil.copy2(compiler_license, app/'source/deskcal/licenses/InnoSetup-LICENSE.txt')
    packaging_commit = os.environ.get('GITHUB_SHA')
    provenance = {'version': version, 'runtime_commit': source_commit, 'runtime_run_id': run_id,
                  'input_zip_sha256': original_hash, 'packaging_commit': packaging_commit,
                  'packaging_run_id': os.environ.get('GITHUB_RUN_ID'),
                  'runtime_sources_verified': True, 'source_text_eol_normalized': True,
                  'verification': 'package/compiler checks only; installer/application/tests were not run'}
    write_json(app/'release-info.json', provenance)
    icon = stage/'DeskCal.ico'
    subprocess.run([sys.executable, str(ROOT/'tools/make_icon.py'), str(icon)], check=True, cwd=ROOT)
    # Build a release ZIP with the same compiled binaries plus current installer
    # sources/notices, so both distribution formats carry the complete recipe.
    output = ROOT/'dist'
    output.mkdir(exist_ok=True)
    release_zip = output/expected_name
    require(release_zip.resolve() != package.resolve(), 'Keep the input artifact separate from the release output')
    with ZipFile(release_zip, 'w', ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(app.rglob('*')):
            if path.is_file():
                archive.write(path, 'DeskCal/'+path.relative_to(app).as_posix())
    zip_hash = checksum(release_zip)
    result = {'version': version, 'tag': 'v'+version, 'zip': str(release_zip), 'zip_sha256': zip_hash,
              'bundle': str(app), 'icon': str(icon), **provenance}
    write_json(output/'setup-build-info.json', result)
    print('Runtime source/provenance and ZIP integrity verified; no runtime code executed.')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zip', type=Path, required=True)
    parser.add_argument('--source-run-id', required=True)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--iscc', help='Inno Setup compiler; otherwise use the standard Windows runner path')
    parser.add_argument('--prepare-only', action='store_true', help='assemble files only; do not invoke any Windows program')
    args = parser.parse_args()
    if not args.prepare_only and sys.platform != 'win32':
        raise SystemExit('Compile Setup only on an authorized Windows runner; use --prepare-only for file assembly.')
    compiler = None if args.prepare_only else find_compiler(args.iscc)
    info = prepare(args.zip.resolve(), args.source_run_id, args.source_commit, compiler)
    if compiler:
        command = [str(compiler), '/Qp', '/DMyAppVersion='+info['version'],
                   '/DBundleDir='+info['bundle'], '/DRepoRoot='+str(ROOT),
                   '/DInstallerIcon='+info['icon'], '/DInstallerOutput='+str(ROOT/'dist'),
                   str(ROOT/'tools/DeskCal.iss')]
        print('Compiling Inno Setup (not executing the installer).', flush=True)
        subprocess.run(command, check=True, cwd=ROOT)
        setup = ROOT/'dist'/('DeskCal-'+info['version']+'-Setup.exe')
        with setup.open('rb') as file:
            require(file.read(2) == b'MZ', 'Installer is not a Windows executable')
        info.update(setup=str(setup), setup_sha256=checksum(setup))
        write_json(ROOT/'dist/setup-build-info.json', info)
        print('Setup:', setup)
    print('No installer, application, test, login or sync was executed.')
    print(json.dumps(info, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
