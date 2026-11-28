# SPDX-License-Identifier: AGPL-3.0-or-later
"""Embedded official Anki core; no aqt, HTTP API, or external Anki process.

Construct on the UI thread, then use *all* methods on one dedicated worker.
The collection path is fixed beneath DeskCal's own data directory. Never open
an installed Anki profile or accept a collection path from a card/template.
"""
import html
import json
from pathlib import Path
import re
import sys
import sysconfig
from urllib.parse import quote
from uuid import uuid4

from anki_sync import AnkiSync

ANKI_VERSION = '26.9.2'
RATINGS = ('again', 'hard', 'good', 'easy')
TYPE_PATTERN = re.compile(r'\[\[type:(.+?)\]\]')


class CoreError(Exception):
    """A safe, user-facing error from the embedded collection."""


class AnkiCore:
    def __init__(self, data_dir, language='en'):
        self.directory = Path(data_dir) / 'anki'
        self.language = {'zh': 'zh_CN', 'ko': 'ko_KR'}.get(language, 'en_US')
        self.col = self.card = self.states = None
        self.session = self.token = None
        self.side = 'question'
        self.typed_answer = ''
        self.settings = {}
        self.notice = ''
        self.counts = {}
        self.blocked_reason = ''
        self.sync = AnkiSync(self)

    def _open(self):
        if self.col is not None:
            if self.col.db is None:
                self.col.reopen(after_full_sync=True)
            return
        vendor = Path(__file__).resolve().parent / 'anki_vendor'
        if (vendor / 'deskcal-vendor.json').is_file():
            manifest = json.loads((vendor / 'deskcal-vendor.json').read_text(encoding='utf-8'))
            if (manifest.get('python') == '%d.%d' % sys.version_info[:2]
                    and manifest.get('platform') == sysconfig.get_platform().replace('-', '_')):
                if str(vendor) not in sys.path:
                    sys.path.insert(0, str(vendor))
        try:
            from importlib.metadata import version
            import anki
            from anki.collection import Collection
            from anki.lang import set_lang
        except ImportError as error:
            raise CoreError('缺少内置 Anki 内核；源码版请安装 requirements-anki.txt 中的依赖') from error
        if version('anki') != ANKI_VERSION:
            raise CoreError('内置内核版本不匹配，请安装 anki==' + ANKI_VERSION)
        self.directory.mkdir(parents=True, exist_ok=True)
        try:
            settings = json.loads((self.directory / 'settings.json').read_text(encoding='utf-8'))
            self.settings = settings if isinstance(settings, dict) else {}
        except (OSError, ValueError):
            self.settings = {}
        set_lang(self.language)
        collection_path = self.directory / 'collection.anki2'
        new_collection = not collection_path.exists()
        col = Collection(str(collection_path))
        try:
            if new_collection:
                if col.sched_ver() != 2:
                    col.upgrade_to_v2_scheduler()
                col.set_v3_scheduler(True)
            selected = self.settings.get('deck_id')
            if type(selected) is int and col.decks.get(selected, default=False):
                col.decks.select(selected)
            self.col = col
            self.session = uuid4().hex
            self.sync.load()
            self._backup(force=False)
        except Exception:
            self.col = None
            col.close()
            raise

    def _backup(self, force):
        backups = self.directory / 'backups'
        backups.mkdir(exist_ok=True)
        self.col.create_backup(backup_folder=str(backups), force=force, wait_for_completion=True)

    def _check(self, session, token=None, side=None):
        if self.col is None or self.col.db is None or session != self.session:
            raise CoreError('复习已失效，请重新读取内置牌库')
        if token is not None and self.sync.pending:
            raise CoreError('请先在设置中确认或取消全量同步')
        if token is not None and (not self.card or token != self.token or self.side != side):
            raise CoreError('这张卡片已更新，未重复提交评分')

    def _reset(self):
        self.card = self.states = None
        self.side = 'question'
        self.typed_answer = ''
        self.token = uuid4().hex
        self.sync.invalidate_pending()

    def _save_settings(self):
        temporary = self.directory / 'settings.json.tmp'
        temporary.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        temporary.replace(self.directory / 'settings.json')

    def _next(self):
        from anki.cards import Card
        from anki.collection import Config
        self.blocked_reason = ''
        if self.col.get_config_string(Config.String.CARD_STATE_CUSTOMIZER):
            self.blocked_reason = '此牌库使用自定义排程 JavaScript，内置模式暂不支持；请勿在此评分'
        elif not self.col.v3_scheduler():
            self.blocked_reason = '此牌库使用旧排程，请先在官方 Anki 中升级后同步'
        if self.blocked_reason:
            self._reset()
            self.counts = {}
            return
        queued = self.col.sched.get_queued_cards()
        self.counts = {'new': queued.new_count, 'learning': queued.learning_count, 'review': queued.review_count}
        if self.card is None and queued.cards:
            first = queued.cards[0]
            self.card = Card(self.col)
            self.card._load_from_backend_card(first.card)
            self.card.start_timer()
            self.states = first.states
            self.states.current.custom_data = first.card.custom_data
            self.side = 'question'
            self.token = uuid4().hex

    def enter(self):
        self._open()
        return self._result()

    def _result(self):
        return {'session': self.session, 'media': self.col.media.dir(), 'review': self.current(self.session)}

    def current(self, session):
        self._check(session)
        if not self.sync.pending:
            self._next()
        selected = self.col.decks.get_current_id()
        decks = [{'id': int(deck.id), 'name': deck.name}
                 for deck in self.col.decks.all_names_and_ids()]
        state = {'active': self.card is not None, 'side': self.side, 'stateToken': self.token,
                 'decks': decks, 'selectedDeck': int(selected), 'counts': self.counts,
                 'deckName': self.col.decks.name(selected), 'notice': self.notice,
                 'totalCards': self.col.card_count(), 'answers': [],
                 'sync': self.sync.public_state(), 'blockedReason': self.blocked_reason}
        if self.card is None:
            return state
        card = self.card
        question = self._typed_html(card.question(), answer=False)
        answer = self._typed_html(card.answer(), answer=True)
        state.update(card={'id': str(card.id), 'templateIndex': int(card.ord),
                           'flags': card.user_flag(), 'deck': {'name': self.col.decks.name(card.did)}},
                     rendered={'questionHtml': question, 'answerHtml': answer},
                     audio={'question': self._audio_tags(card.question_av_tags()),
                            'answer': self._audio_tags(card.answer_av_tags())},
                     autoplay=card.autoplay(), replayQuestion=card.replay_question_audio_on_answer_side())
        if self.side == 'answer':
            labels = self.col.sched.describe_next_states(self.states)
            state['answers'] = [{'rating': rating, 'label': labels[i]}
                                for i, rating in enumerate(RATINGS)]
        return state

    def _typed_html(self, markup, answer):
        def replace(match):
            field = match.group(1)
            cloze = field.startswith('cloze:')
            if cloze:
                field = field[len('cloze:'):]
            combining = not field.startswith('nc:')
            if not combining:
                field = field[len('nc:'):]
            note = self.card.note()
            if field not in note:
                return html.escape('Unknown answer field: ' + field)
            expected = note[field]
            if cloze:
                expected = self.col.extract_cloze_for_typing(expected, self.card.ord + 1)
            if not expected:
                return ''
            if answer:
                return '<div id="typeans">' + self.col.compare_answer(expected, self.typed_answer, combining) + '</div>'
            return '<input type="text" id="typeans" autocomplete="off" onkeypress="_typeAnsPress();">'
        return TYPE_PATTERN.sub(replace, markup)

    @staticmethod
    def _audio_tags(tags):
        from anki.sound import SoundOrVideoTag, TTSTag
        result = []
        for tag in tags:
            if isinstance(tag, SoundOrVideoTag):
                # Shared-deck media must never escape the embedded media directory.
                name = tag.filename
                if name and '/' not in name and '\\' not in name and ':' not in name and '\0' not in name and name not in ('.', '..'):
                    result.append({'url': quote(name, safe='')})
            elif isinstance(tag, TTSTag):
                result.append({'text': tag.field_text, 'lang': tag.lang,
                               'voices': tag.voices, 'rate': tag.speed})
        return result

    def flip(self, session, token, typed_answer=''):
        self._check(session, token, 'question')
        self.typed_answer = typed_answer[:100000] if isinstance(typed_answer, str) else ''
        self.side = 'answer'
        self.token = uuid4().hex
        return self.current(session)

    def answer(self, session, token, rating):
        from anki.scheduler.v3 import CardAnswer
        self._check(session, token, 'answer')
        if rating not in RATINGS:
            raise CoreError('无效评分')
        native_rating = (CardAnswer.AGAIN, CardAnswer.HARD, CardAnswer.GOOD, CardAnswer.EASY)[RATINGS.index(rating)]
        answer = self.col.sched.build_answer(card=self.card, states=self.states, rating=native_rating)
        # Invalidate BEFORE the write: never retry an uncertain scheduling write.
        self.token = uuid4().hex
        try:
            self.col.sched.answer_card(answer)
        finally:
            self._reset()
        return self.current(session)

    def undo(self, session):
        self._check(session)
        if self.sync.pending:
            raise CoreError('请先在设置中确认或取消全量同步')
        if self.col.undo_status().undo:
            self.col.undo()
        self._reset()
        return self.current(session)

    def select_deck(self, session, deck_id):
        self._check(session)
        if self.sync.pending:
            raise CoreError('请先在设置中确认或取消全量同步')
        if type(deck_id) is not int or not self.col.decks.get(deck_id, default=False):
            raise CoreError('牌组不存在')
        self.col.decks.select(deck_id)
        self.settings['deck_id'] = deck_id
        self._save_settings()
        self.notice = ''
        self._reset()
        return self.current(session)

    def import_package(self, session, filename):
        from anki.collection import ImportAnkiPackageOptions, ImportAnkiPackageRequest
        self._check(session)
        if self.sync.pending:
            raise CoreError('请先在设置中确认或取消全量同步')
        path = Path(filename).resolve()
        if path.suffix.lower() != '.apkg' or not path.is_file():
            raise CoreError('请选择 .apkg 牌组包；不直接打开外部牌库文件')
        self._backup(force=True)
        before = {deck.id for deck in self.col.decks.all_names_and_ids()}
        self._reset()
        try:
            self.col.import_anki_package(ImportAnkiPackageRequest(
                package_path=str(path), options=ImportAnkiPackageOptions(
                    with_scheduling=True, with_deck_configs=True, merge_notetypes=False)))
        finally:
            self._reset()
        decks = self.col.decks.all_names_and_ids(skip_empty_default=True)
        added = next((deck for deck in decks if deck.id not in before), None)
        if added:
            self.select_deck(session, int(added.id))
        elif decks and not self.col.decks.card_count(self.col.decks.get_current_id(), include_subdecks=True):
            self.select_deck(session, int(decks[0].id))
        self.notice = '牌组导入完成'
        return self.current(session)

    def export_package(self, session, filename):
        from anki.collection import ExportAnkiPackageOptions
        from anki.import_export_pb2 import ExportLimit
        self._check(session)
        path = Path(filename).resolve()
        if path.suffix.lower() != '.apkg':
            raise CoreError('导出文件必须使用 .apkg 扩展名')
        if path.exists():
            raise CoreError('目标文件已存在，请选择新文件名，避免覆盖')
        self.col.export_anki_package(out_path=str(path), options=ExportAnkiPackageOptions(
            with_scheduling=True, with_deck_configs=True, with_media=True),
            limit=ExportLimit(whole_collection=True))
        self.notice = '已导出全部牌组（含媒体和学习进度）'
        return self.current(session)

    def close(self):
        if self.col is not None:
            try:
                self._backup(force=False)
            finally:
                self.col.close()
                self.col = None
                self.session = None
                self._reset()
