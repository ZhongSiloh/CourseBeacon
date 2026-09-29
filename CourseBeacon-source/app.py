"""CourseBeacon: loopback-only dashboard and serial Playwright CLI worker."""
import argparse
import copy
import hashlib
import json
import logging
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
import webbrowser
from contextlib import closing

from bridge import Bridge, ROOT

HOME = 'https://i.chaoxing.com/base?ws=3&vflag=true&fid=&backUrl='
DEFAULT_PORT = 17890


def allowed_url(url):
    try:
        u = urlparse(url)
        return u.scheme in ('https', 'http') and (u.hostname == 'chaoxing.com' or
            (u.hostname or '').endswith('.chaoxing.com')) and not u.username and not u.password
    except ValueError:
        return False


class Store:
    def __init__(self, directory):
        self.path = Path(directory) / 'coursebeacon.sqlite3'
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            db.commit()

    def load(self):
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute('SELECT value FROM cache WHERE key=?', ('snapshot',)).fetchone()
        return json.loads(row[0]) if row else {}

    def save(self, data):
        with closing(sqlite3.connect(self.path)) as db:
            with db:
                db.execute('INSERT OR REPLACE INTO cache VALUES (?,?)', ('snapshot', json.dumps(data, ensure_ascii=False)))


class Application:
    def __init__(self, directory, args):
        self.directory = directory
        self.args = args
        self.store = Store(directory)
        self.lock = threading.RLock()
        self.wake = threading.Event()
        self.stop = threading.Event()
        self.full_requested = True
        self.bridge = Bridge(directory, args.session)
        self.token = secrets.token_urlsafe(32)
        self.config_file = directory / 'config.json'
        old = self.store.load()
        for item in old.get('items', []):
            item['stale'] = True
        self.state = dict(status='starting', message='正在启动 Chrome…', courses=old.get('courses', []),
            ended=old.get('ended', 0), items=old.get('items', []), errors=[], total=0, completed=0,
            updatedAt=old.get('updatedAt'), stale=True, running=False, port=args.port,
            nextPort=args.port, interval=args.interval)
        self.list_urls = {}

    def set(self, **values):
        with self.lock:
            self.state.update(values)

    def snapshot(self):
        with self.lock:
            result = copy.deepcopy(self.state)
        result['serverTime'] = int(time.time()*1000)
        return result

    def persist(self):
        self.store.save(self.snapshot())

    def refresh(self):
        with self.lock:
            self.full_requested = True
        self.wake.set()

    def run(self, dashboard):
        try:
            if not self.args.attach:
                self.bridge.open(HOME, dashboard, self.args.profile or self.directory / 'chrome-profile')
            else:
                self.bridge.code('async page => { const p=await page.context().newPage(); await p.goto(' + json.dumps(dashboard) + '); return true; }')
        except Exception as exc:
            logging.exception('Browser launch failed')
            self.set(status='error', message='Chrome 启动失败：' + str(exc), running=False)
            webbrowser.open(dashboard)
            return
        while not self.stop.is_set():
            self.wake.clear()
            with self.lock:
                full = self.full_requested
                self.full_requested = False
            try:
                self.scan(full)
            except Exception as exc:
                logging.exception('Scan failed')
                self.set(status='error', message=str(exc), stale=True, running=False)
            # A manual refresh requested during a scan is never lost.
            if not self.stop.is_set():
                self.wake.wait(self.args.interval)
        if not self.args.attach:
            try:
                self.bridge.close()
            except Exception:
                logging.exception('Browser close failed')

    def scan(self, full):
        self.set(status='scanning', running=True, message='正在读取课程列表…', errors=[])
        if full or not self.state['courses']:
            self.bridge.goto(HOME)
            while not self.stop.is_set():
                found = self.bridge.script('courses.js')
                if found.get('ready'):
                    break
                self.set(status='login', message='请在 CourseBeacon 打开的 Chrome 中登录超星；登录后自动继续。')
                self.stop.wait(2)
            if self.stop.is_set():
                return
            if found.get('folders'):
                raise RuntimeError('检测到课程文件夹。请先将需要汇总的课程移到“我学的课”根列表后重试，以免漏报。')
            courses = found['courses']
            if not courses:
                raise RuntimeError('未读取到在读课程，请确认“我学的课”页面已加载。')
            self.list_urls.clear()
            self.set(courses=courses, ended=found['ended'])
        courses = self.snapshot()['courses']
        self.set(status='scanning', total=len(courses), completed=0)
        # Replace only successful course slices; a failed read never means zero homework.
        items = self.snapshot()['items']
        active_ids = {c['id'] for c in courses}
        items = [i for i in items if i.get('courseId') in active_ids]
        errors = []
        for index, course in enumerate(courses):
            if self.stop.is_set():
                return
            self.set(message=f'正在同步 {index+1}/{len(courses)} · {course["name"]}')
            try:
                payload = {'course': course, 'listUrl': self.list_urls.get(course['id'])}
                try:
                    result = self.bridge.script('assignments.js', payload, timeout=180)
                except Exception:
                    if not payload['listUrl']:
                        raise
                    # Signed URLs can expire. Re-enter through the course navigation.
                    result = self.bridge.script('assignments.js', {'course':course}, timeout=180)
                self.list_urls[course['id']] = result['listUrl']
                fresh = []
                for item in result['items']:
                    if not allowed_url(item['url']):
                        raise RuntimeError('作业链接不是超星地址')
                    identity = course['id'] + ':' + item['url'].split('&enc=')[0]
                    item.update(id=hashlib.sha256(identity.encode()).hexdigest()[:20],
                        courseId=course['id'], course=course['name'], stale=False)
                    fresh.append(item)
                items = [i for i in items if i.get('courseId') != course['id']] + fresh
            except Exception as exc:
                logging.exception('Course failed: %s', course['name'])
                errors.append({'course':course['name'], 'message':str(exc)})
                for item in items:
                    if item.get('courseId') == course['id']:
                        item['stale'] = True
            with self.lock:
                self.state.update(items=copy.deepcopy(items), errors=errors[:], completed=index+1)
        partial = bool(errors)
        self.set(status='partial' if partial else 'ready', running=False, stale=partial,
            updatedAt=int(time.time()*1000),
            message=f'已检查 {len(courses)-len(errors)}/{len(courses)} 门课程 · {len(items)} 项未完成作业'
                + (f' · {len(errors)} 门读取失败，请重试' if partial else ''))
        self.persist()


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def send(self, code, data, kind='application/json; charset=utf-8'):
            if not isinstance(data, bytes):
                data = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def valid_host(self):
            return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

        def do_GET(self):
            if not self.valid_host():
                return self.send(403, {'error':'Invalid host'})
            path = urlparse(self.path).path
            if path == '/api/state':
                return self.send(200, app.snapshot())
            if path == '/api/session':
                return self.send(200, {'token':app.token})
            if path == '/api/ping':
                return self.send(200, {'app':'CourseBeacon', 'version':'1.0.0'})
            allowed = {'/':('index.html','text/html; charset=utf-8'),
                '/app.js':('app.js','text/javascript; charset=utf-8'),
                '/style.css':('style.css','text/css; charset=utf-8'),
                '/icons-act.png':('icons-act.png','image/png'),
                '/endTime.png':('endTime.png','image/png')}
            if path in allowed:
                filename, mime = allowed[path]
                try:
                    return self.send(200, (ROOT/'static'/filename).read_bytes(), mime)
                except FileNotFoundError:
                    pass
            self.send(404, {'error':'Not found'})

        def do_POST(self):
            origin = f'http://127.0.0.1:{self.server.server_port}'
            if not self.valid_host() or self.headers.get('Origin') not in (None, origin) or self.headers.get('X-CourseBeacon-Token') != app.token:
                return self.send(403, {'error':'请在 CourseBeacon 本地页面操作'})
            try:
                length = int(self.headers.get('Content-Length','0'))
                if not 0 <= length <= 8192:
                    return self.send(413, {'error':'请求过大'})
                body = json.loads(self.rfile.read(length) or b'{}')
            except (ValueError, json.JSONDecodeError):
                return self.send(400, {'error':'请求格式错误'})
            if self.path == '/api/refresh':
                app.refresh()
                return self.send(202, {'ok':True})
            if self.path == '/api/settings':
                port = body.get('port')
                if type(port) is not int or not 1024 <= port <= 65535:
                    return self.send(400, {'error':'端口必须为 1024–65535 的整数'})
                app.config_file.write_text(json.dumps({'port':port}, indent=2), encoding='utf-8')
                app.set(nextPort=port)
                return self.send(200, {'ok':True})
            if self.path == '/api/stop':
                self.send(200, {'ok':True})
                app.stop.set()
                app.wake.set()
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            self.send(404, {'error':'Not found'})
    return Handler


