"""Safe test runner: no current-desktop GUI tests, no Windows processes.

python tools/test_anki_headless.py [--ankiconnect /path/to/FooSoft/anki-connect]
Use an environment with Anki/aqt 26.9.2 for the optional native HTTP/HTML check.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main(ankiconnect=None, dark_card=None):
    if sys.platform != 'linux':
        raise SystemExit('Run this suite in Linux, never on the current Windows desktop.')
    import resource
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    cache = Path.home() / '.cache/pi/deskcal-anki'
    cache.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software',
               RAYON_NUM_THREADS='2', TMPDIR=str(cache))
    env.pop('DISPLAY', None)
    env.pop('WAYLAND_DISPLAY', None)
    for script in ('test_anki_api.py', 'test_anki_navigation.py', 'test_anki_build.py', 'test_anki_update.py'):
        subprocess.run([sys.executable, str(ROOT/'tests'/script)], cwd=ROOT, env=env, check=True, timeout=30)
    if ankiconnect:
        command = [sys.executable, str(ROOT/'tests/anki_connect_headless.py'),
                   '--ankiconnect', str(ankiconnect.resolve())]
        if dark_card:
            command += ['--dark-card', str(dark_card.resolve())]
        subprocess.run(command, cwd=ROOT, env=env, check=True, timeout=60)
    else:
        print('Native Anki/AnkiConnect/HTML check NOT RUN; provide --ankiconnect with an upstream checkout.')
    print('Headless checks passed. Windows-only GUI/font acceptance is not covered.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ankiconnect', type=Path)
    parser.add_argument('--dark-card', type=Path)
    args = parser.parse_args()
    main(args.ankiconnect, args.dark_card)
