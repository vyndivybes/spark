import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from spark_workspace import SparkWorkspace
from spark_productivity import Productivity
from spark_vayu_data import VayuExports


@pytest.mark.skipif(os.environ.get('SPARK_TEST_VAYU_UI')!='1',reason='Opt-in local Chromium check')
def test_connected_project_graph_tasks_and_source_revocation():
    from playwright.sync_api import sync_playwright,expect
    spec=importlib.util.spec_from_file_location('vayu_project_launcher',Path(__file__).resolve().parents[1]/'scripts/vayu_launcher.py')
    launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);workspace=SparkWorkspace(root);productivity=Productivity(root,workspace.skills)
        note=workspace.execute('import_document','alpha',{'name':'shared.txt','data':b'Published graph evidence'})
        workspace.execute('publish_holo_note','alpha',{'id':note['id']})
        productivity.agenda('alpha','Review project evidence','2026-10-22T09:00:00+05:30','reminder')
        exports=VayuExports(workspace,productivity,SimpleNamespace(jobs=lambda project:[]));exports.publish('alpha')
        launcher.EXPORTS_ROOT=exports.root;launcher.upstream.ROOT=root/'vayu-data'
        server=ThreadingHTTPServer(('127.0.0.1',0),launcher.Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch();page=browser.new_page(viewport={'width':1450,'height':910})
                errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{server.server_port}/spark')
                expect(page.get_by_role('status')).to_contain_text('alpha')
                page.get_by_role('button',name='shared.txt',exact=True).click()
                expect(page.get_by_role('article',name='Selected project record')).to_contain_text('Published graph evidence')
                page.get_by_role('button',name='Task register',exact=True).click()
                expect(page.get_by_role('cell',name='Review project evidence',exact=True)).to_be_visible()
                for width,height in ((1450,910),(390,844)):
                    page.set_viewport_size({'width':width,'height':height})
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    evidence=Path(__file__).resolve().parents[1]/'docs/evidence';evidence.mkdir(exist_ok=True)
                    page.screenshot(path=str(evidence/f'vayu-project-{width}.png'),full_page=True)
                workspace.execute('unpublish_holo_note','alpha',{'id':note['id']})
                page.get_by_role('button',name='Refresh published data',exact=True).click()
                expect(page.get_by_role('status')).to_contain_text('No published project snapshots')
                expect(page.get_by_role('cell',name='Review project evidence',exact=True)).to_have_count(0)
                assert not errors,errors
                browser.close()
        finally:server.shutdown();server.server_close();thread.join()
