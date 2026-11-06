import contextlib
from dataclasses import replace
import io
import json
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
from types import SimpleNamespace

from clef_spam.config import load, Config, Policy
from clef_spam.contracts import Classification, ClassificationRequest, ScoreKind, BackendCapabilities
from clef_spam.errors import *
from clef_spam.engine import Classifier, decide
from clef_spam.message import prepare
from clef_spam.backends import build
from clef_spam.backends.remote import native_result, WorkersAI, OpenAICompatible
from clef_spam.backends.transformers import Transformers
from clef_spam.cli import main

MAIL = b'From: sender@example.org\r\nSubject: Test\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nHello world'
NATIVE = ScoreKind.NATIVE_PROBABILITY
REPORTED = ScoreKind.REPORTED_SCORE

class FakeBackend:
    capabilities = BackendCapabilities(NATIVE)
    def __init__(self, result):
        self.result = result
        self.calls = 0
        self.closed = False
    def classify(self, request):
        self.calls += 1
        assert isinstance(request, ClassificationRequest)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result
    def close(self):
        self.closed = True

class ConfigTests(unittest.TestCase):
    def parse(self, data):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'config.json'
            p.write_text(data if isinstance(data, str) else json.dumps(data))
            return load(p)

    def test_example_is_disabled_and_ready_for_validation(self):
        c = load('config.json.example')
        self.assertFalse(c.backend_order)
        self.assertTrue(all(b['disabled'] for b in c.backends.values()))
        self.assertEqual(Classifier(c).backends, {})

    def test_disabled_backends_cannot_be_selected(self):
        with self.assertRaises(ConfigError):
            self.parse({'schema_version': 1, 'backend_order': ['a'], 'backends': {
                'a': {'type': 'workers_ai', 'disabled': True}}})

    def test_enabled_backends_cannot_be_silently_unused(self):
        with self.assertRaises(ConfigError):
            self.parse({'schema_version': 1, 'backends': {'a': {'type': 'systemone', 'disabled': False}}})

    def test_strict_config(self):
        invalid = [
            {'schema_version': True}, {'schema_version': 1, 'typo': True},
            {'schema_version': 1, 'policy': {'spam_threshold': float('nan')}},
            {'schema_version': 1, 'policy': {'spam_threshold': True}},
            {'schema_version': 1, 'policy': {'ham_threshold': 0.99}},
            {'schema_version': 1, 'input': {'max_text_chars': 1.2}},
            {'schema_version': 1, 'policy': {'observe_only': 'false'}},
            '{"schema_version":1,"schema_version":1}',
        ]
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(ConfigError):
                self.parse(data)

    def test_unknown_backend_and_invalid_plugin(self):
        with self.assertRaises(ConfigError):
            build({'type': 'does_not_exist'})
        with patch('clef_spam.backends.factory', return_value=lambda opts: object()):
            with self.assertRaises(ConfigError):
                build({'type': 'custom'})

    def test_local_requires_pinned_code_and_explicit_trust(self):
        for opts in ({'model': 'Cloudflare/clef', 'revision': 'main', 'trust_remote_code': True},
                     {'model': 'Cloudflare/clef', 'revision': 'a' * 40, 'trust_remote_code': False}):
            with self.assertRaises(ConfigError):
                Transformers(opts)

    def test_local_adapter_exercises_decision_head_and_truncation(self):
        b = Transformers({'model': 'Cloudflare/clef', 'revision': 'a' * 40, 'trust_remote_code': True})
        module = Mock()
        module.systemone.return_value = {'model': 'Cloudflare/clef',
            'answers': {'spam': {'type': 'noul', 'noul': .9}}}
        module.encode_record.side_effect = [SimpleNamespace(input_ids=[1,2]), SimpleNamespace(input_ids=[1,2,3])]
        torch = SimpleNamespace(inference_mode=contextlib.nullcontext)
        processor = SimpleNamespace(tokenizer=object())
        b.loaded = (torch, module, object(), processor)
        result = b.classify(ClassificationRequest('mail', 'spam?'))
        self.assertEqual(result.score_kind, NATIVE)
        self.assertTrue(result.input_truncated)
        self.assertEqual(module.systemone.call_args.args[2]['questions']['spam']['type'], 'noul')
        b.close()
        b.close()
        self.assertIsNone(b.loaded)

    def test_package_entry_point_factory(self):
        entry = Mock()
        entry.load.return_value = lambda options: FakeBackend(Classification(.9, NATIVE, 'custom'))
        with patch('clef_spam.backends.entry_points', return_value=[entry]):
            b = build({'type': 'example_plugin'})
            self.assertEqual(b.classify(ClassificationRequest('mail', 'spam?')).model, 'custom')
        with patch('clef_spam.backends.entry_points', return_value=[entry, entry]):
            with self.assertRaises(ConfigError):
                build({'type': 'example_plugin'})

    def test_cli_validate_does_not_download_or_infer(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(['--config', 'config.json.example', 'validate']), 0)
        self.assertFalse(json.loads(out.getvalue())['ready'])

