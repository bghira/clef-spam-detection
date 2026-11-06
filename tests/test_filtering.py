import unittest
from clef_spam.filtering import annotate
from clef_spam.errors import InputError

class FilteringTests(unittest.TestCase):
    result = {'verdict': 'spam', 'action': 'observe', 'classification': {
        'spam_score': 0.99, 'score_kind': 'native_probability'}}

    def test_strip_spoofed_headers_and_continuations_preserve_mime_bytes(self):
        body = b'--boundary\r\nencoded body =FF\r\n'
        headers = b'From: a@example.org\r\nX-Clef-Action: junk\r\n forged continuation\r\nSubject: original\r\n\tfolded subject\r\nDKIM-Signature: unchanged'
        out = annotate(headers+b'\r\n\r\n'+body, self.result)
        self.assertEqual(out.split(b'\r\n\r\n',1)[1], body)
        self.assertNotIn(b'forged continuation',out)
        self.assertNotIn(b'X-Clef-Action: junk',out)
        self.assertIn(b'X-Clef-Action: observe',out)
        self.assertIn(b'Subject: original\r\n\tfolded subject',out)
        self.assertIn(b'DKIM-Signature: unchanged',out)

    def test_unix_newlines_and_idempotence(self):
        raw=b'From: test@example.org\n\nbody\n'
        once=annotate(raw,self.result)
        self.assertEqual(annotate(once,self.result), once)

    def test_missing_separator_is_not_silently_rewritten(self):
        with self.assertRaises(InputError):
            annotate(b'not a complete message',self.result)

    def test_header_injection_is_rejected(self):
        with self.assertRaises(InputError):
            annotate(b'Subject: test\n\nbody',dict(self.result,action='junk\nInjected: yes'))
