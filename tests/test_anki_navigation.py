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
from anki_tab import AnkiTab, DISCONNECTED_TEXT
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

    def render(self):
        self.trace.append(('render', self.view))


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
        self.tab.reload_client = MagicMock()

    def test_offline_click_opens_anki_page_without_spawning(self):
        before = copy.deepcopy(self.app.conf)
        def fail():
            raise ConnectionRefusedError()
        with patch.object(self.tab.client, 'enter', side_effect=fail), patch('anki_tab.subprocess.Popen') as spawn:
            self.tab.enter()
            item = self.tab.inbox.get(timeout=2)
            self.tab.inbox.put(item)
            self.tab.tick()
        self.assertEqual(self.app.view, 'anki')
        self.assertEqual(self.app.conf, before)
        self.assertEqual(self.app.trace, [('view', 'anki')])
        self.assertIsNone(self.tab.session)
        self.assertIsNone(self.tab.state)
        self.assertFalse(self.tab.connecting)
        self.assertIn('AnkiConnect', self.tab.connection_hint)
        spawn.assert_not_called()
        self.assertFalse(self.tab.busy)

    def test_tab_switch_commits_timetable_before_offline_page(self):
        app = Navigation()
        app.view, app.compact, app.conf = 'tt', False, {'view': 'tt'}
        app.anki = MagicMock()
        for name in ('tt_commit', 'close_picker', 'hide_tip', 'draw_header', 'render', 'save_conf'):
            setattr(app, name, MagicMock())
        app.anki.enter.side_effect = lambda: app.set_view('anki', _anki_select=True)
        app.set_view('anki')
        app.anki.enter.assert_called_once()
        app.tt_commit.assert_called_once()
        self.assertEqual(app.view, 'anki')
        self.assertEqual(app.conf, {'view': 'anki'})

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
        self.app.view = 'anki'
        self.tab.host = MagicMock()
        self.tab.host.poll.return_value = None
        self.tab.send_media = lambda: self.app.trace.append(('media', self.tab.media))
        self.tab.display = lambda: self.app.trace.append(('card', self.tab.state))
        self.tab.entered({'session': 'new-session', 'media': 'new-media', 'review': state()})
        self.assertEqual(self.app.trace[0], ('media', 'new-media'))
        self.assertEqual(self.app.trace[1], ('render', 'anki'))

    def test_disconnected_message_is_visible_without_a_browser(self):
        self.app.w, self.app.h = lambda: 640, lambda: 420
        self.app.pad, self.app.head_h = 18, 66
        self.app.px, self.app.f = lambda v: round(v), lambda *args: 'font'
        self.tab.d.FG, self.tab.d.MUTED = 'white', 'gray'
        self.tab.canvas = MagicMock()
        self.tab.status()
        texts = [c.kwargs['text'] for c in self.tab.canvas.create_text.call_args_list]
        self.assertIn(DISCONNECTED_TEXT, texts)
        self.assertIsNone(self.tab.browser_canvas)
        self.assertIsNone(self.tab.host)

    def test_offline_tab_can_retry_without_leaving_page(self):
        self.app.view = 'anki'
        self.tab.run = MagicMock()
        self.tab.enter()
        self.tab.enter()
        self.assertEqual(self.tab.run.call_count, 2)
        self.assertEqual(self.app.trace, [])
        self.assertEqual(self.tab.reload_client.call_count, 2)

    def test_connection_loss_stays_on_anki_page_and_clears_card(self):
        self.app.view = 'anki'
        self.tab.session, self.tab.state, self.tab.seq = 'session', state(), 7
        self.tab.refresh_job = self.app.after(1000, lambda: None)
        self.tab.disconnected(ConnectionRefusedError())
        self.assertEqual(self.app.view, 'anki')
        self.assertEqual(self.app.trace, [])
        self.assertIsNone(self.tab.state)
        self.assertIsNone(self.tab.session)
        self.assertIsNone(self.tab.refresh_job)
        self.assertEqual(self.tab.seq, 8)

    def test_no_automatic_review_attempt_while_disconnected(self):
        self.app.view = 'anki'
        self.tab.run = MagicMock()
        self.tab.refresh()
        self.tab.run.assert_not_called()
        self.assertIsNone(self.tab.refresh_job)

    def test_offline_review_and_undo_do_not_call_the_api(self):
        self.app.view = 'anki'
        self.tab.ready = True
        self.tab.run = MagicMock()
        self.tab.flip()
        self.tab.rate(0)
        self.tab.audio()
        self.tab.undo()
        self.tab.run.assert_not_called()

    def test_retry_reloads_explicit_connection_configuration(self):
        self.tab.config_path.write_text(json.dumps({'endpoint': 'http://127.0.0.1:8766/api/v1', 'api_key': 'new-test-key'}))
        with patch('anki_tab.find_web_assets', return_value=Path('/fake/assets')):
            AnkiTab.reload_client(self.tab)
        self.assertEqual(self.tab.client.endpoint, 'http://127.0.0.1:8766/api/v1')
        self.assertEqual(self.tab.client.key, 'new-test-key')

    def test_connected_active_tab_does_not_start_a_second_review(self):
        self.app.view = 'anki'
        self.tab.session = 'session'
        self.tab.run = MagicMock()
        self.tab.enter()
        self.tab.run.assert_not_called()

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
