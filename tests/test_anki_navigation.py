"""No Tk root, native window, desktop screenshot or Windows process is created."""
import ast
import copy
import json
from pathlib import Path
import queue
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from anki_tab import AnkiTab
from test_anki_api import state


def navigation_class():
    """Exercise original navigation methods directly, without importing Win32/Tk."""
    tree = ast.parse((ROOT / 'deskcal.py').read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'DeskCal')
    names = {'set_view', 'menu', 'close_mode', 'undo'}
    nodes = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in names]
    namespace = {'json': json}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(ROOT/'deskcal.py'), 'exec'), namespace)
    return type('OriginalNavigation', (), {name: namespace[name] for name in names})


Navigation = navigation_class()


class App:
    def __init__(self):
        self.view, self.compact, self.panel_mode, self.theme = 'cal', False, 'day', 'dark'
        self.conf, self.jobs, self.trace = {'view': 'cal'}, {}, []

    def after(self, milliseconds, callback):
        name = 'job-' + str(len(self.jobs))
        self.jobs[name] = (milliseconds, callback)
        return name

    def after_cancel(self, name):
        self.jobs.pop(name, None)

    def set_view(self, view, **kwargs):
        self.trace.append(('view', view))
        self.view = view


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = App()
        self.logs = []
        style = SimpleNamespace(APP_DIR=self.temp.name, HERE=str(ROOT), log=self.logs.append)
        with patch('anki_tab.find_web_assets', return_value=Path('/fake/anki-assets')):
            self.tab = AnkiTab(self.app, style)
        self.tab.exe = Path('/fake/host.exe')
        self.tab.assets = Path('/fake/assets')

    def test_offline_click_does_not_switch_or_spawn(self):
        before = copy.deepcopy(self.app.conf)
        def fail():
            raise ConnectionRefusedError()
        with patch.object(self.tab.client, 'enter', side_effect=fail), patch('anki_tab.subprocess.Popen') as spawn:
            self.tab.enter()
            item = self.tab.inbox.get(timeout=2)
            self.tab.inbox.put(item)
            self.tab.tick()
        self.assertEqual(self.app.view, 'cal')
        self.assertEqual(self.app.conf, before)
        self.assertEqual(self.app.trace, [])
        spawn.assert_not_called()
        self.assertFalse(self.tab.busy)

    def test_original_gate_does_not_commit_calendar_when_offline(self):
        app = Navigation()
        app.view, app.compact, app.conf = 'tt', False, {'view': 'tt'}
        app.anki = MagicMock()
        app.tt_commit = MagicMock()
        app.set_view('anki')
        app.anki.enter.assert_called_once()
        app.tt_commit.assert_not_called()
        self.assertEqual(app.view, 'tt')
        self.assertEqual(app.conf, {'view': 'tt'})

    def test_original_tabs_continue_to_commit_and_render_normally(self):
        app = Navigation()
        app.view, app.compact, app.conf = 'cal', False, {'view': 'cal'}
        app.anki = SimpleNamespace(generation=0)
        for name in ('tt_commit', 'close_picker', 'hide_tip', 'draw_header', 'render', 'save_conf'):
            setattr(app, name, MagicMock())
        app.set_view('tt')
        self.assertEqual(app.view, 'tt')
        self.assertEqual(app.conf['view'], 'tt')
        self.assertEqual(app.anki.generation, 1)
        app.render.assert_called_once()
        app.set_view('cal')
        self.assertEqual(app.view, 'cal')
        self.assertEqual(app.anki.generation, 2)

    def test_original_settings_close_returns_to_anki(self):
        app = Navigation()
        app.anki = MagicMock()
        app.anki.active.return_value = True
        app.panel_mode = 'settings'
        app.render, app.render_panel = MagicMock(), MagicMock()
        app.close_mode()
        self.assertEqual(app.panel_mode, 'day')
        app.render.assert_called_once()
        app.render_panel.assert_not_called()

    def test_anki_undo_never_changes_calendar_undo_stack(self):
        app = Navigation()
        app.anki = MagicMock()
        app.anki.active.return_value = True
        app.undo_stack = ['calendar-state']
        self.assertEqual(app.undo(), 'break')
        app.anki.undo.assert_called_once()
        self.assertEqual(app.undo_stack, ['calendar-state'])

    def test_new_media_mapping_precedes_new_card_render(self):
        self.tab.host = MagicMock()
        self.tab.host.poll.return_value = None
        self.tab.send_media = lambda: self.app.trace.append(('media', self.tab.media))
        self.tab.display = lambda: self.app.trace.append(('card', self.tab.state))
        self.tab.entered({'session': 'new-session', 'media': 'new-media', 'review': state()})
        self.assertEqual(self.app.trace[0], ('media', 'new-media'))
        self.assertEqual(self.app.trace[1], ('view', 'anki'))

    def test_closed_old_host_cannot_close_new_host(self):
        self.app.view = 'anki'
        old, current = MagicMock(), MagicMock()
        self.tab.host = current
        self.tab.ready = True
        self.tab.place = MagicMock()
        self.tab.inbox.put(('host', old, b'closed'))
        self.tab.tick()
        self.assertIs(self.tab.host, current)
        self.assertTrue(self.tab.ready)
        current.stdin.close.assert_not_called()

    def test_dead_renderer_is_detached_for_retry(self):
        self.tab.host = host = MagicMock()
        self.tab.host_event(b'closed')
        host.stdin.close.assert_called_once()
        self.assertIsNone(self.tab.host)
        self.assertFalse(self.tab.ready)

    def test_malformed_web_messages_are_ignored(self):
        for value in (None, [], 'text', 17):
            self.tab.host_event(b'msg ' + json.dumps(value).encode())
        self.assertEqual(self.app.view, 'cal')

    def test_stale_card_message_cannot_rate(self):
        self.tab.seq = 4
        self.tab.rate = MagicMock()
        self.tab.host_event(b'msg {"seq":3,"action":"rate","index":2}')
        self.tab.rate.assert_not_called()

    def test_rapid_double_rating_is_serialized(self):
        self.app.view = 'anki'
        self.tab.ready = True
        self.tab.state = state()
        self.tab.state['side'] = 'answer'
        self.tab.session = 'session'
        # Keep the first request pending without making any native call.
        def run(function, callback):
            self.tab.busy = True
        self.tab.run = MagicMock(side_effect=run)
        self.tab.rate(0)
        self.tab.rate(0)
        self.tab.run.assert_called_once()


if __name__ == '__main__':
    unittest.main()
