"""Read-only compatibility with the user's existing dark-card and Zoom add-ons.

No add-on Python is imported/executed, no settings are changed, and no collection
is opened. This is not a general replacement for Anki's card_will_show hooks.
"""
import json
import math
import os
from pathlib import Path


class InstalledCardEffects:
    def __init__(self, addons=None):
        self.addons = Path(addons) if addons is not None else Path(os.environ.get('APPDATA', '')) / 'Anki2/addons21'

    @staticmethod
    def read_json(path):
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def values(self, side):
        css = ''
        dark = self.addons / 'anki_dark_card'
        if dark.is_dir() and not self.read_json(dark / 'meta.json').get('disabled', False):
            try:
                css = (dark / 'dark.css').read_text(encoding='utf-8')
            except OSError:
                pass
        zoom = 1.0
        addon = self.addons / '1923741581'
        meta = self.read_json(addon / 'meta.json')
        if addon.is_dir() and not meta.get('disabled', False):
            config = self.read_json(addon / 'config.json')
            override = meta.get('config')
            if isinstance(override, dict):
                config.update(override)
            value = config.get(side + '_zoom', config.get('review_zoom', 1)) if config.get('different_zoom_question_and_answer', True) else config.get('review_zoom', 1)
            try:
                value = float(value)
                if math.isfinite(value) and .25 <= value <= 5:
                    zoom = value
            except (TypeError, ValueError):
                pass
        return {'css': css, 'zoom': zoom}
