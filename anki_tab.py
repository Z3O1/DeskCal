"""Embedded Anki page inside the original DeskCal Tk/Win32 shell."""
import base64
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog

from anki_core import AnkiCore, CoreError
from anki_render import BIDI, display_card
from anki_settings import AnkiSettings

DISCONNECTED_TEXT = '内置 Anki 暂不可用'
CONNECTING_TEXT = '正在打开内置 Anki…'
RETRY_TEXT = '重试'

LABELS = {
    'en': dict(again='Again', hard='Hard', good='Good', easy='Easy', flip='Show Answer', done='No cards due', loading='Loading card…'),
    'zh': dict(again='重来', hard='困难', good='良好', easy='简单', flip='显示答案', done='没有待学卡片', loading='正在加载卡面…'),
    'ko': dict(again='다시', hard='어려움', good='알맞음', easy='쉬움', flip='정답 보기', done='복습할 카드 없음', loading='카드 여는 중…'),
}


def find_web_assets(root):
    # Assets belong to DeskCal, never to a separately installed Anki.
    path = Path(root) / 'anki_webview/assets'
    return path if (path / 'js/reviewer.js').is_file() else None


class AnkiTab:
    def __init__(self, app, style):
        self.app, self.d = app, style
        self.client = AnkiCore(style.APP_DIR, app.lang)
        # Collection and Rust backend are confined to this one thread, including close.
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix='deskcal-anki')
        self.session = self.media = self.state = None
        self.previous = 'cal'
        self.generation = self.seq = 0
        self.busy = self.ready = self.closed = False
        self.connecting = False
        self.connection_hint = ''
        self.renderer_error = False
        self.canvas = self.browser_canvas = self.window = self.host = None
        self.inbox = queue.Queue()
        self.syncing = False
        self.sync_status_text = self.library_error = ''
        self.settings_ui = None
        self.client.sync.report = lambda text: self.inbox.put(('sync-progress', text))
        self.tick_job = self.refresh_job = None
        self.signature = self.bounds = None
        self.root = Path(style.HERE)
        self.exe = next((p for p in (self.root / 'build/anki-host/CardHost.exe',
                                    self.root / 'anki_webview/CardHost.exe') if p.is_file()), None)
        self.assets = find_web_assets(self.root)

    def active(self):
        return self.app.view == 'anki' and not self.app.compact

    def enter(self):
        if self.closed:
            return
        was_active = self.active()
        if was_active and (self.busy or (self.session is not None and not self.renderer_error)):
            return
        if not was_active:
            self.previous = self.app.view
        self.session = self.media = self.state = None
        self.connecting = False
        self.renderer_error = False
        self.connection_hint = ''
        # Opening the page never launches or connects to an external Anki.
        if not was_active:
            self.app.set_view('anki', _anki_select=True)
        if self.busy:
            self.paint()
            return
        self.assets = find_web_assets(self.root)
        if not self.exe or not self.assets:
            self.renderer_error = True
            self.connection_hint = '缺少内置卡片组件，请重新安装；源码版请先准备宿主和卡片资源'
            self.d.log('Anki tab: bundled WebView2 host or reviewer assets missing')
            self.paint()
            return
        self.connecting = True
        self.paint()
        self.run(self.client.enter, self.entered, entering=True)

    def run(self, function, callback, entering=False, quiet=False, persistent=False, on_error=None):
        if self.busy or self.closed:
            return
        self.busy = True
        generation = None if persistent else self.generation
        def work():
            try:
                value, error = function(), None
            except Exception as exc:
                value, error = None, exc
            self.inbox.put(('api', generation, callback, value, error, entering, on_error))
        self.worker.submit(work)
        if not quiet:
            self.toolbar()
        self.refresh_settings()
        self.ensure_tick()

    def entered(self, result):
        if not self.active():
            return
        self.connecting = False
        self.renderer_error = False
        self.connection_hint = ''
        self.session, self.media = result['session'], result['media']
        self.state = result['review']
        self.signature = None
        # Update media routing before publishing a card from a new session.
        if self.host and self.host.poll() is None:
            self.send_media()
        self.app.render()
        if self.app.panel_mode == 'settings':
            self.refresh_settings()
            self.schedule_refresh()
            return
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
            self.host = subprocess.Popen([str(self.exe), str(self.browser_canvas.winfo_id()),
                                          str(self.root / 'anki_webview/card.html'), str(self.assets), profile],
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self.send_media()
            self.place(force=True)
            threading.Thread(target=self.read_host, args=(self.host,), daemon=True).start()
            self.ensure_tick()
        except OSError:
            self.d.log('Anki tab: WebView2 host failed to start')
            self.disconnected(renderer=True)

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
            fast = self.busy or (self.active() and self.session is not None)
            self.tick_job = self.app.after(40 if fast else 400, self.tick)

    def tick(self):
        self.tick_job = None
        if self.closed:
            return
        try:
            while True:
                item = self.inbox.get_nowait()
                if item[0] == 'api':
                    _, generation, callback, value, error, entering, on_error = item
                    self.busy = False
                    if generation is not None and generation != self.generation:
                        continue
                    if error:
                        self.d.log('Anki tab request failed: ' + self.error_code(error))
                        if on_error:
                            on_error(error)
                        else:
                            self.disconnected(error)
                    else:
                        callback(value)
                elif item[0] == 'sync-progress':
                    if self.syncing:
                        self.sync_status_text = item[1]
                        if self.active() and self.app.panel_mode != 'settings':
                            self.toolbar()
                elif item[0] == 'host' and item[1] is self.host:
                    self.host_event(item[2])
        except queue.Empty:
            pass
        self.refresh_settings()
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
                self.flip(message.get('answer', ''))
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
            self.disconnected(renderer=True)

    def schedule_refresh(self):
        if self.refresh_job:
            self.app.after_cancel(self.refresh_job)
        self.refresh_job = self.app.after(1000, self.refresh)

    def refresh(self):
        self.refresh_job = None
        if self.closed or not self.active() or self.session is None:
            return
        if not self.busy and self.app.panel_mode != 'settings':
            session = self.session
            self.run(lambda: self.client.current(session), self.updated, quiet=True)
        self.schedule_refresh()

    def updated(self, state):
        self.state = state
        self.library_error = ''
        if not self.syncing:
            self.sync_status_text = ''
        self.refresh_settings()
        if self.app.panel_mode != 'settings':
            self.display()

    @staticmethod
    def error_code(error):
        code = type(error).__name__
        if hasattr(error, 'code'):
            code += ' ' + str(error.code)
        return code

    def disconnected(self, error=None, renderer=False):
        self.connecting = False
        self.renderer_error = renderer
        self.session = self.media = self.state = None
        self.signature = None
        self.seq += 1  # Ignore messages from a no-longer-visible card.
        self.send('card ' + json.dumps({'phase': 'done', 'seq': self.seq}))
        self.connection_hint = ('卡片渲染器未就绪，请检查安装组件' if renderer else
                                '请重试；内置牌库与原 Anki 完全独立')
        if isinstance(error, CoreError):
            self.connection_hint = str(error)
        elif error is not None:
            self.connection_hint += '（' + self.error_code(error) + '）'
        if self.refresh_job:
            self.app.after_cancel(self.refresh_job)
            self.refresh_job = None
        self.paint()
        self.place(force=True)

    def can_act(self):
        return (self.active() and self.app.panel_mode != 'settings' and self.ready and not self.busy
                and not self.syncing and self.session is not None and self.state and self.state.get('active')
                and not self.state.get('sync', {}).get('pending'))

    def flip(self, typed_answer=None):
        if self.can_act() and self.state['side'] == 'question':
            if typed_answer is None:
                # Ask the browser for the current input before flipping, including
                # clicks on the native toolbar (not only browser keyboard events).
                self.send('activate')
                return
            token, session = self.state['stateToken'], self.session
            self.run(lambda: self.client.flip(session, token, typed_answer), self.updated)

    def rate(self, index):
        if self.can_act() and self.state['side'] == 'answer' and type(index) is int:
            answers = self.state['answers']
            if 0 <= index < len(answers):
                token, rating, session = self.state['stateToken'], answers[index]['rating'], self.session
                self.run(lambda: self.client.answer(session, token, rating), self.updated)

    def audio(self):
        if self.can_act():
            self.send('card ' + json.dumps({'command': 'audio', 'seq': self.seq}))

    def undo(self):
        if self.state and self.state.get('sync', {}).get('pending'):
            return
        if self.active() and self.session is not None and not self.busy and self.app.panel_mode != 'settings':
            session = self.session
            self.run(lambda: self.client.undo(session), self.updated)

    def render_settings(self, parent):
        self.settings_ui = AnkiSettings(self, parent)
        if self.session is None and not self.busy:
            self.load_library()

    def refresh_settings(self):
        if self.settings_ui is not None and self.settings_ui.alive():
            self.settings_ui.render()

    def load_library(self):
        if self.busy or self.closed:
            return
        self.library_error = ''
        self.run(self.client.enter, self.library_loaded, persistent=True, on_error=self.library_failed)

    def library_loaded(self, result):
        self.session, self.media, self.state = result['session'], result['media'], result['review']
        self.library_error = ''
        self.signature = None
        if self.host and self.host.poll() is None:
            self.send_media()
        self.refresh_settings()
        if self.active() and self.app.panel_mode != 'settings':
            self.entered(result)

    def library_failed(self, error):
        self.library_error = str(error) if isinstance(error, CoreError) else '无法读取内置牌库（%s）' % self.error_code(error)
        self.session = self.state = None
        self.sync_status_text = self.library_error
        self.seq += 1
        self.send('card ' + json.dumps({'phase': 'done', 'seq': self.seq}))
        self.place()
        self.refresh_settings()

    def settings_failed(self, error):
        self.sync_status_text = str(error) if isinstance(error, CoreError) else '操作未完成（%s），请重试' % self.error_code(error)
        self.load_library()

    def sync_action(self, function):
        if self.busy or self.session is None or self.closed:
            return
        self.syncing = True
        self.sync_status_text = '正在处理同步请求…'
        self.client.sync.prepare()
        self.seq += 1
        self.send('card ' + json.dumps({'phase': 'done', 'seq': self.seq}))
        self.run(function, self.sync_finished, persistent=True, on_error=self.sync_failed)

    def sync_finished(self, result):
        self.syncing = False
        library = result.get('library')
        self.sync_status_text = result.get('error') or (library['review'].get('notice', '') if library else '请重新读取内置牌库')
        if library:
            self.library_loaded(library)
        else:
            self.library_failed(CoreError(self.sync_status_text))
        self.refresh_settings()

    def sync_failed(self, error):
        self.syncing = False
        self.settings_failed(error)

    def sign_in(self, username, password, remember, changed=False):
        session = self.session
        self.sync_action(lambda: self.client.sync.sign_in(session, username, password, remember, changed))

    def sign_out(self):
        session = self.session
        self.sync_action(lambda: self.client.sync.sign_out(session))

    def start_sync(self):
        session = self.session
        self.sync_action(lambda: self.client.sync.start(session))

    def continue_full_sync(self, token, direction):
        session = self.session
        self.sync_action(lambda: self.client.sync.continue_full(session, token, direction))

    def cancel_pending_sync(self):
        session = self.session
        self.sync_action(lambda: self.client.sync.cancel_pending(session))

    def cancel_sync(self):
        if self.syncing:
            self.client.sync.request_cancel()
            self.sync_status_text = '正在取消同步…'
            self.refresh_settings()

    def select_deck(self, deck_id):
        if self.busy or self.session is None:
            return
        session = self.session
        self.run(lambda: self.client.select_deck(session, deck_id), self.updated,
                 persistent=True, on_error=self.settings_failed)

    def import_package(self):
        if self.busy or self.session is None:
            return
        filename = filedialog.askopenfilename(parent=self.app, title='导入到 DeskCal 独立牌库',
                                               filetypes=[('Anki 牌组包', '*.apkg')])
        if filename:
            session = self.session
            self.run(lambda: self.client.import_package(session, filename), self.updated,
                     persistent=True, on_error=self.settings_failed)

    def export_package(self):
        if self.busy or self.session is None:
            return
        filename = filedialog.asksaveasfilename(parent=self.app, title='导出全部牌组及学习进度',
                                                defaultextension='.apkg', initialfile='DeskCal-decks.apkg',
                                                filetypes=[('Anki 牌组包', '*.apkg')])
        if filename:
            session = self.session
            self.run(lambda: self.client.export_package(session, filename), self.updated,
                     persistent=True, on_error=self.settings_failed)

    def leave(self):
        self.generation += 1
        if self.active():
            self.app.set_view(self.previous if self.previous in ('cal', 'tt') else 'cal')

    def hide(self):
        self.send('card ' + json.dumps({'command': 'stop'}))
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
            # The transparent browser's parent never contains status text, avoiding
            # a stale backing surface when reconnecting from the offline page.
            self.browser_canvas = tk.Canvas(self.canvas, highlightthickness=0, bd=0)
            self.browser_canvas.bind('<Button-3>', app.menu)
        width, height = app.w() - 2 * app.pad, app.h() - app.head_h - app.pad
        app.base.coords(self.window, app.pad, app.head_h)
        app.base.itemconfigure(self.window, state='normal', width=width, height=height)
        self.canvas.configure(width=width, height=height, bg=d.BG)
        self.paint()
        self.place(force=True)
        self.display()
        if self.session is not None and (not self.host or self.host.poll() is not None):
            if self.exe and self.assets:
                self.ready = False
                self.start_host()
            else:
                self.disconnected(CoreError('缺少内置卡片组件，请检查安装文件'), renderer=True)

    def paint(self):
        if self.canvas is None or not self.active():
            return
        app, d, c = self.app, self.d, self.canvas
        c.delete('glass')
        app.glass_under(c, app.pad, app.head_h)
        self.status()
        self.toolbar()
        if self.browser_canvas is not None:
            self.browser_canvas.configure(bg=d.BG)
            self.browser_canvas.delete('glass')
            app.glass_under(self.browser_canvas, app.pad, app.head_h)
        self.send('moved')

    def status(self):
        if self.canvas is None:
            return
        app, d, c = self.app, self.d, self.canvas
        c.delete('anki-status')
        if self.session is not None and self.state and self.state.get('active'):
            return
        width = app.w() - 2 * app.pad
        body_height = app.h() - app.head_h - app.pad - app.px(83)
        title = CONNECTING_TEXT if self.connecting else DISCONNECTED_TEXT
        if self.renderer_error:
            title = '卡片渲染器未就绪'
        hint = self.connection_hint
        if self.session is not None:
            empty = not self.state.get('totalCards')
            title = '欢迎使用内置 Anki' if empty else '当前牌组没有待学卡片'
            hint = '在齿轮设置中登录 AnkiWeb 同步，或导入 .apkg 牌组' if empty else '在齿轮设置中切换牌组，或稍后继续学习'
            if self.state.get('sync', {}).get('pending'):
                title, hint = '请确认同步方向', '在齿轮设置中确认或取消全量同步'
            if self.state.get('blockedReason'):
                title, hint = '当前牌库无法复习', self.state['blockedReason']
        c.create_text(width / 2, body_height / 2 - app.px(14), text=title,
                      fill=d.FG, font=app.f(18, True), tags='anki-status')
        if hint:
            c.create_text(width / 2, body_height / 2 + app.px(22), text=hint,
                          width=max(1, width-app.px(40)), fill=d.MUTED,
                          font=app.f(11), tags='anki-status')

    def toolbar(self):
        if self.canvas is None:
            return
        app, d, c = self.app, self.d, self.canvas
        c.delete('anki-controls')
        labels = LABELS.get(app.lang, LABELS['en'])
        width, height = app.w() - 2 * app.pad, app.h() - app.head_h - app.pad
        phase = self.state.get('side') if self.state and self.state.get('active') else 'done'
        cy = height - app.px(25)
        if self.session is not None and self.state:
            counts = self.state.get('counts', {})
            notice = self.state.get('notice') or ('新卡 %d · 学习 %d · 复习 %d' %
                       (counts.get('new', 0), counts.get('learning', 0), counts.get('review', 0)))
            c.create_text(width/2, height-app.px(65), text=(self.sync_status_text or '正在同步…') if self.syncing else ('正在处理…' if self.busy else notice),
                          fill=d.MUTED, font=app.f(10), width=max(1, width-app.px(12)), tags='anki-controls')
        if self.session is None:
            if not self.connecting:
                self.button('retry', width / 2 - app.px(90), cy, app.px(180), RETRY_TEXT, self.enter, True)
        elif phase == 'question':
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
        c.tag_bind(tag, '<Button-1>', lambda _: callback() if not self.busy else None)
        c.tag_bind(tag, '<Enter>', lambda _: c.configure(cursor='hand2'))
        c.tag_bind(tag, '<Leave>', lambda _: c.configure(cursor=''))

    def place(self, force=False):
        if self.canvas is None:
            return
        app = self.app
        show = (self.active() and app.panel_mode != 'settings' and self.ready
                and self.session is not None and self.state and self.state.get('active'))
        width, height = max(1, app.w()-2*app.pad), max(1, app.h()-app.head_h-app.pad-app.px(83))
        if self.browser_canvas is not None:
            if show:
                self.browser_canvas.place(x=0, y=0, width=width, height=height)
            else:
                self.browser_canvas.place_forget()
        bounds = (0, 0, width, height, int(bool(show)))
        if force or bounds != self.bounds:
            self.bounds = bounds
            self.send('bounds ' + ' '.join(map(str, bounds)))

    def display(self):
        if not self.state or not self.active() or self.app.panel_mode == 'settings':
            return
        self.status()
        self.toolbar()
        self.place()
        signature = json.dumps([self.state.get('card'), self.state.get('side'), self.state.get('rendered'), self.app.theme], sort_keys=True)
        if signature != self.signature or not self.ready:
            self.signature = signature
            self.seq += 1
            card = display_card(self.state, self.seq, self.app.theme)
            self.send('card ' + json.dumps(card, ensure_ascii=True))

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.syncing:
            self.client.sync.request_cancel()
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
        def close_core():
            try:
                self.client.close()
            except Exception as error:
                self.d.log('Embedded Anki close failed: ' + self.error_code(error))
        self.worker.submit(close_core)
        self.worker.shutdown(wait=False)
