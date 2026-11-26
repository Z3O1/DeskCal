"""Fork update/startup policy tests, without Win32 imports or registry writes."""
import ast
import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
TREE = ast.parse((ROOT/'deskcal.py').read_text(encoding='utf-8'))
CONSTANTS = {}
for node in TREE.body:
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        if node.targets[0].id in ('RELEASES_API', 'RELEASES_PAGE', 'RELEASES_DL'):
            CONSTANTS[node.targets[0].id] = ast.literal_eval(node.value)
CLASS = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == 'DeskCal')


class Tests(unittest.TestCase):
    def test_update_urls_all_belong_to_fork(self):
        self.assertEqual(len(CONSTANTS), 3)
        for value in CONSTANTS.values():
            self.assertIn('/Z3O1/DeskCal/', value)
            self.assertNotIn('HANSEIDON', value)

    def test_upstream_cached_installer_is_removed_but_preferences_stay(self):
        init = next(n for n in CLASS.body if isinstance(n, ast.FunctionDef) and n.name == '__init__')
        branch = next(n for n in init.body if isinstance(n, ast.If) and 'update_source' in ast.unparse(n.test))
        conf = {'theme': 'dark', 'update_check': False, 'update_latest': '9.9.9',
                'update_setup_url': 'https://github.com/HANSEIDON/DeskCal/releases/download/old.exe'}
        app = SimpleNamespace(conf=copy.deepcopy(conf))
        exec(compile(ast.Module(body=[copy.deepcopy(branch)], type_ignores=[]), '<update-cache>', 'exec'),
             {**CONSTANTS, 'self': app})
        self.assertEqual(app.conf, {'theme': 'dark', 'update_check': False, 'update_source': CONSTANTS['RELEASES_API']})

    def test_default_autostart_remains_enabled_without_touching_registry(self):
        method = next(n for n in CLASS.body if isinstance(n, ast.FunctionDef) and n.name == 'init_autostart')
        namespace = {}
        exec(compile(ast.Module(body=[copy.deepcopy(method)], type_ignores=[]), '<autostart>', 'exec'), namespace)
        setter = MagicMock()
        namespace['init_autostart'](SimpleNamespace(conf={}, set_autostart_pref=setter))
        setter.assert_called_once_with(True)
        setter.reset_mock()
        namespace['init_autostart'](SimpleNamespace(conf={'autostart': False}, set_autostart_pref=setter))
        setter.assert_not_called()

    def test_release_parser_rejects_original_repository_installer(self):
        method = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == 'fetch_release')
        response = {'tag_name': 'v9.9.9', 'assets': [
            {'name': 'DeskCal-9.9.9-Setup.exe', 'browser_download_url': 'https://github.com/HANSEIDON/DeskCal/releases/download/v9.9.9/DeskCal-9.9.9-Setup.exe'},
            {'name': 'DeskCal-9.9.9-Setup.exe.sha256', 'browser_download_url': CONSTANTS['RELEASES_DL']+'v9.9.9/hash'}]}
        reply = MagicMock()
        reply.__enter__.return_value = reply
        reply.read.return_value = json.dumps(response).encode()
        # Only the first-party Request class is real; no network request is made.
        request = SimpleNamespace(Request=urllib.request.Request, urlopen=MagicMock(return_value=reply))
        namespace = {**CONSTANTS, 'json': json, 'urllib': SimpleNamespace(request=request)}
        exec(compile(ast.Module(body=[copy.deepcopy(method)], type_ignores=[]), '<release>', 'exec'), namespace)
        value = namespace['fetch_release']()
        self.assertEqual(value['setup_url'], '')
        self.assertTrue(value['sha_url'].startswith(CONSTANTS['RELEASES_DL']))
        self.assertEqual(request.urlopen.call_args.args[0].full_url, CONSTANTS['RELEASES_API'])


if __name__ == '__main__':
    unittest.main()