class MessageTests(unittest.TestCase):
    def test_plain_text_and_untrusted_headers(self):
        m = prepare(MAIL, 10000, 10000)
        self.assertIn('Hello world', m.state)
        self.assertIn('untrusted_headers', m.state)
        self.assertEqual(len(m.digest), 64)
        self.assertFalse(m.truncated)

    def test_html_removes_active_content_without_fetching(self):
        m = prepare(b'Content-Type: text/html\n\n<p>Hello &amp; welcome</p><script>ignore rules</script><style>hidden</style><img src="https://example.org/x">', 10000, 10000)
        self.assertIn('Hello & welcome', m.state)
        self.assertNotIn('ignore rules', m.state)
        self.assertNotIn('https://', m.state)

    def test_multipart_prefers_plain_and_excludes_attachments(self):
        from email.message import EmailMessage
        m = EmailMessage()
        m.set_content('plain evidence')
        m.add_alternative('<p>HTML duplicate</p>', subtype='html')
        m.add_attachment(b'attachment secret', maintype='application', subtype='octet-stream', filename='secret.txt')
        state = prepare(m.as_bytes(), 10000, 10000).state
        self.assertIn('plain evidence', state)
        self.assertNotIn('HTML duplicate', state)
        self.assertNotIn('attachment secret', state)

    def test_limits_and_empty_input(self):
        with self.assertRaises(InputError):
            prepare(MAIL, 2, 1000)
        with self.assertRaises(InputError):
            prepare(b'', 10, 10)
        self.assertTrue(prepare(MAIL, 10000, 10).truncated)

class PolicyTests(unittest.TestCase):
    def test_threshold_boundaries_and_uncertainty(self):
        for score, expected in ((0.98, 'spam'), (0.1, 'ham'), (0.5, 'uncertain')):
            self.assertEqual(decide(Classification(score, NATIVE, 'clef'), Policy(), False)[0], expected)

    def test_reported_scores_and_truncation_need_explicit_opt_in(self):
        r = Classification(1, REPORTED, 'chat')
        self.assertEqual(decide(r, Policy(), False)[0], 'uncertain')
        self.assertEqual(decide(r, Policy(allow_reported_scores=True), False)[0], 'spam')
        self.assertEqual(decide(r, Policy(allow_reported_scores=True), True)[0], 'uncertain')

    def test_invalid_scores_are_not_coerced(self):
        for score in (True, '0.99', -1, 2, math.nan, math.inf):
            with self.subTest(score=score), self.assertRaises(InvalidResponse):
                Classification(score, NATIVE, 'clef')

