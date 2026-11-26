"""Anki view controller for the original DeskCal window (standard-library only)."""
import base64
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import tkinter as tk

from anki_api import AnkiClient, BIDI, display_card
from anki_effects import InstalledCardEffects

LABELS = {
    'en': dict(again='Again', hard='Hard', good='Good', easy='Easy', flip='Show Answer', done='No cards due', loading='Loading card…'),
    'zh': dict(again='重来', hard='困难', good='良好', easy='简单', flip='显示答案', done='没有待学卡片', loading='正在加载卡面…'),
    'ko': dict(again='다시', hard='어려움', good='알맞음', easy='쉬움', flip='정답 보기', done='복습할 카드 없음', loading='카드 여는 중…'),
}


def find_web_assets(configured=None):
    if configured:
        path = Path(configured)
        if (path / 'js/reviewer.js').is_file():
            return path
    local = Path(os.environ.get('LOCALAPPDATA', ''))
    for root in (local / 'Programs/Anki', Path(os.environ.get('PROGRAMFILES', '')) / 'Anki'):
        path = root / 'app_packages/_aqt/data/web'
        if (path / 'js/reviewer.js').is_file():
            return path
    return None


class AnkiTab:
    def __init__(self, app, style):
        self.app, self.d = app, style
        self.client = AnkiClient.from_file(Path(style.APP_DIR) / 'anki-connect.json')
        self.effects = InstalledCardEffects(self.client.settings.get('addons_dir'))
        self.session = self.media = self.state = None
        self.previous = 'cal'
        self.generation = self.seq = 0
        self.busy = self.ready = self.closed = False
        self.canvas = self.window = self.host = None
        self.inbox = queue.Queue()
        self.tick_job = self.refresh_job = None
        self.signature = self.bounds = None
        self.root = Path(style.HERE)
        self.exe = next((p for p in (self.root / 'build/anki-host/CardHost.exe',
                                    self.root / 'anki_webview/CardHost.exe') if p.is_file()), None)
        self.assets = find_web_assets(self.client.settings.get('web_assets'))

    def active(self):
        return self.app.view == 'anki' and not self.app.compact

    def enter(self):
        if self.closed or self.busy or self.active():
            return
        if not self.exe or not self.assets:
            self.d.log('Anki tab: build the WebView2 host and install Anki web resources first')
            return
        self.previous = self.app.view
        self.run(self.client.enter, self.entered, entering=True)

    def run(self, function, callback, entering=False):
        if self.busy or self.closed:
            return
        self.busy = True
        generation = self.generation
        def work():
            try:
                value, error = function(), None
            except Exception as exc:
                value, error = None, exc
            self.inbox.put(('api', generation, callback, value, error, entering))
        threading.Thread(target=work, daemon=True).start()
        self.ensure_tick()

    def entered(self, result):
        if self.app.view != self.previous:
            return
        self.session, self.media = result['session'], result['media']
        self.state = result['review']
        self.signature = None
        # Update the native resource mapping before set_view() publishes HTML.
        if self.host and self.host.poll() is None:
            self.send_media()
        self.app.set_view('anki', _anki_ready=True)
        if not self.host or self.host.poll() is not None:
            self.host = None
            self.ready = False
            self.start_host()
        else:
            self.display()
        self.schedule_refresh()

    def start_host(self):
        self.app.update_idletasks()
        try:
            profile = str(Path(self.d.APP_DIR) / 'anki-webview-profile')
            self.host = subprocess.Popen([str(self.exe), str(self.canvas.winfo_id()),
                                          str(self.root / 'anki_webview/card.html'), str(self.assets), profile],
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self.send_media()
            self.place(force=True)
            threading.Thread(target=self.read_host, args=(self.host,), daemon=True).start()
            self.ensure_tick()
        except OSError:
            self.d.log('Anki tab: WebView2 host failed to start')
            self.leave()

    def read_host(self, host):
        buffer = b''
        try:
            while True:
                chunk = os.read(host.stdout.fileno(), 8192)
                if not chunk:
                    break
                buffer += chunk
                while b'\n' in buffer:
                    line, _, buffer = buffer.partition(b'\n')
                    self.inbox.put(('host', host, line.strip()))
                if len(buffer) > 65536:
                    buffer = b''
        except OSError:
            pass
        self.inbox.put(('host', host, b'closed'))

    def send(self, message):
        if self.host and self.host.poll() is None:
            try:
                self.host.stdin.write(message.encode('utf-8') + b'\n')
                self.host.stdin.flush()
            except (OSError, ValueError):
                pass

    def send_media(self):
        self.send('media ' + base64.b64encode(self.media.encode('utf-8')).decode('ascii'))

    def ensure_tick(self):
        if self.tick_job is None and not self.closed:
            self.tick_job = self.app.after(40 if self.active() or self.busy else 400, self.tick)

    def tick(self):
        self.tick_job = None
        if self.closed:
            return
        try:
            while True:
                item = self.inbox.get_nowait()
                if item[0] == 'api':
                    _, generation, callback, value, error, entering = item
                    self.busy = False
                    if generation != self.generation:
                        continue
                    if error:
                        # Offline entry leaves every existing calendar state unchanged.
                        if not entering:
                            self.d.log('Anki tab request failed: ' + type(error).__name__)
                            self.leave()
                    else:
                        callback(value)
                elif item[1] is self.host:
                    self.host_event(item[2])
        except queue.Empty:
            pass
        if self.active():
            self.place()
        if self.host or self.busy:
            self.ensure_tick()

    def host_event(self, line):
        if line == b'ready':
            self.ready = True
            self.signature = None
            self.display()
        elif line.startswith(b'msg '):
            try:
                message = json.loads(line[4:])
            except (ValueError, UnicodeError):
                return
            if not isinstance(message, dict) or message.get('seq') != self.seq:
                return
            action = message.get('action')
            if action == 'flip':
                self.flip()
            elif action == 'rate':
                self.rate(message.get('index'))
            elif action == 'audio':
                self.audio()
            elif action == 'undo':
                self.undo()
        elif line.startswith(b'error ') or line == b'closed':
            self.ready = False
            if self.host:
                try:
                    self.host.stdin.close()
                except (OSError, ValueError):
                    pass
                self.host = None
            self.d.log('Anki tab: renderer unavailable')
            if self.active():
                self.leave()

    def schedule_refresh(self):
        if self.refresh_job:
            self.app.after_cancel(self.refresh_job)
        self.refresh_job = self.app.after(1000, self.refresh)

    def refresh(self):
        self.refresh_job = None
        if self.closed or not self.active():
            return
        if not self.busy:
            self.run(lambda: self.client.current(self.session), self.updated)
        self.schedule_refresh()

    def updated(self, state):
        self.state = state
        self.display()

    def can_act(self):
        return (self.active() and self.app.panel_mode != 'settings' and self.ready and not self.busy
                and self.state and self.state.get('active'))

    def flip(self):
        if self.can_act() and self.state['side'] == 'question':
            token = self.state['stateToken']
            self.run(lambda: self.client.flip(self.session, token), self.updated)

    def rate(self, index):
        if self.can_act() and self.state['side'] == 'answer' and type(index) is int:
            answers = self.state['answers']
            if 0 <= index < len(answers):
                token, rating = self.state['stateToken'], answers[index]['rating']
                self.run(lambda: self.client.answer(self.session, token, rating), self.updated)

    def audio(self):
        if self.can_act():
            token = self.state['stateToken']
            self.run(lambda: self.client.audio(self.session, token), self.updated)

    def undo(self):
        if self.active() and not self.busy and self.app.panel_mode != 'settings':
            def work():
                self.client.call('collection.undo', session=self.session)
                return self.client.current(self.session)
            self.run(work, self.updated)

    def leave(self):
        self.generation += 1
        if self.active():
            self.app.set_view(self.previous if self.previous in ('cal', 'tt') else 'cal')

    def hide(self):
        if self.window is not None:
            self.app.base.itemconfigure(self.window, state='hidden')
        self.place()

    def render(self):
        app, d = self.app, self.d
        app.set_title('Anki')
        app.base.itemconfigure(app._cal_win, state='hidden')
        settings = app.panel_mode == 'settings'
        for tag in ('panel_bg', app._panel_win):
            app.base.itemconfigure(tag, state='normal' if settings else 'hidden')
        if settings:
            self.hide()
            app.render_panel()
            return
        if self.canvas is None:
            self.canvas = tk.Canvas(app.base, highlightthickness=0, bd=0)
            self.window = app.base.create_window(app.pad, app.head_h, window=self.canvas, anchor='nw')
            self.canvas.bind('<Button-3>', app.menu)
        width, height = app.w() - 2 * app.pad, app.h() - app.head_h - app.pad
        app.base.coords(self.window, app.pad, app.head_h)
        app.base.itemconfigure(self.window, state='normal', width=width, height=height)
        self.canvas.configure(width=width, height=height, bg=d.BG)
        self.paint()
        self.place(force=True)
        self.display()

    def paint(self):
        if self.canvas is None or not self.active():
            return
        app, d, c = self.app, self.d, self.canvas
        c.delete('glass')
        app.glass_under(c, app.pad, app.head_h)
        self.toolbar()
        self.send('moved')

    def toolbar(self):
        if self.canvas is None:
            return
        app, d, c = self.app, self.d, self.canvas
        c.delete('anki-controls')
        labels = LABELS.get(app.lang, LABELS['en'])
        width, height = app.w() - 2 * app.pad, app.h() - app.head_h - app.pad
        phase = self.state.get('side') if self.state and self.state.get('active') else 'done'
        cy = height - app.px(25)
        if phase == 'question':
            self.button('flip', width / 2 - app.px(90), cy, app.px(180), labels['flip'], self.flip, True)
        elif phase == 'answer':
            answers = self.state['answers']
            gap = app.px(8)
            bw = (width - gap * (len(answers) - 1)) / max(1, len(answers))
            for i, answer in enumerate(answers):
                x = i * (bw + gap)
                text = answer['label'].translate(BIDI)
                c.create_text(x + bw / 2, cy - app.px(27), text=text, fill=d.MUTED,
                              font=app.f(11), tags='anki-controls')
                self.button(str(i), x, cy, bw, labels[answer['rating']], lambda i=i: self.rate(i),
                            answer['rating'] == 'good')
        else:
            c.create_text(width / 2, cy, text=labels['done'], fill=d.FG, font=app.f(13), tags='anki-controls')

    def button(self, name, x, y, width, text, callback, active=False):
        app, d, c = self.app, self.d, self.canvas
        tag = 'anki-' + name
        fill = d.SEL_BG if active else d.mix(d.BG, d.FG, .12)
        d.round_rect(c, x, y-app.px(17), x+width, y+app.px(17), app.px(9),
                     fill=fill, outline='', tags=('anki-controls', tag))
        c.create_text(x+width/2, y, text=text, fill=d.FG, font=app.f(12, active), tags=('anki-controls', tag))
        c.tag_bind(tag, '<Button-1>', lambda _: callback())
        c.tag_bind(tag, '<Enter>', lambda _: c.configure(cursor='hand2'))
        c.tag_bind(tag, '<Leave>', lambda _: c.configure(cursor=''))

    def place(self, force=False):
        if self.canvas is None:
            return
        app = self.app
        show = self.active() and app.panel_mode != 'settings' and self.state and self.state.get('active')
        bounds = (0, 0, max(1, app.w()-2*app.pad),
                  max(1, app.h()-app.head_h-app.pad-app.px(83)), int(bool(show)))
        if force or bounds != self.bounds:
            self.bounds = bounds
            self.send('bounds ' + ' '.join(map(str, bounds)))

    def display(self):
        if not self.state or not self.active():
            return
        self.toolbar()
        self.place()
        effects = self.effects.values(self.state.get('side', 'question'))
        signature = json.dumps([self.state.get('card'), self.state.get('side'), self.state.get('rendered'), self.app.theme, effects], sort_keys=True)
        if signature != self.signature or not self.ready:
            self.signature = signature
            self.seq += 1
            card = display_card(self.state, self.seq, self.app.theme, effects)
            self.send('card ' + json.dumps(card, ensure_ascii=True))

    def close(self):
        self.closed = True
        self.generation += 1
        for job in (self.tick_job, self.refresh_job):
            if job:
                try:
                    self.app.after_cancel(job)
                except tk.TclError:
                    pass
        if self.host:
            try:
                self.host.stdin.close()
            except (OSError, ValueError):
                pass
