"""Standard AnkiConnect v1 client. No collection files are opened by DeskCal."""
import itertools
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler

DEFAULT_DECK = '英语单词::大学四级英语单词'
BIDI = str.maketrans('', '', '\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069')
RATINGS = ('again', 'hard', 'good', 'easy')


class AnkiError(Exception):
    pass


class AnkiClient:
    def __init__(self, settings=None):
        settings = dict(settings) if isinstance(settings, dict) else {}
        self.settings = settings
        self.endpoint = settings.get('endpoint', 'http://127.0.0.1:8765/api/v1')
        self.key = settings.get('api_key', '')
        self.deck = settings.get('deck', DEFAULT_DECK)
        try:
            self.timeout = max(.1, min(30, float(settings.get('timeout', 2))))
        except (TypeError, ValueError):
            self.timeout = 2
        self.ids = itertools.count(1)
        # Local IPC must not accidentally go through the user's HTTP proxy.
        self.http = build_opener(ProxyHandler({}))

    @staticmethod
    def read_json(path):
        try:
            value = json.loads(Path(path).read_text(encoding='utf-8'))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    @classmethod
    def from_file(cls, path):
        settings = cls.read_json(path)
        # A packaged DeskCal must not contain a personal key. For local IPC only,
        # read the same user's existing AnkiConnect settings, without changing them.
        endpoint = settings.get('endpoint', 'http://127.0.0.1:8765/api/v1')
        try:
            local = urlsplit(endpoint).hostname in ('localhost', '127.0.0.1', '::1')
        except (TypeError, ValueError):
            local = False
        appdata = os.environ.get('APPDATA')
        if local and appdata:
            addons = Path(settings.get('addons_dir') or Path(appdata) / 'Anki2/addons21')
            addon = addons / '2055492159'
            meta = cls.read_json(addon / 'meta.json')
            config = cls.read_json(addon / 'config.json')
            override = meta.get('config')
            if isinstance(override, dict):
                config.update(override)
            if not meta.get('disabled', False):
                if 'api_key' not in settings:
                    settings['api_key'] = config.get('apiKey') or ''
                port = config.get('webBindPort', 8765)
                if 'endpoint' not in settings and type(port) is int and 1 <= port <= 65535:
                    settings['endpoint'] = 'http://127.0.0.1:%d/api/v1' % port
        return cls(settings)

    def request(self, method, **params):
        ident = next(self.ids)
        body = json.dumps({'jsonrpc': '2.0', 'id': ident, 'method': method, 'params': params}).encode()
        headers = {'Content-Type': 'application/json'}
        if self.key:
            headers['Authorization'] = 'Bearer ' + self.key
        request = Request(self.endpoint, data=body, headers=headers, method='POST')
        with self.http.open(request, timeout=self.timeout) as reply:
            data = json.load(reply)
        if data.get('id') != ident:
            raise AnkiError('Mismatched response')
        if 'error' in data:
            raise AnkiError(data['error'].get('message', 'Anki request failed'))
        return data['result']

    def call(self, method, **params):
        value = self.request(method, **params)
        if not isinstance(value, dict) or 'operationId' not in value:
            return value
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            operation = self.request('operations.get', operationId=value['operationId'])
            if operation['state'] == 'succeeded':
                return operation['result']
            if operation['state'] in ('failed', 'cancelled'):
                raise AnkiError(operation['error'].get('message', 'Anki operation failed'))
            if operation['state'] == 'waitingForUser':
                raise AnkiError('Anki is waiting for user input')
            time.sleep(.05)
        raise AnkiError('Anki operation timed out; not retried')

    def enter(self):
        collection = self.call('collection.get')
        session = collection['session']
        media = self.call('media.getDirectory', session=session)['path']
        state = self.call('reviewer.get', session=session)
        deck_name = ((state.get('card') or {}).get('deck') or {}).get('name', '')
        if not state['active'] or (self.deck and deck_name != self.deck and not deck_name.startswith(self.deck + '::')):
            self.call('application.navigate', session=session, view='review', deck={'name': self.deck})
            state = self.call('reviewer.get', session=session)
        return {'session': session, 'media': media, 'review': state}

    def current(self, session):
        return self.call('reviewer.get', session=session)

    def flip(self, session, token):
        self.call('reviewer.showAnswer', session=session, stateToken=token)
        return self.current(session)

    def answer(self, session, token, rating):
        if rating not in RATINGS:
            raise AnkiError('Invalid rating')
        # AnkiConnect checks the session, native reviewer state and prediction token.
        # Never retry a write: a lost HTTP response does not mean it did not commit.
        self.call('reviewer.answer', session=session, stateToken=token, rating=rating)
        return self.current(session)

    def audio(self, session, token):
        self.call('reviewer.playAudio', session=session, stateToken=token)
        return self.current(session)


def display_card(state, seq, theme, effects=None):
    """Transport the original rendered template, not a projection of note fields."""
    side = state.get('side')
    if not state.get('active') or side not in ('question', 'answer'):
        return {'phase': 'done', 'seq': seq, 'theme': theme}
    rendered, card = state['rendered'], state['card']
    markup = rendered['questionHtml' if side == 'question' else 'answerHtml']
    # Native rendering emits [anki:play:q:0] placeholders. All replay buttons use
    # Anki's own current-side replay, without exposing filesystem or API access.
    markup = re.sub(r'\[anki:play:[qa]:\d+\]',
                    '<button class="replay-button" onclick="pycmd(\'play\')" aria-label="Play audio">▶</button>', markup)
    effects = effects or {}
    if effects.get('css'):
        markup += '\n<style>\n' + effects['css'] + '\n</style>\n'
    return {'phase': side, 'seq': seq, 'theme': theme, 'card_id': card['id'],
            'zoom': effects.get('zoom', 1),
            # AnkiConnect v1 uses Card.question()/answer(), which already include CSS.
            'html': markup,
            'classes': 'card card' + str(int(card['templateIndex']) + 1),
            'flag': card.get('flags', 0),
            'buttons': [[item['rating'], item['label'].translate(BIDI)] for item in state['answers']]}
