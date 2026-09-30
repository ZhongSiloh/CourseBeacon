"""CourseBeacon: loopback-only dashboard and serial Playwright CLI worker."""
import argparse
import copy
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
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

from bridge import Bridge, ROOT, open_chrome

HOME = 'https://i.chaoxing.com/base?ws=3&vflag=true&fid=&backUrl='
DEFAULT_PORT = 17890


class LocalHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        if os.name == 'nt':
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def failure_kind(exc):
    text = str(exc).lower()
    if any(s in text for s in ('auth_required', '登录已失效', '登录失效', 'passport2')):
        return 'login'
    if any(s in text for s in ('browser_gone', 'not open', 'has been closed', 'browser closed',
                              'econnrefused', 'socket closed', 'connection closed')):
        return 'browser'
    if any(s in text for s in ('verification_required', '人脸', '验证码', '访问验证')):
        return 'verification'
    return 'transient'


class InstanceLock:
    def __init__(self, directory):
        self.path = Path(directory)/'instance.lock'
        self.handle = None

    def acquire(self):
        import msvcrt
        self.handle = self.path.open('a+b')
        self.handle.seek(0, 2)
        if not self.handle.tell():
            self.handle.write(b'0'); self.handle.flush()
        self.handle.seek(0)
        try:
            msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            self.handle.close(); self.handle = None
            return False

    def close(self):
        if self.handle:
            import msvcrt
            self.handle.seek(0)
            msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            self.handle.close(); self.handle = None


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
        self.wake.set()  # Exactly one initial scan; later scans require a button click.
        self.bridge = Bridge(directory, args.session)
        self.token = secrets.token_urlsafe(32)
        self.config_file = directory / 'config.json'
        old = self.store.load()
        for item in old.get('items', []):
            item['stale'] = True
        self.state = dict(status='starting', message='正在启动 Chrome…', courses=old.get('courses', []),
            ended=old.get('ended', 0), items=old.get('items', []), errors=[], total=0, completed=0,
            updatedAt=old.get('updatedAt'), stale=True, running=False, port=args.port,
            nextPort=args.port, mode='manual', needsBrowserSetup=False)
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
            if self.state['running'] or self.wake.is_set():
                return False
            self.wake.set()
            return True

    def run(self, dashboard):
        try:
            while True:
                self.wake.wait()  # No timer and no automatic retry after failure.
                if self.stop.is_set():
                    break
                with self.lock:
                    self.wake.clear()
                    self.state.update(running=True, completed=0, total=0)
                try:
                    if not self.bridge.connected:
                        self.set(status='connecting', message='正在连接本机 Chrome，请允许 Chrome 中的连接提示…')
                        try:
                            self.bridge.connect(HOME)
                            self.set(needsBrowserSetup=False)
                        except Exception:
                            try: self.bridge.close()
                            except Exception: pass
                            self.bridge.connected = False
                            self.set(needsBrowserSetup=True)
                            raise RuntimeError('未连接到本机 Chrome。请打开 chrome://inspect/#remote-debugging，允许远程调试和连接提示，然后点击“检查作业”重试。')
                    self.scan(True)
                except Exception as exc:
                    logging.exception('Scan interrupted')
                    kind = failure_kind(exc)
                    if kind == 'browser':
                        try: self.bridge.close()
                        except Exception: pass
                        self.bridge.connected = False
                    self.set(status='login' if kind == 'login' else 'error', message=str(exc),
                             stale=True, running=False)
                finally:
                    self.set(running=False)
        finally:
            try: self.bridge.close()
            except Exception: logging.exception('Browser detach failed')

    def scan(self, full):
        self.set(status='scanning', running=True, message='正在读取课程列表…', errors=[], completed=0)
        if full or not self.state['courses']:
            self.bridge.goto(HOME)
            deadline = time.monotonic() + 45
            login_deadline = time.monotonic() + 600
            while not self.stop.is_set():
                found = self.bridge.script('courses.js')
                if found.get('ready'):
                    break
                if found.get('login'):
                    self.set(status='login', message='请在本机 Chrome 的超星页登录；本次检查将在登录后继续。')
                    deadline = time.monotonic() + 45
                    if time.monotonic() > login_deadline:
                        raise RuntimeError('AUTH_REQUIRED: 登录等待超时，请登录后点击检查作业。')
                elif time.monotonic() > deadline:
                    raise RuntimeError('课程列表加载超时，请检查网络或页面提示后手动重试。')
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
        for item in items:
            item['stale'] = True
        self.set(items=copy.deepcopy(items), stale=bool(items))
        errors = []
        consecutive_failures = 0
        for index, course in enumerate(courses):
            if self.stop.is_set():
                return
            self.set(message=f'正在同步 {index+1}/{len(courses)} · {course["name"]}')
            try:
                payload = {'course': course, 'listUrl': self.list_urls.get(course['id'])}
                for attempt in range(2):
                    try:
                        result = self.bridge.script('assignments.js', payload, timeout=120)
                        break
                    except Exception as exc:
                        if failure_kind(exc) != 'transient' or attempt:
                            raise
                        if self.stop.wait(1.5): return
                        payload = {'course':course}  # One fresh navigation retry only.
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
                consecutive_failures = 0
            except Exception as exc:
                logging.warning('Course failed: %s: %s', course['name'], str(exc).split('Call log:')[0][:500])
                kind = failure_kind(exc)
                if kind in ('login', 'browser'):
                    self.set(items=copy.deepcopy(items), errors=errors + [{'course':course['name'], 'message':str(exc)}],
                             completed=index, stale=True)
                    self.persist()
                    raise RuntimeError(str(exc) + '；本轮已停止，剩余课程尚未检查。') from exc
                errors.append({'course':course['name'], 'message':str(exc)})
                consecutive_failures = consecutive_failures+1 if kind == 'transient' else 0
                for item in items:
                    if item.get('courseId') == course['id']:
                        item['stale'] = True
                if consecutive_failures >= 3:
                    self.set(items=copy.deepcopy(items), errors=errors, completed=index+1, stale=True)
                    self.persist()
                    raise RuntimeError('连续 3 门课程读取失败，本轮已停止；请检查网络后手动重试，剩余课程尚未检查。')
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
                return self.send(200, {'app':'CourseBeacon', 'version':'2.0.0'})
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
                accepted = app.refresh()
                return self.send(202 if accepted else 200, {'ok':True, 'queued':accepted})
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
    parser.add_argument('--data-dir',type=Path,help='缓存、配置和日志目录')
    parser.add_argument('--session',default='coursebeacon-'+secrets.token_hex(6),help=argparse.SUPPRESS)
    args = parser.parse_args()
    directory = (args.data_dir or Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'CourseBeacon').resolve()
    directory.mkdir(parents=True, exist_ok=True)
    if args.port is None:
        try:
            args.port = json.loads((directory/'config.json').read_text(encoding='utf-8'))['port']
        except (OSError, ValueError, KeyError):
            args.port = DEFAULT_PORT
    if type(args.port) is not int or not 1024 <= args.port <= 65535:
        parser.error('端口必须为 1024–65535')
    instance = InstanceLock(directory)
    if not instance.acquire():
        try:
            existing = int((directory/'running-port.txt').read_text())
        except (OSError, ValueError):
            existing = args.port
        open_chrome(f'http://127.0.0.1:{existing}')
        return 0
    (directory/'running-port.txt').write_text(str(args.port), encoding='utf-8')
    logging.basicConfig(handlers=[RotatingFileHandler(directory/'coursebeacon-v2.log',
        maxBytes=1024*1024, backupCount=3, encoding='utf-8')], level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s')
    app = Application(directory, args)
    try:
        server = LocalHTTPServer(('127.0.0.1', args.port), make_handler(app))
    except OSError:
        instance.close()
        import ctypes
        ctypes.windll.user32.MessageBoxW(None,
            f'端口 {args.port} 已被占用。\n请关闭已有 CourseBeacon，或使用 --port 其他端口。', 'CourseBeacon', 0x10)
        return 1
    worker = threading.Thread(target=app.run, args=(f'http://127.0.0.1:{args.port}',), daemon=True)
    open_chrome(f'http://127.0.0.1:{args.port}')
    worker.start()
    try:
        server.serve_forever(poll_interval=.25)
    except KeyboardInterrupt:
        app.stop.set()
        app.wake.set()
    finally:
        server.server_close()
        worker.join(timeout=195)
        instance.close()
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        logging.exception('Fatal')
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, str(exc), 'CourseBeacon 启动失败', 0x10)
        raise
