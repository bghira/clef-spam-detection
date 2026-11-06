from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Thread
import time
import unittest
from unittest.mock import patch

from clef_spam.backends.http import post, endpoint, MAX_RESPONSE
from clef_spam.errors import *

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def do_POST(self):
        self.server.seen.append((self.path, self.headers.get('Authorization'), json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
        status = int(self.path[1:]) if self.path[1:].isdigit() else 200
        if self.path == '/slow':
            time.sleep(0.2)
        self.send_response(status)
        if status == 302:
            self.send_header('Location', '/redirect-target')
        self.end_headers()
        body = {'/native': json.dumps({'model': 'clef', 'answers': {'spam': {'type': 'noul', 'noul': 0.99}}}).encode(), '/ok': b'{"ok":true}', '/invalid': b'not json', '/array': b'[]', '/big': b' ' * (MAX_RESPONSE + 1)}.get(self.path, b'{"error":"SECRET"}')
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.server.seen = []
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = 'http://127.0.0.1:' + str(cls.server.server_port)
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_actual_http_json_and_bearer(self):
        with patch.dict(os.environ, TOKEN='test-secret'):
            self.assertEqual(post(self.url+'/ok', {'hello':'world'}, 'TOKEN', 1), {'ok':True})
        self.assertEqual(self.server.seen[-1][1:], ('Bearer test-secret', {'hello':'world'}))

    def test_error_taxonomy_and_no_error_body_leak(self):
        for status, expected in ((401,AuthenticationError),(403,AuthenticationError),(429,RateLimitError),(503,BackendUnavailable),(404,UnsupportedCapability),(400,InvalidResponse)):
            with self.subTest(status=status), self.assertRaises(expected) as cm:
                post(self.url+'/'+str(status), {}, None, 1)
            self.assertNotIn('SECRET', str(cm.exception))

    def test_timeout(self):
        with self.assertRaises(BackendTimeout):
            post(self.url+'/slow', {}, None, 0.05)

    def test_redirects_are_not_followed(self):
        before=len(self.server.seen)
        with self.assertRaises(InvalidResponse):
            post(self.url+'/302', {}, None, 1)
        self.assertEqual(len(self.server.seen),before+1)

    def test_bounded_response_and_invalid_json(self):
        for path in ('/big','/invalid','/array'):
            with self.subTest(path=path), self.assertRaises(InvalidResponse):
                post(self.url+path, {}, None, 1)

    def test_secrets_required_before_network(self):
        before=len(self.server.seen)
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(AuthenticationError):
            post(self.url+'/ok', {}, 'MISSING', 1)
        with patch.dict(os.environ, TOKEN='bad\nheader'), self.assertRaises(AuthenticationError):
            post(self.url+'/ok', {}, 'TOKEN', 1)
        self.assertEqual(len(self.server.seen),before)

    def test_cli_pipeline_with_real_local_http(self):
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            config = d/'config.json'
            config.write_text(json.dumps({
                'schema_version': 1, 'backend_order': ['local'],
                'backends': {'local': {'type': 'systemone', 'disabled': False,
                    'options': {'model': 'clef', 'endpoint': self.url+'/native'}}},
                'policy': {'observe_only': False}
            }))
            raw = b'Subject: test\r\nX-Clef-Action: forged\r\n\r\noriginal body\r\n'
            base = [sys.executable, '-m', 'clef_spam', '--config', str(config)]
            classified = subprocess.run(base+['classify'], input=raw, capture_output=True, check=True)
            result = json.loads(classified.stdout)
            self.assertEqual(result['action'], 'junk')
            self.assertEqual(result['classification']['spam_score'], .99)
            filtered = subprocess.run(base+['filter'], input=raw, capture_output=True, check=True)
            self.assertIn(b'X-Clef-Action: junk\r\n', filtered.stdout)
            self.assertNotIn(b'forged', filtered.stdout)
            self.assertTrue(filtered.stdout.endswith(b'\r\n\r\noriginal body\r\n'))
            self.assertEqual(filtered.stderr,b'')

    def test_cli_error_has_no_email_output_or_provider_body(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)/'config.json'
            config.write_text(json.dumps({'schema_version':1,'backend_order':['a'],
                'backends':{'a':{'type':'systemone','disabled':False,
                    'options':{'model':'clef','endpoint':self.url+'/401'}}}}))
            result = subprocess.run([sys.executable,'-m','clef_spam','--config',str(config),'filter'],
                input=b'Subject: test\n\nprivate body',capture_output=True)
            self.assertEqual(result.returncode,1)
            self.assertEqual(result.stdout,b'')
            self.assertEqual(json.loads(result.stderr)['error']['code'],'authentication')
            self.assertNotIn(b'SECRET',result.stderr)
            self.assertNotIn(b'private body',result.stderr)

    def test_endpoint_validation(self):
        for value in ('http://example.org/api','https://token@example.org/api','ftp://example.org','https://example.org/?key=secret','https://example.org:bad/','https://example.org/\ninjected'):
            with self.subTest(value=value), self.assertRaises(ConfigError):
                endpoint(value)
        self.assertEqual(endpoint(self.url+'/ok'), self.url+'/ok')

if __name__ == '__main__':
    unittest.main()