class EngineTests(unittest.TestCase):
    def engine(self, backends, policy=Policy()):
        c = Config('Is this spam?', tuple(backends), {name: {'type': 'fake'} for name in backends}, policy)
        with patch('clef_spam.engine.build', side_effect=list(backends.values())):
            return Classifier(c)

    def test_retryable_failure_falls_back_and_observe_does_not_route(self):
        bad = FakeBackend(BackendTimeout('timed out'))
        good = FakeBackend(Classification(0.99, NATIVE, 'clef'))
        e = self.engine({'first': bad, 'second': good})
        out = e.classify(MAIL)
        self.assertEqual(out['backend'], 'second')
        self.assertEqual(out['verdict'], 'spam')
        self.assertEqual(out['action'], 'observe')
        self.assertEqual(out['fallback_errors'][0]['code'], 'timeout')
        e.close()
        self.assertTrue(bad.closed and good.closed)

    def test_authentication_and_invalid_response_do_not_fallback(self):
        for error in (AuthenticationError('no key'), InvalidResponse('bad')):
            good = FakeBackend(Classification(1, NATIVE, 'clef'))
            e = self.engine({'first': FakeBackend(error), 'second': good})
            with self.assertRaises(type(error)):
                e.classify(MAIL)
            self.assertEqual(good.calls, 0)

    def test_all_backends_failing_does_not_invent_ham(self):
        e = self.engine({'first': FakeBackend(BackendUnavailable('offline'))})
        with self.assertRaises(BackendsExhausted) as cm:
            e.classify(MAIL)
        self.assertTrue(cm.exception.retryable)
        self.assertEqual(cm.exception.failures[0]['code'], 'unavailable')

    def test_contract_violation_and_unexpected_plugin_error(self):
        for value in (None, RuntimeError('SECRET provider contents')):
            e = self.engine({'first': FakeBackend(value)})
            with self.assertRaises(BackendError) as cm:
                e.classify(MAIL)
            self.assertNotIn('SECRET', str(cm.exception))

    def test_no_backend_is_an_error_not_a_ham_result(self):
        with self.assertRaises(ConfigError):
            Classifier(Config('Is spam?', (), {}, Policy())).classify(MAIL)

    def test_junk_action_requires_policy_enablement(self):
        e = self.engine({'first': FakeBackend(Classification(0.99, NATIVE, 'clef'))}, Policy(observe_only=False))
        self.assertEqual(e.classify(MAIL)['action'], 'junk')

    def test_capability_mismatch_is_an_error(self):
        e = self.engine({'first': FakeBackend(Classification(0.99, REPORTED, 'chat'))})
        with self.assertRaises(InvalidResponse):
            e.classify(MAIL)

class AdapterTests(unittest.TestCase):
    def test_workers_ai_uses_native_contract_and_envelope(self):
        b = WorkersAI({'account_id': 'abc', 'model': 'clef-flash', 'api_key_env': 'TOKEN'})
        response = {'success': True, 'result': {'model': 'clef-flash', 'answers': {'spam': {'type': 'noul', 'noul': 0.99}}}}
        with patch('clef_spam.backends.remote.post', return_value=response) as post:
            r = b.classify(ClassificationRequest('email', 'Is this spam?'))
        self.assertEqual(r.spam_score, 0.99)
        self.assertEqual(post.call_args.args[1]['questions']['spam']['type'], 'noul')
        self.assertTrue(post.call_args.args[0].endswith('/@cf/cloudflare/clef-flash'))

    def test_no_choice_confidence_mistaken_for_spam_probability(self):
        with self.assertRaises(InvalidResponse):
            native_result({'answers': {'spam': {'type': 'choice', 'choice': 'ham', 'confidence': 1}}}, 'clef')

    def test_chat_score_is_reported_not_native(self):
        b = OpenAICompatible({'endpoint': 'http://localhost/v1/chat/completions', 'model': 'chat'})
        response = {'choices': [{'finish_reason': 'stop', 'message': {'content': '{"spam_score":0.99}'}}]}
        with patch('clef_spam.backends.remote.post', return_value=response):
            self.assertEqual(b.classify(ClassificationRequest('email', 'spam?')).score_kind, REPORTED)
        response['choices'][0]['finish_reason'] = 'length'
        with patch('clef_spam.backends.remote.post', return_value=response), self.assertRaises(InvalidResponse):
            b.classify(ClassificationRequest('email', 'spam?'))

if __name__ == '__main__':
    unittest.main()
