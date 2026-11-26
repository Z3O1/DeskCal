"""Package pipeline checks with fake compiler output; no Windows compiler is run."""
import importlib.util
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('deskcal_build', ROOT/'tools/build.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class Tests(unittest.TestCase):
    def test_host_survives_build_cleanup_and_is_bundled_with_html(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            work, dist = root/'build', root/'dist'
            host = work/'anki-host'
            host.mkdir(parents=True)
            payload = {'CardHost.exe': b'test-host', 'Microsoft.Web.WebView2.Core.dll': b'test-core',
                       'WebView2Loader.dll': b'test-loader', 'WEBVIEW2-LICENSE.txt': b'test-license'}
            for name, blob in payload.items():
                (host/name).write_bytes(blob)
            (root/'deskcal.py').write_text('__version__ = "1.3.2"\n')
            (root/'README-ANKI.md').write_text('Anki fork')
            python = root/'venv/Scripts/python.exe'
            python.parent.mkdir(parents=True)
            python.write_bytes(b'fake-python')
            runtime = root/'python-runtime'
            runtime.mkdir()
            (runtime/'LICENSE.txt').write_text('Python')
            calls = []
            def fake_run(*args):
                calls.append(args)
                if args[1:3] == ('-m', 'nuitka'):
                    app = work/'dist/deskcal.dist'
                    (app/'anki_webview').mkdir(parents=True)
                    (app/'DeskCal.exe').write_bytes(b'fake-nuitka-output')
                    (app/'anki_webview/card.html').write_text('<html>card</html>')
            with patch.multiple(build, ROOT=str(root), BUILD=str(work), DIST=str(dist), VPY=str(python)), \
                 patch.object(build, 'run', side_effect=fake_run), \
                 patch.object(build.subprocess, 'run', return_value=SimpleNamespace(stdout=str(runtime))), \
                 patch.object(sys, 'argv', ['build.py']):
                build.main()
            packages = list(dist.glob('*.zip'))
            self.assertEqual(len(packages), 1)
            with ZipFile(packages[0]) as package:
                self.assertEqual(package.read('DeskCal/anki_webview/card.html'), b'<html>card</html>')
                for name, blob in payload.items():
                    self.assertEqual(package.read('DeskCal/anki_webview/'+name), blob)
                self.assertIn('DeskCal/README-ANKI.md', package.namelist())
                self.assertFalse(any('/data/' in name or 'meta.json' in name for name in package.namelist()))
            command = next(args for args in calls if args[1:3] == ('-m', 'nuitka'))
            self.assertTrue(any('=anki_webview/card.html' in item for item in command))


if __name__ == '__main__':
    unittest.main()
