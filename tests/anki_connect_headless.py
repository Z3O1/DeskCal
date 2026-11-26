"""Real AnkiConnect + Anki 26.x + independent HTML renderer, Linux offscreen only.

Usage: python tests/anki_connect_headless.py --ankiconnect PATH_TO_UPSTREAM_CHECKOUT
Never starts a Windows process, connects to port 8765, or opens a personal profile.
"""
import argparse
import faulthandler
import json
import os
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
from threading import Thread
from time import monotonic
from types import SimpleNamespace
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# These settings are unconditional: DISPLAY/Wayland cannot accidentally select a desktop.
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = '--disable-gpu --single-process --num-raster-threads=1'
os.environ['ANKI_SINGLE_INSTANCE_KEY'] = 'deskcal-offscreen-' + uuid4().hex
os.environ.pop('DISPLAY', None)
os.environ.pop('WAYLAND_DISPLAY', None)

from anki_api import AnkiClient, AnkiError, display_card
from anki_effects import InstalledCardEffects


def main(source, base, dark_card=None):
    faulthandler.dump_traceback_later(25)
    import aqt
    import anki.cards
    from anki.collection import Collection
    from anki.lang import set_lang
    from aqt.main import AnkiQt
    from aqt.profiles import ProfileManager
    from aqt.qt import QEventLoop, QTimer, QUrl, Qt
    from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineScript
    from aqt.mediasrv import PageContext

    def pump():
        loop = QEventLoop()
        QTimer.singleShot(15, loop.quit)
        loop.exec()

    def until(predicate, reason, seconds=20):
        end = monotonic() + seconds
        while monotonic() < end:
            if predicate():
                return
            pump()
        raise AssertionError(reason)

    def call(function):
        result = []
        def work():
            try:
                result.append((function(), None))
            except Exception as exc:
                result.append((None, exc))
        thread = Thread(target=work, daemon=True)
        thread.start()
        until(lambda: bool(result), 'HTTP operation timed out', 30)
        thread.join(1)
        value, error = result[0]
        if error:
            raise error
        return value

    set_lang('en_US')
    pm = ProfileManager(str(base))
    pm.setupMeta()
    pm.create('DeskCal isolated')
    pm.load('DeskCal isolated')
    pm.meta['firstRun'] = False
    pm.profile['autoSync'] = False
    pm.profile['numBackups'] = 0
    pm.save()
    collection = Collection(pm.collectionPath())
    deck = collection.decks.id('Words')
    model = collection.models.by_name('Basic')
    model['tmpls'][0]['qfmt'] = ('{{Front}}<img src="badge.svg" onload="document.getElementById(\'media-status\').textContent=\'ready\'">'
                                '<span id="media-status"></span><script>sessionStorage.word="reflect";</script>')
    model['tmpls'][0]['afmt'] = ('{{FrontSide}}<details open><summary>Meaning</summary>{{Back}}</details>'
                                '<span id="remember"></span><script>document.getElementById("remember").textContent=sessionStorage.word;</script>')
    collection.models.update_dict(model)
    note = collection.new_note(model)
    note['Front'] = '<h1>reflect</h1><span>[rɪˈflekt]</span><font color="navy">example</font>'
    note['Back'] = 'v. 反射'
    collection.add_note(note, deck)
    collection.set_config('estTimes', True)
    media = Path(collection.media.dir())
    (media / 'badge.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"><rect width="8" height="8" fill="green"/></svg>')
    collection.close()
    # Install only the existing read-only CSS injector into the disposable profile.
    addon_source = dark_card or ROOT / 'tests/fixtures/dark_card'
    addons = Path(pm.addonFolder())
    dark = addons / 'anki_dark_card'
    dark.mkdir(parents=True)
    for name in ('__init__.py', 'dark.css', 'manifest.json'):
        shutil.copy2(addon_source / name, dark / name)
    pm.db.close()
    opened, native = [], {}
    aqt.gui_hooks.profile_did_open.append(lambda: opened.append(True))
    AnkiQt.maybe_check_for_addon_updates = lambda *args: None
    AnkiQt.maybe_auto_sync_on_open_close = lambda self, done: done(False)
    anki.cards.time = SimpleNamespace(time=monotonic)
    print('OFFSCREEN: starting isolated Anki', flush=True)
    app = aqt._run([sys.argv[0], '-b', str(base), '-p', 'DeskCal isolated', '-l', 'en_US'], exec=False)
    print('OFFSCREEN: Anki initialized', flush=True)
    mw = aqt.mw
    assert app and app.platformName() == 'offscreen' and mw
    sys.path.insert(0, str(source))
    from plugin import AnkiConnect, util
    owner = AnkiConnect()
    owner.runtime.register_hooks()
    setting = util.setting
    overrides = {'webBindPort': 0, 'webBindAddress': '0.0.0.0', 'apiKey': 'isolated-test-key'}
    util.setting = lambda name: overrides[name] if name in overrides else setting(name)
    owner.startWebServer()
    client = AnkiClient({'endpoint': 'http://127.0.0.1:%d/api/v1' % owner.server.sock.getsockname()[1],
                         'api_key': 'isolated-test-key', 'deck': 'Words', 'timeout': 10})
    page = None
    page_id = 971623

    def capture(html, card, kind):
        native[(card.id, kind)] = html
        return html

    aqt.gui_hooks.card_will_show.append(capture)
    try:
        until(lambda: opened and mw.col and not mw._background_op_count, 'temporary profile did not open')
        print('OFFSCREEN: calling native review API', flush=True)
        result = call(client.enter)
        session = result['session']
        review = result['review']
        until(lambda: mw.state == 'review' and mw.reviewer.state == 'question', 'native reviewer did not start')
        review = call(lambda: client.current(session))
        effects = InstalledCardEffects(addons)
        card = display_card(review, 1, 'dark', effects.values('question'))
        assert card['html'] == native[(int(review['card']['id']), 'reviewQuestion')]
        assert '[rɪˈflekt]' in card['html'] and '<font color="navy">example</font>' in card['html']
        assert mw.col.db.scalar('select count(*) from revlog') == 0

        # The exact production wrapper and real reviewer.js, but a page without a window.
        html = (ROOT / 'anki_webview/card.html').read_text(encoding='utf-8').replace('https://deskcal.invalid/media/', mw.serverURL())
        mw.mediaServer.set_page_html(page_id, html, PageContext.REVIEWER)
        # Chromium single-process mode permits one profile. Reuse Anki's profile,
        # but create a separate page/sessionStorage and install shims only there.
        errors = []
        class InspectPage(QWebEnginePage):
            def javaScriptConsoleMessage(self, level, message, line, source):
                if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
                    errors.append(message)
        page = InspectPage(mw.web.page().profile())
        page.setBackgroundColor(Qt.GlobalColor.transparent)
        shim = QWebEngineScript()
        shim.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        shim.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        shim.setSourceCode('window.__messages=[];window.chrome=window.chrome||{};window.chrome.webview={postMessage:m=>window.__messages.push(m),addEventListener:(name,fn)=>window.__deliver=fn};window.qt={webChannelTransport:{send:()=>{}}};')
        page.scripts().insert(shim)
        loaded = []
        page.loadFinished.connect(loaded.append)
        page.load(QUrl(mw.serverURL() + '_anki/legacyPageData?id=' + str(page_id)))
        until(lambda: bool(loaded), 'independent HTML page did not load')
        assert loaded[-1]

        def js(script):
            replies = []
            page.runJavaScript(script, replies.append)
            until(lambda: bool(replies), 'JavaScript callback did not complete')
            return replies[0]

        until(lambda: js('typeof _showQuestion') == 'function', 'reviewer.js did not initialize')
        js('window.__deliver({data:' + json.dumps(card) + '})')
        until(lambda: js('document.getElementById("media-status")?.textContent') == 'ready', 'template JS or media failed')
        assert js('document.querySelector("h1").textContent') == 'reflect'
        assert js('getComputedStyle(document.querySelector("font")).color') == 'rgb(157, 196, 255)'
        assert js('getComputedStyle(document.body).backgroundColor') == 'rgba(0, 0, 0, 0)'
        assert js('getComputedStyle(document.getElementById("qa")).backgroundColor') == 'rgba(0, 0, 0, 0)'
        assert js('JSON.stringify(window.__messages)').find('isolated-test-key') == -1

        answer = call(lambda: client.flip(session, review['stateToken']))
        assert answer['side'] == 'answer' and all(a['label'] for a in answer['answers'])
        card = display_card(answer, 2, 'dark', {**effects.values('answer'), 'zoom': 1.25})
        assert card['html'] == native[(int(answer['card']['id']), 'reviewAnswer')]
        js('window.__deliver({data:' + json.dumps(card) + '})')
        until(lambda: js('document.getElementById("remember")?.textContent') == 'reflect', 'front/back sessionStorage was not preserved')
        assert js('document.getElementById("qa").style.zoom') == '1.25'
        assert js('document.querySelector("summary").textContent') == 'Meaning'
        card_id, old_token = answer['card']['id'], answer['stateToken']
        call(lambda: client.answer(session, old_token, 'good'))
        assert mw.col.db.scalar('select count(*) from revlog') == 1
        try:
            call(lambda: client.answer(session, old_token, 'good'))
        except AnkiError:
            pass
        else:
            raise AssertionError('duplicate native answer was not rejected')
        assert mw.col.db.scalar('select count(*) from revlog') == 1
        assert not errors, errors
        faulthandler.cancel_dump_traceback_later()
        print('PASS: OFFSCREEN ONLY / real AnkiConnect HTTP / exact native dark-card HTML / template JS and media / transparent CSS / front-back state / zoom / native revlog / stale-rating guard', flush=True)
    finally:
        aqt.gui_hooks.card_will_show.remove(capture)
        if owner.timer:
            owner.timer.stop()
        owner.server.close()
        if page:
            page.deleteLater()
            pump()
        mw.mediaServer.clear_page_html(page_id)
        mw.close()  # This isolated offscreen profile only, never the user's Windows Anki.
        until(lambda: mw.col is None, 'isolated collection did not close')
        app.quit()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ankiconnect', required=True, type=Path)
    parser.add_argument('--dark-card', type=Path, help='existing plugin source for exact-HTML comparison; otherwise use the synthetic fixture')
    args = parser.parse_args()
    cache = Path.home() / '.cache/pi/deskcal-anki'
    cache.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='offscreen-', dir=cache) as temp:
        main(args.ankiconnect.resolve(), Path(temp), args.dark_card.resolve() if args.dark_card else None)
