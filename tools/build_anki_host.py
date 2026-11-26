"""Compile the tiny WebView2 child host (Windows, or WSL with Windows .NET).

python tools/build_anki_host.py --sdk PATH_TO_EXTRACTED_SDK
The directory must contain the x64 loader, Core DLL, and WebView2 license.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
FILES = ('Microsoft.Web.WebView2.Core.dll', 'WebView2Loader.dll', 'WEBVIEW2-LICENSE.txt')


def windows(path):
    if os.name == 'nt':
        return str(path)
    return subprocess.check_output(['wslpath', '-w', str(path)], text=True).strip()


def build(sdk):
    output = ROOT / 'build/anki-host'
    output.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        source = sdk / name
        if not source.is_file():
            raise FileNotFoundError(source)
        shutil.copy2(source, output / name)
    compiler = (Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
                if os.name == 'nt' else Path('/mnt/c/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe'))
    subprocess.run([str(compiler), '/nologo', '/platform:x64', '/target:exe',
                    '/out:' + windows(output / 'CardHost.exe'),
                    '/reference:' + windows(output / FILES[0]),
                    '/reference:System.Drawing.dll', '/reference:System.Windows.Forms.dll',
                    windows(ROOT / 'anki_webview/CardHost.cs')], check=True)
    print(output / 'CardHost.exe')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', required=True, type=Path)
    args = parser.parse_args()
    build(args.sdk.resolve())
