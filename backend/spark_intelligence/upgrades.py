"""Read-only version/compatibility inspection; never installs or deploys updates."""
import asyncio
from importlib import metadata
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]


def versions():
    packages={}
    for name in ('mcp','httpx','jsonschema','croniter','tzdata','dspy','gepa','faiss-cpu','sentence-transformers'):
        try:
            info=metadata.metadata(name)
            license_value=info.get('License-Expression') or info.get('License') or 'Review package license'
            packages[name]={'version':metadata.version(name),'license':license_value[:200]}
        except metadata.PackageNotFoundError:
            packages[name]={'version':None,'state':'not_installed'}
    try:
        revision=subprocess.run(['git','-C',str(ROOT),'rev-parse','HEAD'],capture_output=True,text=True,timeout=5,check=True).stdout.strip()
    except (OSError,subprocess.SubprocessError):revision=None
    return {'spark':json.loads((ROOT/'package.json').read_text(encoding='utf-8'))['version'],'source_revision':revision,'python':sys.version.split()[0],'packages':packages,'automatic_updates':False,'security_scan':'unavailable; inspected code, tests and dependency compatibility do not establish absence of vulnerabilities'}


def compatibility():
    try:
        result=subprocess.run([sys.executable,'-m','pip','check'],capture_output=True,text=True,timeout=30)
        return {'ok':result.returncode==0,'report':(result.stdout+result.stderr)[-12000:],'method':'pip check; installed package constraints only','changes_applied':False}
    except (OSError,subprocess.SubprocessError):
        return {'ok':False,'report':'Dependency compatibility check unavailable or timed out','changes_applied':False}


async def releases():
    import httpx
    results=[]
    async with httpx.AsyncClient(timeout=10,trust_env=False,follow_redirects=False) as client:
        for repository in ('vyndivybes/spark','open-jarvis/OpenJarvis'):
            try:
                response=await client.get('https://api.github.com/repos/'+repository+'/releases/latest',headers={'Accept':'application/vnd.github+json'})
                response.raise_for_status()
                value=response.json()
                results.append({'repository':repository,'tag':value['tag_name'],'url':value['html_url'],'published':value.get('published_at'),'state':'available'})
            except Exception:
                results.append({'repository':repository,'state':'unavailable_or_no_release'})
    return {'releases':results,'updates_installed':False}
