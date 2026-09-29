"""Python -> bundled Node -> official playwright-cli (no shell interpolation)."""
from pathlib import Path
import json
import os
import subprocess
import sys
import threading
import uuid
import re

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))


class BrowserError(RuntimeError):
    pass


class Bridge:
    def __init__(self, data_dir, session='coursebeacon'):
        self.data_dir = Path(data_dir)
        self.session = session
        runtime = ROOT / 'runtime'
        self.node = Path(os.environ.get('COURSEBEACON_NODE', str(runtime / 'node.exe')))
        self.cli = Path(os.environ.get('COURSEBEACON_CLI', str(runtime / 'cli' / 'playwright-cli.js')))
        self.lock = threading.Lock()
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def command(self, *args, timeout=120):
        if not self.node.is_file() or not self.cli.is_file():
            raise BrowserError('未找到内置 Node / playwright-cli。源码运行前请执行 build.py --prepare。')
        with self.lock:
            try:
                p = subprocess.run([str(self.node), str(self.cli), '-s=' + self.session, *args, '--raw'],
                    cwd=self.data_dir, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, encoding='utf-8', errors='replace', timeout=timeout,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            except subprocess.TimeoutExpired as exc:
                raise BrowserError('浏览器操作超时，请检查网络后重试。') from exc
        text = p.stdout.strip()
        if p.returncode or text.startswith('### Error'):
            message = re.sub(r'\x1b\[[0-9;]*m', '', p.stderr.strip() or text or '浏览器命令失败')
            raise BrowserError(message.replace('### Error\n', '').strip()[-1800:])
        return text

    def code(self, code, timeout=120):
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

    def open(self, url, dashboard, profile):
        self.command('open', url, '--browser=chrome', '--headed', '--persistent', '--profile=' + str(profile))
        self.code('async page => { const p = await page.context().newPage(); '
                  'await p.goto(' + json.dumps(dashboard) + '); return true; }')

    def goto(self, url):
        return self.code('async page => { await page.goto(' + json.dumps(url) +
            ', {waitUntil:"domcontentloaded",timeout:30000}); return true; }')

    def close(self):
        self.command('close', timeout=15)
