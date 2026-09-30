"""Python -> bundled Node -> official playwright-cli (no shell interpolation)."""
from pathlib import Path
import json
import os
import subprocess
import sys
import threading
import uuid
import re
import shutil

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))


class BrowserError(RuntimeError):
    pass


def open_chrome(url):
    candidates = [shutil.which('chrome'),
        str(Path(os.environ.get('PROGRAMFILES', 'C:/Program Files'))/'Google/Chrome/Application/chrome.exe'),
        str(Path(os.environ.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)'))/'Google/Chrome/Application/chrome.exe'),
        str(Path(os.environ.get('LOCALAPPDATA', ''))/'Google/Chrome/Application/chrome.exe')]
    chrome = next((p for p in candidates if p and Path(p).is_file()), None)
    if not chrome:
        raise BrowserError('未找到本机 Google Chrome，请先安装 Chrome。')
    # No user-data-dir or profile switches: use the user's ordinary Chrome.
    subprocess.Popen([chrome, url], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


class Bridge:
    def __init__(self, data_dir, session='coursebeacon'):
        self.data_dir = Path(data_dir)
        self.session = session
        self.session_prefix = session
        runtime = ROOT / 'runtime'
        self.node = Path(os.environ.get('COURSEBEACON_NODE', str(runtime / 'node.exe')))
        self.cli = Path(os.environ.get('COURSEBEACON_CLI', str(runtime / 'cli' / 'playwright-cli.js')))
        self.lock = threading.Lock()
        self.scanner_id = None
        self.connected = False
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.environment = os.environ.copy()
        self.environment['PLAYWRIGHT_DAEMON_SESSION_DIR'] = str(self.data_dir / 'cli-sessions')

    def command(self, *args, timeout=120):
        if not self.node.is_file() or not self.cli.is_file():
            raise BrowserError('未找到内置 Node / playwright-cli。源码运行前请执行 build.py --prepare。')
        with self.lock:
            try:
                p = subprocess.run([str(self.node), str(self.cli), '-s=' + self.session, *args, '--raw'],
                    cwd=self.data_dir, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, encoding='utf-8', errors='replace', timeout=timeout,
                    env=self.environment,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            except subprocess.TimeoutExpired as exc:
                raise BrowserError('浏览器操作超时，请检查网络后重试。') from exc
        text = p.stdout.strip()
        if p.returncode or text.startswith('### Error'):
            message = re.sub(r'\x1b\[[0-9;]*m', '', p.stderr.strip() or text or '浏览器命令失败')
            raise BrowserError(message.replace('### Error\n', '').strip()[-1800:])
        return text

    def code(self, code, timeout=120):
        if self.scanner_id:
            code = '''async current => {
              const ctx=current.context(); let scanner=null;
              for (const candidate of ctx.pages()) {
                try {
                  const cdp=await ctx.newCDPSession(candidate);
                  const info=await cdp.send('Target.getTargetInfo'); await cdp.detach();
                  if(info.targetInfo.targetId===TARGET) { scanner=candidate; break; }
                } catch {}
              }
              if(!scanner) throw Error('BROWSER_GONE: CourseBeacon 扫描标签页已关闭，请点击检查作业重新连接');
              return await (SCRIPT)(scanner);
            }'''.replace('TARGET', json.dumps(self.scanner_id)).replace('SCRIPT', code)
        path = self.data_dir / ('command-' + uuid.uuid4().hex + '.js')
        path.write_text(code, encoding='utf-8')
        try:
            result = self.command('run-code', '--filename=' + str(path), timeout=timeout)
            try:
                return json.loads(result) if result else None
            except json.JSONDecodeError as exc:
                raise BrowserError('浏览器未返回有效数据：' + result[:600]) from exc
        finally:
            path.unlink(missing_ok=True)

    def script(self, name, payload=None, timeout=120):
        code = (ROOT / 'scripts' / name).read_text(encoding='utf-8')
        return self.code(code.replace('__INPUT__', json.dumps(payload, ensure_ascii=False)), timeout)

    def connect(self, url):
        self.scanner_id = None
        self.session = self.session_prefix + '-' + uuid.uuid4().hex[:8]
        self.command('attach', '--cdp=chrome', timeout=90)
        self.connected = True
        # Create our own tab; never navigate the user's selected tab.
        self.command('tab-new', 'about:blank', timeout=30)
        self.scanner_id = self.code('''async page => {
            const cdp=await page.context().newCDPSession(page);
            const info=await cdp.send('Target.getTargetInfo'); await cdp.detach();
            return info.targetInfo.targetId;
        }''')
        self.goto(url)

    def goto(self, url):
        return self.code('async page => { await page.goto(' + json.dumps(url) +
            ', {waitUntil:"domcontentloaded",timeout:30000}); return true; }')

    def close(self):
        try:
            if self.scanner_id:
                self.code('async page => { await page.close(); return true; }', timeout=15)
        except Exception:
            pass
        finally:
            self.scanner_id = None
            try:
                if self.connected:
                    self.command('detach', timeout=15)
            finally:
                self.connected = False
