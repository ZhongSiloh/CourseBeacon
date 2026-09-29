import argparse
import json
from pathlib import Path
import tempfile
import threading
import unittest
import logging
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from app import Application, allowed_url, make_handler


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Application(Path(self.tmp.name), argparse.Namespace(
            port=17890,interval=60,session='test',attach=True,profile=None))

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
        with self.assertLogs(level=logging.ERROR):
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
