"""Bundle Python + Node + official playwright-cli into one Windows exe.

Requires system Google Chrome; does not bundle a browser or any user profile.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--node', type=Path)
    p.add_argument('--cli-root', type=Path)
    p.add_argument('--work-dir', type=Path, default=ROOT/'build-work')
    p.add_argument('--output-dir', type=Path, default=ROOT/'dist')
    p.add_argument('--prepare', action='store_true')
    args = p.parse_args()
    node = args.node or Path(shutil.which('node') or '')
    if not node.is_file():
        p.error('Install Node.js or supply --node path/to/node.exe')
    if args.cli_root:
        cli = args.cli_root
    else:
        npm = shutil.which('npm.cmd') or shutil.which('npm')
        if not npm:
            p.error('Install @playwright/cli or supply --cli-root')
        npm_root = subprocess.check_output([npm,'root','-g'], text=True).strip()
        cli = Path(npm_root)/'@playwright'/'cli'
    if not (cli/'playwright-cli.js').is_file():
        p.error('Run npm install -g @playwright/cli@0.1.13 first')
    work = args.work_dir.resolve()
    runtime = work/'runtime'
    runtime.mkdir(parents=True, exist_ok=True)
    shutil.copy2(node, runtime/'node.exe')
    shutil.copytree(cli, runtime/'cli', dirs_exist_ok=True)
    node_version = subprocess.check_output([str(node),'--version'], text=True).strip()
    license_file = node.parent/'LICENSE'
    if license_file.is_file():
        license_bytes = license_file.read_bytes()
    elif (runtime/'NODE-LICENSE.txt').is_file():
        license_bytes = (runtime/'NODE-LICENSE.txt').read_bytes()
    else:
        license_bytes = urllib.request.urlopen(
            f'https://raw.githubusercontent.com/nodejs/node/{node_version}/LICENSE', timeout=45).read()
    (runtime/'NODE-LICENSE.txt').write_bytes(license_bytes)
    (runtime/'runtime-versions.json').write_text(json.dumps({
        'node':node_version,
        'playwright-cli':json.loads((cli/'package.json').read_text())['version']}, indent=2))
    if args.prepare:
        print('Prepared:', runtime)
        print('Set COURSEBEACON_NODE and COURSEBEACON_CLI to run source with this runtime.')
        return
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed',
        '--name','CourseBeacon','--distpath',str(args.output_dir.resolve()),
        '--workpath',str(work/'pyinstaller'),'--specpath',str(work),
        '--add-data',str(ROOT/'static')+';static',
        '--add-data',str(ROOT/'scripts')+';scripts',
        '--add-data',str(runtime)+';runtime',str(ROOT/'app.py')], check=True)


if __name__ == '__main__':
    main()
