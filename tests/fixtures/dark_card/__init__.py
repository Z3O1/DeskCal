"""Synthetic CSS hook for portable, isolated headless tests only."""
from pathlib import Path
from aqt import gui_hooks


def inject(html, *_):
    css = Path(__file__).with_name('dark.css').read_text(encoding='utf-8')
    return html + '\n<style>\n' + css + '\n</style>\n'


gui_hooks.card_will_show.append(inject)