def main():
    parser = argparse.ArgumentParser(description='CourseBeacon 本地未完成作业汇总')
    parser.add_argument('-p','--port',type=int,help='本地端口，默认 17890')
    parser.add_argument('--data-dir',type=Path,help='数据及独立 Chrome 配置目录')
    parser.add_argument('--profile',type=Path,help=argparse.SUPPRESS)
    parser.add_argument('--session',default='coursebeacon',help=argparse.SUPPRESS)
    parser.add_argument('--attach',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--interval',type=int,default=60,help='两次同步之间的间隔秒数，至少 30')
    args = parser.parse_args()
    if args.profile:
        args.profile = args.profile.resolve()
    if args.interval < 30:
        parser.error('同步间隔不能小于 30 秒')
    directory = (args.data_dir or Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'CourseBeacon').resolve()
    directory.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=directory/'coursebeacon.log', level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s', encoding='utf-8')
    if args.port is None:
        try:
            args.port = json.loads((directory/'config.json').read_text(encoding='utf-8'))['port']
        except (OSError, ValueError, KeyError):
            args.port = DEFAULT_PORT
    if type(args.port) is not int or not 1024 <= args.port <= 65535:
        parser.error('端口必须为 1024–65535')
    app = Application(directory, args)
    try:
        server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(app))
    except OSError:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None,
            f'端口 {args.port} 已被占用。\n请关闭已有 CourseBeacon，或使用 --port 其他端口。', 'CourseBeacon', 0x10)
        return 1
    worker = threading.Thread(target=app.run, args=(f'http://127.0.0.1:{args.port}',), daemon=True)
    worker.start()
    try:
        server.serve_forever(poll_interval=.25)
    except KeyboardInterrupt:
        app.stop.set()
        app.wake.set()
    finally:
        server.server_close()
        worker.join(timeout=195)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        logging.exception('Fatal')
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, str(exc), 'CourseBeacon 启动失败', 0x10)
        raise
