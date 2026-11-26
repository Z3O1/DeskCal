"""Original Windows DeskCal + live WebView2, with a disposable AnkiConnect stub.

No personal calendar, collection, Anki window, startup registry entry or sync is used.
"""
import copy
from ctypes import byref
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Thread
from time import monotonic, sleep

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def until(app, predicate, reason, seconds=15):
    end = monotonic() + seconds
    while monotonic() < end:
        app.update()
        if predicate():
            return
        sleep(.02)
    raise AssertionError(reason)


def test(temp, screenshots):
    sys.argv.append('--float')
    os.environ['DESKCAL_DIR'] = str(temp)
    os.environ['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'] = '--no-proxy-server'
    import deskcal as d
    d.DPI_MODE = d.set_dpi_awareness()
    # Avoid putting the user's wallpaper in diagnostic screenshots.
    def glass(x, y, w, h, *_args):
        row = b''.join(bytes((32 + 57*i//w, 32 + 28*i//w, 62 - 32*i//w, 255)) for i in range(w))
        return row * h
    d.make_glass = glass
    d.DeskCal.prepare_desk = lambda app: None
    d.save_json(d.CONF_FILE, {'x': 180, 'y': 180, 'glass': 'clear', 'size': 0, 'lang': 'en'})
    media = temp / 'media'
    media.mkdir()
    from PIL import Image
    from windows_capture import capture
    Image.new('RGB', (10, 10), '#19c472').save(media / 'badge.png')
    question = ('<style>.card{background:white;color:white;font-size:25px}</style>'
                '<h1>reflect</h1><p>[rɪˈflekt]</p><h2>Waiting for media</h2>'
                '<img src="badge.png" onload="document.querySelector(\'h2\').textContent=\'Media and JS ready\';pycmd(\'play\')">')
    back = question + '<details open><summary>Meaning</summary>v. 反射；反思</details>'
    review = {'active': True, 'card': {'id': '42', 'templateIndex': 0, 'deck': {'name': 'Words'}, 'flags': 0},
              'side': 'question', 'stateToken': 'token-42',
              'rendered': {'questionHtml': question, 'answerHtml': back, 'css': ''},
              'answers': [{'rating': name, 'label': '\u2068' + interval + '\u2069'}
                          for name, interval in zip(('again', 'hard', 'good', 'easy'), ('<10m', '4d', '2.6mo', '6.3mo'))]}
    stats = dict(audio=0, answers=0, requests=0)

    class Server(BaseHTTPRequestHandler):
        def do_POST(self):
            assert self.headers.get('Authorization') == 'Bearer test-secret'
            assert not self.headers.get('Origin')
            message = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            method, params = message['method'], message['params']
            stats['requests'] += 1
            if method == 'collection.get':
                result = {'session': 'session-1'}
            else:
                assert params.get('session') == 'session-1'
                if method == 'media.getDirectory':
                    result = {'path': str(media)}
                elif method == 'reviewer.get':
                    result = copy.deepcopy(review)
                elif method == 'application.navigate':
                    result = {'changed': True}
                else:
                    assert params['stateToken'] == 'token-42'
                    if method == 'reviewer.showAnswer':
                        review['side'] = 'answer'
                    elif method == 'reviewer.playAudio':
                        stats['audio'] += 1
                    elif method == 'reviewer.answer':
                        assert review['side'] == 'answer' and review['active']
                        assert params['rating'] == 'good'
                        stats['answers'] += 1
                        review.update(active=False, side='none', card=None, stateToken=None, rendered=None, answers=[])
                    else:
                        raise AssertionError(method)
                    result = {'changed': True}
            data = json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': result}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_):
            pass

    settings_path = temp / 'anki-connect.json'
    settings = {'endpoint': 'http://127.0.0.1:1/api/v1', 'api_key': 'test-secret',
                'deck': 'Words', 'timeout': .25, 'addons_dir': str(temp/'isolated-addons')}
    settings_path.write_text(json.dumps(settings), encoding='utf-8')
    app = d.DeskCal()
    app.attributes('-topmost', True)
    def shot(name, glass_check=False):
        for _ in range(12):
            app.update()
            sleep(.025)
        rect = d.RECT()
        assert d.user32.GetWindowRect(app.base.winfo_id(), byref(rect))
        image = capture(app.base.winfo_id(), app.w(), app.h())
        if screenshots:
            screenshots.mkdir(parents=True, exist_ok=True)
            image.save(screenshots / name)
        if glass_check:
            for x in (app.pad + 24, app.w()-app.pad-24):
                y = app.h()-app.pad-app.px(110)
                actual = image.getpixel((x, y))
                expected = tuple(app.glass_img.get(x, y))
                assert max(abs(a-b) for a,b in zip(actual, expected)) < 12, (actual, expected)

    server = ThreadingHTTPServer(('0.0.0.0', 0), Server)
    Thread(target=server.serve_forever, daemon=True).start()
    host = None
    try:
        assert app.view == 'cal' and stats['requests'] == 0
        assert app.base.find_withtag('b_cal') and app.base.find_withtag('b_anki') and app.base.find_withtag('b_tt')
        assert app.base.bbox('b_cal')[2] < app.base.bbox('b_anki')[0] < app.base.bbox('b_tt')[0]
        size, selected, shown, conf = (app.w(), app.h()), app.selected, app.shown, dict(app.conf)
        shot('anki-tab-calendar.png')
        app.set_view('anki')
        until(app, lambda: not app.anki.busy, 'offline request did not finish')
        assert app.view == 'anki' and stats['requests'] == 0
        assert app.conf['view'] == 'anki'
        assert not app.anki.host and app.anki.canvas.find_withtag('anki-status')
        assert app.anki.canvas.find_withtag('anki-retry')
        settings['endpoint'] = f'http://127.0.0.1:{server.server_port}/api/v1'
        settings_path.write_text(json.dumps(settings), encoding='utf-8')
        app.set_view('anki')
        until(app, lambda: app.view == 'anki' and app.anki.ready, 'Anki page did not open')
        host = app.anki.host
        until(app, lambda: stats['audio'] >= 1 and not app.anki.busy, 'HTML JS / media / native message bridge did not run')
        assert size == (app.w(), app.h())
        assert app.base.itemcget(app._cal_win, 'state') == 'hidden'
        assert app.base.itemcget(app._panel_win, 'state') == 'hidden'
        assert app.anki.canvas.find_withtag('anki-flip')
        shot('anki-tab-front.png', True)
        app.anki.flip()
        until(app, lambda: app.anki.state['side'] == 'answer' and stats['audio'] >= 2 and not app.anki.busy, 'could not flip')
        assert all(app.anki.canvas.find_withtag('anki-'+str(i)) for i in range(4))
        assert all(not any(c in app.anki.canvas.itemcget(item, 'text') for c in '\u2068\u2069')
                   for item in app.anki.canvas.find_withtag('anki-controls') if app.anki.canvas.type(item) == 'text')
        shot('anki-tab-back.png', True)
        app.menu()
        assert app.panel_mode == 'settings' and app.anki.bounds[-1] == 0
        assert app.base.itemcget(app._panel_win, 'state') == 'normal'
        shot('anki-tab-settings.png')
        app.menu()
        assert app.anki.bounds[-1] == 1
        app.set_view('tt')
        assert app.view == 'tt' and app.base.itemcget(app._cal_win, 'state') == 'normal'
        assert app.anki.bounds[-1] == 0
        app.set_view('cal')
        assert app.selected == selected and app.shown == shown and (app.w(), app.h()) == size
        app.set_view('anki')
        until(app, lambda: app.view == 'anki' and not app.anki.busy, 'could not return to Anki')
        app.anki.rate(2)
        app.anki.rate(2)
        until(app, lambda: stats['answers'] == 1 and not app.anki.busy, 'rating failed')
        assert not app.anki.state['active'] and app.anki.bounds[-1] == 0
        app.anki.rate(2)
        assert stats['answers'] == 1
        app.set_view('cal')
        assert not app.anki.active() and app.base.itemcget(app._panel_win, 'state') == 'normal'
        print('PASS: original Calendar/Timetable/settings, offline status/retry, full-page template HTML/JS/media, real transparency, intervals, guarded rating, tab restore')
    finally:
        app.destroy()
        if host:
            assert host.wait(timeout=10) == 0
        server.shutdown()
        server.server_close()
    log = temp / 'error.log'
    if log.exists():
        text = log.read_text(encoding='utf-8')
        assert '콜백 예외' not in text and 'Traceback' not in text, text


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--screenshots', type=Path)
    parser.add_argument('--allow-current-desktop', action='store_true',
                        help='requires fresh explicit permission; never run on the user desktop by default')
    args = parser.parse_args()
    if not args.allow_current_desktop:
        parser.error('Desktop tests are disabled. Use tools/test_anki_headless.py instead.')
    with TemporaryDirectory(prefix='deskcal-anki-test-') as tmp:
        test(Path(tmp), args.screenshots)
