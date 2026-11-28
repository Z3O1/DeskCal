# SPDX-License-Identifier: AGPL-3.0-or-later
"""Card transport for the embedded core. No database or scheduling access in JS."""
import re

BIDI = str.maketrans('', '', '\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069')


def display_card(state, seq, theme):
    side = state.get('side')
    if not state.get('active') or side not in ('question', 'answer'):
        return {'phase': 'done', 'seq': seq, 'theme': theme}
    card = state['card']
    markup = state['rendered']['questionHtml' if side == 'question' else 'answerHtml']
    markup = re.sub(
        r'\[anki:play:([qa]):(\d+)\]',
        lambda m: '<button class="replay-button" onclick="pycmd(\'play:%s:%s\')" aria-label="Play audio">▶</button>' % m.groups(),
        markup)
    return {'phase': side, 'seq': seq, 'theme': theme, 'card_id': card['id'],
            'html': markup, 'classes': 'card card' + str(int(card['templateIndex']) + 1),
            'flag': card.get('flags', 0), 'zoom': 1,
            'audio': state.get('audio', {}), 'autoplay': state.get('autoplay', True),
            'replayQuestion': state.get('replayQuestion', True),
            'buttons': [[item['rating'], item['label'].translate(BIDI)] for item in state['answers']]}
