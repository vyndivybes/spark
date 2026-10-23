"""Isolated UI acceptance host using SPARK's actual workspace socket handler.

Uses a temporary data directory and no microphone, hardware, accounts or provider.
Run manually with SPARK_TEST_PORT if needed. Never part of the application launch.
"""
import ast
import asyncio
from pathlib import Path
import sys
import tempfile
import subprocess
import shutil
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
import socketio
import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from spark_workspace import SparkWorkspace,WorkspaceError
from spark_workbench import Workbench,ACTION_KEYS as WORKBENCH_ACTIONS
from spark_productivity import WorkbenchError
from spark_maintenance import MaintenanceError
from spark_rea import ReaError
from arkus_skill_forge import SkillError


def main():
    import os
    with tempfile.TemporaryDirectory(prefix='spark-ui-acceptance-') as directory:
        workspace=SparkWorkspace(directory)
        workbench=Workbench(workspace)
        port=int(os.environ.get('SPARK_TEST_PORT','8123'))
        sio=socketio.AsyncServer(async_mode='asgi',cors_allowed_origins=[f'http://127.0.0.1:{port}',f'http://localhost:{port}','http://localhost:5173','http://127.0.0.1:5173'],max_http_buffer_size=3000000)
        namespace={'os':os,'workspace_client_allowed':lambda environ,provided,expected:environ.get('HTTP_ORIGIN','') in ('',f'http://127.0.0.1:{port}',f'http://localhost:{port}'),'asyncio':asyncio,'sio':sio,'audio_loop':SimpleNamespace(owner_sid=None,session=object()),
            'SETTINGS':{'face_auth_enabled':False},'authenticator':None,'spark_workspace':workspace,
            'spark_workbench':workbench,'workspace_project_by_sid':{},'EVOLUTION_ACTIONS':{},
            'WORKBENCH_ACTIONS':WORKBENCH_ACTIONS,'WorkspaceError':WorkspaceError,'WorkbenchError':WorkbenchError,
            'MaintenanceError':MaintenanceError,'ReaError':ReaError,'SkillError':SkillError,
            'CAPABILITY_READ_ONLY_ACTIONS':set()}
        tree=ast.parse((ROOT/'backend'/'server.py').read_text(encoding='utf-8'))
        handler=next(node for node in tree.body if isinstance(node,ast.AsyncFunctionDef) and node.name=='workspace_action')
        handler.decorator_list=[]
        exec(compile(ast.Module(body=[handler],type_ignores=[]),str(ROOT/'backend'/'server.py'),'exec'),namespace)
        sio.on('workspace_action',namespace['workspace_action'])
        @sio.event
        async def connect(sid,environ,auth):
            if not isinstance(auth,dict) or auth.get('acceptance') is not True:
                raise socketio.exceptions.ConnectionRefusedError('Isolated acceptance client required')
            namespace['audio_loop'].owner_sid=sid
        app=FastAPI()
        bundle=Path(directory)/'preview.js'
        subprocess.run([shutil.which('node') or 'node',str(ROOT/'node_modules/esbuild/bin/esbuild'),
                        str(ROOT/'tests/fixtures/workbench_preview.jsx'),'--bundle','--format=esm','--outfile='+str(bundle)],
                       cwd=ROOT,check=True,timeout=60)
        @app.get('/preview')
        async def preview():
            return HTMLResponse('<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>SPARK workbench acceptance</title><link rel="stylesheet" href="/preview.css"></head><body><main id="root" style="height:100vh;overflow:auto;padding:16px;color:white"></main><script type="module" src="/preview.js?v=1792419987090848400"></script></body></html>')
        @app.get('/preview.js')
        async def script():return FileResponse(bundle,media_type='text/javascript')
        @app.get('/preview.css')
        async def style():return FileResponse(max((ROOT/'dist/assets').glob('index-*.css'),key=lambda path:path.stat().st_mtime),media_type='text/css')
        uvicorn.run(socketio.ASGIApp(sio,app),host='127.0.0.1',port=int(os.environ.get('SPARK_TEST_PORT','8123')),log_level='warning')


if __name__=='__main__':main()
