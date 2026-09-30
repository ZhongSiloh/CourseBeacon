import argparse
import json
from pathlib import Path
import tempfile
import threading
import unittest
import logging
from unittest.mock import Mock
import time
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from app import Application, allowed_url, make_handler, failure_kind, InstanceLock, LocalHTTPServer


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Application(Path(self.tmp.name), argparse.Namespace(
            port=17890,session='test'))

    def tearDown(self):
        self.tmp.cleanup()

    def test_url_validation(self):
        self.assertTrue(allowed_url('https://mooc1.chaoxing.com/mooc-ans/work/task?id=1'))
        for u in ['javascript:alert(1)','https://chaoxing.com.evil.test/',
                  'https://evilchaoxing.com/','https://secret@chaoxing.com/']:
            self.assertFalse(allowed_url(u), u)

    def test_partial_failure_preserves_only_failed_course_cache(self):
        courses = [dict(id='a',name='A',url='https://mooc1.chaoxing.com/a'),
                   dict(id='b',name='B',url='https://mooc1.chaoxing.com/b')]
        self.app.set(courses=courses,items=[dict(courseId='a',title='old-a'),dict(courseId='b',title='old-b')])
        class Fake:
            def script(self,name,payload,**kw):
                if payload['course']['id']=='b': raise RuntimeError('离线')
                return {'items':[], 'listUrl':'https://mooc1.chaoxing.com/list'}
        self.app.bridge=Fake()
        with self.assertLogs(level=logging.WARNING):
            self.app.scan(False)
        s=self.app.snapshot()
        self.assertEqual(s['status'],'partial')
        self.assertEqual(s['completed'],2)
        self.assertEqual([x['title'] for x in s['items']],['old-b'])
        self.assertTrue(s['items'][0]['stale'])
        self.assertEqual(self.app.store.load()['items'],s['items'])

    def test_successful_refresh_removes_old_and_ended_course_items(self):
        self.app.set(items=[{'courseId':'ended','title':'do not retain'}])
        class Fake:
            def goto(self,url): pass
            def script(self,name,payload=None,**kw):
                if name=='courses.js':
                    return {'ready':True,'courses':[dict(id='a',name='A',url='https://mooc1.chaoxing.com/a')],'ended':1,'folders':0}
                return {'items':[dict(title='new',url='https://mooc1.chaoxing.com/task?workId=1')],
                        'listUrl':'https://mooc1.chaoxing.com/list'}
        self.app.bridge=Fake();self.app.scan(True)
        s=self.app.snapshot()
        self.assertEqual(s['status'],'ready');self.assertFalse(s['stale'])
        self.assertEqual([i['title'] for i in s['items']],['new'])
        self.assertEqual(s['ended'],1)

    def test_manual_schedule_and_duplicate_click(self):
        self.app.bridge=Mock(connected=True)
        completed=threading.Event()
        calls=[]
        def scan(full):
            calls.append(full)
            self.assertFalse(self.app.refresh())  # A busy click cannot queue another scan.
            completed.set()
        self.app.scan=scan
        worker=threading.Thread(target=self.app.run,args=('http://127.0.0.1',))
        worker.start()
        try:
            self.assertTrue(completed.wait(2))
            time.sleep(.15)
            self.assertEqual(len(calls),1)
            completed.clear()
            self.assertTrue(self.app.refresh())
            self.assertTrue(completed.wait(2))
            time.sleep(.15)
            self.assertEqual(len(calls),2)
        finally:
            self.app.stop.set();self.app.wake.set();worker.join(2)
        self.assertFalse(worker.is_alive())

    def test_login_failure_stops_round_without_retrying_other_courses(self):
        self.app.set(courses=[dict(id='a',name='A'),dict(id='b',name='B')])
        self.app.bridge=Mock()
        self.app.bridge.script.side_effect=RuntimeError('AUTH_REQUIRED: 登录已失效')
        with self.assertLogs(level=logging.WARNING):
            with self.assertRaisesRegex(RuntimeError,'剩余课程尚未检查'):
                self.app.scan(False)
        self.assertEqual(self.app.bridge.script.call_count,1)
        self.assertEqual(self.app.snapshot()['completed'],0)

    def test_transient_failure_retries_once(self):
        self.app.set(courses=[dict(id='a',name='A')])
        self.app.bridge=Mock()
        self.app.bridge.script.side_effect=[RuntimeError('navigation timeout'), {'items':[],'listUrl':'https://mooc1.chaoxing.com/list'}]
        self.app.scan(False)
        self.assertEqual(self.app.bridge.script.call_count,2)
        self.assertEqual(self.app.snapshot()['status'],'ready')

    def test_permanent_verification_is_not_retried(self):
        self.app.set(courses=[dict(id='a',name='A')])
        self.app.bridge=Mock()
        self.app.bridge.script.side_effect=RuntimeError('VERIFICATION_REQUIRED: 人脸信息采集')
        with self.assertLogs(level=logging.WARNING):self.app.scan(False)
        self.assertEqual(self.app.bridge.script.call_count,1)
        self.assertEqual(self.app.snapshot()['status'],'partial')

    def test_windows_single_instance(self):
        import os
        if os.name!='nt':self.skipTest('Windows only')
        first=InstanceLock(self.tmp.name);second=InstanceLock(self.tmp.name)
        try:
            self.assertTrue(first.acquire());self.assertFalse(second.acquire())
            first.close();self.assertTrue(second.acquire())
        finally:first.close();second.close()

    def test_local_server_rejects_second_bind(self):
        server=LocalHTTPServer(('127.0.0.1',0),make_handler(self.app))
        try:
            with self.assertRaises(OSError):
                duplicate=ThreadingHTTPServer(('127.0.0.1',server.server_port),make_handler(self.app))
                duplicate.server_close()
        finally:server.server_close()

    def test_bridge_detaches_instead_of_closing_user_browser(self):
        bridge=self.app.bridge
        bridge.command=Mock();bridge.code=Mock();bridge.connected=True;bridge.scanner_id='owned'
        bridge.close()
        bridge.command.assert_called_once_with('detach',timeout=15)
        self.assertFalse(bridge.connected)

    def test_connection_failure_allows_manual_retry(self):
        self.app.bridge=Mock(connected=False)
        self.app.bridge.connect.side_effect=RuntimeError('permission denied')
        worker=threading.Thread(target=self.app.run,args=('http://127.0.0.1',))
        with self.assertLogs(level=logging.ERROR):
            worker.start()
            for _ in range(100):
                if self.app.snapshot()['status']=='error':break
                time.sleep(.01)
            self.app.stop.set();self.app.wake.set();worker.join(2)
        self.assertFalse(self.app.snapshot()['running'])
        self.assertTrue(self.app.snapshot()['needsBrowserSetup'])
        self.assertEqual(self.app.bridge.connect.call_count,1)

    def test_http_rejects_unauthorized_mutation_and_host(self):
        server=ThreadingHTTPServer(('127.0.0.1',0), make_handler(self.app))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            def post(headers,body=b'{}'):
                return urlopen(Request(base+'/api/settings',data=body,headers=headers),timeout=3)
            with self.assertRaises(HTTPError) as e: post({})
            self.assertEqual(e.exception.code,403)
            token={'X-CourseBeacon-Token':self.app.token}
            with self.assertRaises(HTTPError) as e: post({**token,'Origin':'https://evil.test'})
            self.assertEqual(e.exception.code,403)
            with self.assertRaises(HTTPError) as e: post(token,b'{"port":80}')
            self.assertEqual(e.exception.code,400)
            with post(token,b'{"port":19000}') as r:self.assertEqual(r.status,200)
            self.assertEqual(json.loads(self.app.config_file.read_text())['port'],19000)
            with self.assertRaises(HTTPError) as e:
                urlopen(Request(base+'/api/state',headers={'Host':'evil.test'}),timeout=3)
            self.assertEqual(e.exception.code,403)
        finally:
            server.shutdown();server.server_close();thread.join()


if __name__=='__main__': unittest.main()
