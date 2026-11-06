from contextlib import contextmanager
from dataclasses import replace
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import smtplib
import socketserver
import tempfile
from threading import Thread
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from clef_spam.config import Config, Policy
from clef_spam.delivery import forward, run, smtp_data
from clef_spam.errors import BackendUnavailable, ConfigError

MAIL=b'From: sender@example.org\r\nX-Clef-Action: junk\r\nSubject: test\r\n\r\nHello\r\n.line\r\n'
RESULT={'verdict':'ham','action':'observe','classification':{'spam_score':.02,'score_kind':'native_probability'},'backend':'test','elapsed_ms':1}
CONFIG=Config('spam?',('test',),{},Policy())

class LMTPHandler(socketserver.StreamRequestHandler):
    def handle(self):
        def reply(value):
            self.wfile.write(value+b'\r\n');self.wfile.flush()
        reply(b'220 fixture LMTP')
        while line:=self.rfile.readline():
            self.server.commands.append(line)
            if line.upper().startswith(b'LHLO '):
                reply(b'250-fixture');reply(b'250 8BITMIME')
            elif line.upper().startswith(b'MAIL FROM:'):
                reply(b'250 sender accepted')
            elif line.upper().startswith(b'RCPT TO:'):
                reply(str(self.server.rcpt_status).encode()+b' recipient status')
            elif line.upper().startswith(b'DATA'):
                reply(b'354 continue')
                data=[]
                while chunk:=self.rfile.readline():
                    if chunk==b'.\r\n':break
                    data.append(chunk[1:] if chunk.startswith(b'..') else chunk)
                self.server.messages.append(b''.join(data))
                if self.server.drop_final:return
                reply(str(self.server.final_status).encode()+b' delivery status')
            else:
                reply(b'500 unexpected command')

@contextmanager
def fixture():
    with tempfile.TemporaryDirectory() as root:
        path=str(Path(root)/'lmtp')
        server=socketserver.UnixStreamServer(path,LMTPHandler)
        server.commands=[];server.messages=[];server.final_status=250;server.rcpt_status=250;server.drop_final=False
        thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        try:yield path,server
        finally:server.shutdown();server.server_close();thread.join()

class DeliveryTests(unittest.TestCase):
    def args(self,path,**kw):
        values=dict(config='unused',sender='',recipient='bcc@example.org',lmtp_socket=path,
                    lmtp_timeout=2,max_delivery_bytes=1048576,failure_mode='deliver')
        values.update(kw);return SimpleNamespace(**values)

    def invoke(self,args,result=RESULT,config=CONFIG):
        with patch('clef_spam.delivery.load',return_value=config),patch('clef_spam.delivery.Classifier') as cls,patch('clef_spam.delivery.event') as log:
            if isinstance(result,Exception):cls.return_value.classify.side_effect=result
            else:cls.return_value.classify.return_value=result
            status=run(args,io.BytesIO(MAIL))
        return status,log

    def test_pipe_to_lmtp_preserves_null_sender_bcc_and_body(self):
        with fixture() as (path,server):
            status,log=self.invoke(self.args(path))
            self.assertEqual(status,os.EX_OK)
            self.assertEqual(len(server.messages),1)
            data=server.messages[0]
            self.assertIn(b'X-Clef-Action: observe\r\n',data)
            self.assertNotIn(b'X-Clef-Action: junk',data)
            self.assertTrue(data.endswith(b'Hello\r\n.line\r\n'))
            self.assertTrue(any(x.startswith(b'mail FROM:<>') for x in server.commands))
            self.assertTrue(any(b'bcc@example.org' in x for x in server.commands))
            self.assertEqual(log.call_args.args[0]['status'],'delivered')

    def test_inference_failure_delivers_unclassified_and_strips_spoofed_verdict(self):
        with fixture() as (path,server):
            status,_=self.invoke(self.args(path),BackendUnavailable('SECRET provider text'))
            self.assertEqual(status,os.EX_OK)
            self.assertIn(b'X-Clef-Verdict: unclassified',server.messages[0])
            self.assertNotIn(b'junk',server.messages[0])
            self.assertNotIn(b'SECRET',server.messages[0])

    def test_defer_policy_does_not_send_any_mail(self):
        with fixture() as (path,server):
            status,_=self.invoke(self.args(path,failure_mode='defer'),BackendUnavailable('offline'))
            self.assertEqual(status,os.EX_TEMPFAIL)
            self.assertFalse(server.messages)

    def test_config_errors_always_defer(self):
        with fixture() as (path,server):
            status,_=self.invoke(self.args(path),ConfigError('invalid config'))
            self.assertEqual(status,os.EX_TEMPFAIL)
            self.assertFalse(server.messages)

    def test_downstream_failure_never_returns_success(self):
        for code in (451,550):
            with self.subTest(code=code),fixture() as (path,server):
                server.final_status=code
                status,_=self.invoke(self.args(path))
                self.assertEqual(status,os.EX_TEMPFAIL)

    def test_lost_final_reply_is_deferred(self):
        with fixture() as (path,server):
            server.drop_final=True
            status,_=self.invoke(self.args(path))
            self.assertEqual(status,os.EX_TEMPFAIL)

    def test_rejected_recipient_does_not_send_data(self):
        with fixture() as (path,server):
            server.rcpt_status=550
            status,_=self.invoke(self.args(path))
            self.assertEqual(status,os.EX_TEMPFAIL)
            self.assertFalse(server.messages)

    def test_envelope_command_injection_is_rejected(self):
        status,_=self.invoke(self.args('/missing',recipient='x\r\nDATA'))
        self.assertEqual(status,os.EX_TEMPFAIL)

    def test_delivery_spool_limit_defers_without_dropping_mail(self):
        status,_=self.invoke(self.args('/missing',max_delivery_bytes=5))
        self.assertEqual(status,os.EX_TEMPFAIL)

    def test_large_messages_can_bypass_inference_and_stream_to_delivery(self):
        from clef_spam.errors import InputError
        with fixture() as (path,server):
            status,_=self.invoke(self.args(path),InputError('exceeds inference limit'))
            self.assertEqual(status,os.EX_OK)
            self.assertTrue(server.messages[0].endswith(b'Hello\r\n.line\r\n'))

    def test_dot_stuffing_and_newline_normalization_across_every_boundary(self):
        raw=b'a\r\n.b\n..c\r\n\r\nlast'
        expected=b'a\r\n..b\r\n...c\r\n\r\nlast\r\n.\r\n'
        for i in range(len(raw)+1):
            with self.subTest(i=i):
                self.assertEqual(b''.join(smtp_data([raw[:i],raw[i:]])),expected)

    def test_long_unbroken_lines_remain_bounded(self):
        chunks=list(smtp_data([b'x'*200000]))
        self.assertLessEqual(max(map(len,chunks)),65538)
        self.assertEqual(b''.join(chunks),b'x'*200000+b'\r\n.\r\n')

if __name__=='__main__':unittest.main()
