"""Headless tests for original-HTML transport, native state guards and read-only effects."""
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from anki_api import AnkiClient, AnkiError, display_card
from anki_effects import InstalledCardEffects


def state():
    return {'active': True, 'side': 'question', 'stateToken': 'native-token',
            'card': {'id': '1', 'templateIndex': 0, 'deck': {'name': 'Words'}},
            'rendered': {'questionHtml': '<style>.card{color:red}</style><h1>reflect</h1><script>test()</script>',
                         'answerHtml': '<details><summary>Meaning</summary>反射</details>', 'css': '.card{color:red}'},
            'answers': [{'rating': 'good', 'label': '\u20682d\u2069'}]}


class Tests(unittest.TestCase):
    def test_html_not_projected_or_duplicated(self):
        review = state()
        output = display_card(review, 8, 'dark')
        self.assertEqual(output['html'], review['rendered']['questionHtml'])
        self.assertEqual(output['classes'], 'card card1')
        self.assertEqual(output['buttons'], [['good', '2d']])
        self.assertNotIn('native-token', json.dumps(output))

    def test_exact_existing_css_and_zoom(self):
        review = state()
        css = 'body[class*="night"] font[color="navy"]{color:#9dc4ff!important}'
        output = display_card(review, 1, 'dark', {'css': css, 'zoom': 1.2})
        self.assertEqual(output['html'], review['rendered']['questionHtml'] + '\n<style>\n' + css + '\n</style>\n')
        self.assertEqual(output['zoom'], 1.2)
        self.assertEqual(review['rendered']['questionHtml'].count(css), 0)

    def test_effects_hot_reload_disabled_and_separate_zooms(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            dark, zoom = root/'anki_dark_card', root/'1923741581'
            dark.mkdir(); zoom.mkdir()
            (dark/'dark.css').write_text('body{color:red}', encoding='utf-8')
            (zoom/'config.json').write_text('{"review_zoom":1,"different_zoom_question_and_answer":true}')
            (zoom/'meta.json').write_text('{"config":{"question_zoom":1.1,"answer_zoom":1.3}}')
            effects = InstalledCardEffects(root)
            self.assertEqual(effects.values('question'), {'css': 'body{color:red}', 'zoom': 1.1})
            self.assertEqual(effects.values('answer')['zoom'], 1.3)
            (dark/'dark.css').write_text('body{color:blue}', encoding='utf-8')
            self.assertEqual(effects.values('answer')['css'], 'body{color:blue}')
            (dark/'meta.json').write_text('{"disabled":true}')
            (zoom/'meta.json').write_text('{"disabled":true}')
            self.assertEqual(effects.values('question'), {'css': '', 'zoom': 1})

    def test_local_key_autodiscovery_is_read_only(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            addon = root/'Anki2/addons21/2055492159'
            addon.mkdir(parents=True)
            meta = '{"config":{"apiKey":"local-secret","webBindPort":8766}}'
            (addon/'meta.json').write_text(meta)
            with patch.dict(os.environ, {'APPDATA': temp}):
                client = AnkiClient.from_file(root/'missing-config.json')
            self.assertEqual(client.key, 'local-secret')
            self.assertEqual(client.endpoint, 'http://127.0.0.1:8766/api/v1')
            self.assertEqual((addon/'meta.json').read_text(), meta)
            self.assertFalse((root/'missing-config.json').exists())

    def test_local_key_is_not_forwarded_to_remote_endpoint(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            addon = root/'Anki2/addons21/2055492159'
            addon.mkdir(parents=True)
            (addon/'meta.json').write_text('{"config":{"apiKey":"must-stay-local"}}')
            config = root/'settings.json'
            config.write_text('{"endpoint":"https://anki.example/api/v1"}')
            with patch.dict(os.environ, {'APPDATA': temp}):
                client = AnkiClient.from_file(config)
            self.assertEqual(client.key, '')

    def test_invalid_configuration_falls_back_without_crashing_calendar(self):
        with TemporaryDirectory() as temp:
            config = Path(temp)/'settings.json'
            config.write_text('["not a config object"]')
            with patch.dict(os.environ, {'APPDATA': temp}):
                client = AnkiClient.from_file(config)
            self.assertEqual(client.deck, '英语单词::大学四级英语单词')
            self.assertEqual(AnkiClient({'timeout': 'invalid'}).timeout, 2)

    def test_enter_uses_only_active_anki_collection(self):
        client = AnkiClient({'deck': 'Words'})
        responses = [{'session': 's'}, {'path': 'media'}, state()]
        with patch.object(client, 'call', side_effect=responses) as call:
            result = client.enter()
        self.assertEqual(result['session'], 's')
        self.assertEqual([c.args[0] for c in call.call_args_list], ['collection.get', 'media.getDirectory', 'reviewer.get'])
        self.assertEqual(call.call_args_list[-1].kwargs, {'session': 's'})

    def test_offline_enter_never_navigates_or_starts_process(self):
        client = AnkiClient()
        with patch.object(client, 'call', side_effect=ConnectionRefusedError) as call:
            with self.assertRaises(ConnectionRefusedError):
                client.enter()
        self.assertEqual(call.call_count, 1)
        self.assertEqual(call.call_args.args[0], 'collection.get')

    def test_answer_retains_session_and_native_token(self):
        client = AnkiClient()
        with patch.object(client, 'call', side_effect=[{}, state()]) as call:
            client.answer('s', 't', 'good')
        self.assertEqual(call.call_args_list[0].kwargs, {'session': 's', 'stateToken': 't', 'rating': 'good'})

    def test_lost_write_response_is_never_retried(self):
        client = AnkiClient()
        with patch.object(client, 'call', side_effect=TimeoutError) as call:
            with self.assertRaises(TimeoutError):
                client.answer('s', 't', 'good')
        self.assertEqual(call.call_count, 1)

    def test_native_completion_is_awaited(self):
        client = AnkiClient()
        with patch.object(client, 'request', side_effect=[{'operationId': 'op'}, {'state': 'running'},
                                                         {'state': 'succeeded', 'result': {'changed': True}}]) as request:
            with patch('anki_api.time.sleep'):
                result = client.call('application.navigate', view='review', deck={'name': 'Words'})
        self.assertEqual(result, {'changed': True})
        self.assertEqual(request.call_count, 3)

    def test_waiting_for_user_does_not_loop_forever(self):
        client = AnkiClient()
        with patch.object(client, 'request', side_effect=[{'operationId': 'op'}, {'state': 'waitingForUser'}]):
            with self.assertRaises(AnkiError):
                client.call('application.navigate')


if __name__ == '__main__':
    unittest.main()
