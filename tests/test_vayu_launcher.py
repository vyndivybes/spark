"""Exercise VAYU's real HTTP and persistence boundary through the SPARK adapter."""
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer

spec = importlib.util.spec_from_file_location('vayu_launcher', Path(__file__).resolve().parents[1] / 'scripts/vayu_launcher.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class VayuIntegration(unittest.TestCase):
    def test_published_project_api_and_views(self):
        with tempfile.TemporaryDirectory() as folder:
            previous=launcher.EXPORTS_ROOT
            launcher.EXPORTS_ROOT=Path(folder)
            data={'project':'alpha','publishedAt':'2026-10-20T01:00:00Z','documents':[{'title':'A note'}],'tasks':[],'nodes':[],'edges':[]}
            (Path(folder)/'alpha.json').write_text(json.dumps(data))
            server=ThreadingHTTPServer(('127.0.0.1',0),launcher.Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            origin=f'http://127.0.0.1:{server.server_port}'
            try:
                with urlopen(origin+'/api/spark-projects') as response:
                    self.assertEqual(json.load(response)['projects'][0]['project'],'alpha')
                with urlopen(origin+'/api/spark-project?project=alpha') as response:
                    self.assertEqual(json.load(response),data)
                for page in ('/spark','/spark-view.js','/spark-view.css'):
                    with urlopen(origin+page) as response:self.assertEqual(response.status,200)
                with self.assertRaises(HTTPError):urlopen(origin+'/api/spark-project?project=../alpha')
                (Path(folder)/'alpha.json').unlink()
                with self.assertRaises(HTTPError):urlopen(origin+'/api/spark-project?project=alpha')
            finally:
                server.shutdown();server.server_close();thread.join();launcher.EXPORTS_ROOT=previous

    def test_views_storage_isolation_restart_and_conflicts(self):
        with tempfile.TemporaryDirectory() as folder:
            launcher.upstream.ROOT = Path(folder)
            for restart in range(2):
                server = ThreadingHTTPServer(('127.0.0.1', 0), launcher.Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                origin = f'http://127.0.0.1:{server.server_port}'

                def get(route):
                    return urlopen(origin + route)

                def save(revision, origin_header=origin):
                    body = json.dumps({'revision': revision, 'items': [{'id': 'test-item', 'title': 'Persisted outcome', 'status': 'Open'}]}).encode()
                    return urlopen(Request(origin + '/api/workspace?space=business', data=body,
                        headers={'Content-Type': 'application/json', 'Origin': origin_header}))

                try:
                    for page in ['VAYU-Knowledge-Sphere-Live.html', 'VYNDI_VAOS_Neural_Schema_Gesture_Hologram_v4.html', 'views/index.html', 'views/analytics.html', 'views/graph.html', 'assets/data-intelligence.js', 'assets/visual-workspace.js', 'assets/visual-workspace.css']:
                        with get('/' + page) as response:
                            self.assertEqual(response.status, 200)
                            self.assertEqual(response.headers.get('Cache-Control'), 'no-store')
                    with get('/api/workspace?space=business') as response:
                        stored = json.load(response)
                    self.assertEqual(stored['revision'], restart)
                    if restart:
                        self.assertEqual(stored['items'][0]['title'], 'Persisted outcome')
                    else:
                        with save(0) as response:
                            self.assertEqual(json.load(response)['revision'], 1)
                        with self.assertRaises(HTTPError) as conflict:
                            save(0)
                        self.assertEqual(conflict.exception.code, 409)
                        with self.assertRaises(HTTPError) as foreign:
                            save(1, 'https://example.com')
                        self.assertEqual(foreign.exception.code, 403)
                    with get('/api/workspace?space=personal') as response:
                        self.assertEqual(json.load(response)['items'], [])
                    for private in ['/workspace-data/business.json', '/start.py', '/assets/../workspace-data/business.json']:
                        with self.assertRaises(HTTPError) as blocked:
                            get(private)
                        self.assertEqual(blocked.exception.code, 404)
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join()


if __name__ == '__main__':
    unittest.main()
