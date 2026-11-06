import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from clef_spam.credentials import api_key, parse_env, read_env_file, MAX_ENV_BYTES
from clef_spam.errors import AuthenticationError, ConfigError
from clef_spam.backends.remote import SystemOne, WorkersAI, OpenAICompatible
from clef_spam.contracts import ClassificationRequest
from clef_spam.cli import main

class CredentialTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)/'credentials.env'

    def write(self, value, mode=0o600):
        self.path.write_text(value)
        self.path.chmod(mode)
        return str(self.path)

    def test_literal_assignments_comments_quotes_export(self):
        data = parse_env('''# comment
export TOKEN = "test-secret" # comment
OTHER='abc=def#suffix'
EMPTY=
COMMENT= # comment
''')
        self.assertEqual(data, {'TOKEN':'test-secret','OTHER':'abc=def#suffix','EMPTY':'','COMMENT':''})

    def test_file_is_authoritative_and_does_not_mutate_environment(self):
        path = self.write('TOKEN=file-secret\nOTHER=other-value\n')
        with patch.dict(os.environ,TOKEN='ambient-secret'):
            self.assertEqual(api_key('TOKEN', path),'file-secret')
            self.assertEqual(os.environ['TOKEN'],'ambient-secret')
        self.write('OTHER=other-value\n')
        with patch.dict(os.environ,TOKEN='ambient-secret'),self.assertRaises(AuthenticationError):
            api_key('TOKEN',path)

    def test_existing_process_environment_is_still_supported(self):
        with patch.dict(os.environ,TOKEN='environment-secret'):
            self.assertEqual(api_key('TOKEN'),'environment-secret')

    def test_rotation_is_seen_on_the_next_request(self):
        path = self.write('TOKEN=first\n')
        self.assertEqual(api_key('TOKEN',path),'first')
        self.write('TOKEN=second\n')
        self.assertEqual(api_key('TOKEN',path),'second')

    def test_group_read_allowed_but_public_access_and_group_write_rejected(self):
        path = self.write('TOKEN=test-secret\n',0o640)
        self.assertEqual(api_key('TOKEN',path),'test-secret')
        for mode in (0o644,0o660,0o606):
            self.path.chmod(mode)
            with self.subTest(mode=mode),self.assertRaises(AuthenticationError):
                api_key('TOKEN',path)

    def test_missing_symlink_special_file_and_size_bounds(self):
        with self.assertRaises(AuthenticationError):
            read_env_file(str(self.path))
        target = Path(self.directory.name)/'target'
        target.write_text('TOKEN=secret')
        self.path.symlink_to(target)
        with self.assertRaises(AuthenticationError):
            read_env_file(str(self.path))
        self.path.unlink()
        os.mkfifo(self.path,0o600)
        with self.assertRaises(AuthenticationError):
            read_env_file(str(self.path))
        self.path.unlink()
        with self.assertRaises(AuthenticationError):
            read_env_file(self.write('TOKEN='+'a'*MAX_ENV_BYTES))

    def test_unsafe_owner_is_rejected_before_read(self):
        path = self.write('TOKEN=test-secret')
        info = os.stat(path)
        from types import SimpleNamespace
        fake = SimpleNamespace(st_mode=info.st_mode,st_uid=987654,st_size=info.st_size)
        with patch('clef_spam.credentials.os.fstat',return_value=fake),self.assertRaises(AuthenticationError):
            read_env_file(path)

    def test_unsafe_syntax_cannot_execute_or_disclose_values(self):
        marker = Path(self.directory.name)/'executed'
        for contents in ('TOKEN=first-secret\nTOKEN=second-secret', 'bad-variable=secret',
                         'TOKEN="unterminated-secret', 'TOKEN=two secret words',
                         'TOKEN=${OTHER}', f'TOKEN=$(touch {marker})',f'TOKEN=`touch {marker}`'):
            with self.subTest(contents=contents),self.assertRaises(AuthenticationError) as cm:
                parse_env(contents)
            self.assertNotIn('secret',str(cm.exception))
        self.assertFalse(marker.exists())

    def test_empty_and_whitespace_keys_are_rejected(self):
        for value in ("TOKEN=", "TOKEN='test secret'", "TOKEN='test\tsecret'"):
            with self.subTest(value=value),self.assertRaises(AuthenticationError):
                api_key('TOKEN',self.write(value))

    def test_all_remote_backends_accept_file_option_without_reading_at_init(self):
        opts = {'model':'clef','api_key_env':'TOKEN','api_key_env_file':str(self.path)}
        for cls in (SystemOne,OpenAICompatible,WorkersAI):
            config = dict(opts,account_id='example') if cls is WorkersAI else dict(opts,endpoint='http://localhost/api')
            with patch('clef_spam.credentials.read_env_file',side_effect=AssertionError('must not read')):
                backend=cls(config)
            with patch('clef_spam.backends.remote.post',side_effect=AuthenticationError('test')) as post:
                with self.assertRaises(AuthenticationError):
                    backend.classify(ClassificationRequest('mail','spam?'))
            self.assertEqual(post.call_args.kwargs['key_env_file'],str(self.path))

    def test_file_option_requires_named_variable_and_absolute_path(self):
        for opts in ({'api_key_env_file':str(self.path)},
                     {'api_key_env_file':'relative.env','api_key_env':'TOKEN'},
                     {'api_key_env':'not-a-variable'}):
            with self.subTest(opts=opts),self.assertRaises(ConfigError):
                SystemOne(dict(opts,model='clef',endpoint='http://localhost/api'))

    def test_cli_validation_does_not_open_credentials(self):
        config=Path(self.directory.name)/'config.json'
        config.write_text(json.dumps({'schema_version':1,'backend_order':['a'],
            'backends':{'a':{'type':'systemone','disabled':False,'options':{
                'model':'clef','endpoint':'http://localhost/api','api_key_env':'TOKEN',
                'api_key_env_file':str(self.path)}}}}))
        with patch('clef_spam.credentials.read_env_file',side_effect=AssertionError('must not read')):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['--config',str(config),'validate']),0)

if __name__ == '__main__':
    unittest.main()
