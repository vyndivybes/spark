"""Host the bundled VAYU UI with durable storage outside its source checkout."""
import argparse
import json
import os
import re
import importlib.util
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit, unquote, parse_qs

STATIC_ROOT = Path(__file__).resolve().parents[1] / 'vendor' / 'vayu-workspace'
SPARK_ASSETS=Path(__file__).resolve().parents[1]/'public'/'vayu-spark'
EXPORTS_ROOT=Path(os.environ['SPARK_VAYU_EXPORTS_DIR']).resolve() if os.environ.get('SPARK_VAYU_EXPORTS_DIR') else None
spec = importlib.util.spec_from_file_location('spark_vayu_upstream', STATIC_ROOT / 'start.py')
upstream = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upstream)


class Handler(upstream.Handler):
    def __init__(self, *args, **kwargs):
        SimpleHTTPRequestHandler.__init__(self, *args, directory=str(STATIC_ROOT), **kwargs)

    def end_headers(self):
        # Local updates must not leave old navigation scripts in Electron's cache.
        route = urlsplit(self.path).path
        if not route.startswith('/api/') and route.endswith(('.html', '.js', '.css')):
            self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def do_GET(self):
        route = unquote(urlsplit(self.path).path)
        if not self.valid_host():return self.reply(403,{'error':'Use the loopback URL.'})
        if route in ('/api/spark-projects','/api/spark-project'):
            try:
                if route=='/api/spark-projects':
                    projects=[]
                    if EXPORTS_ROOT and EXPORTS_ROOT.is_dir() and not EXPORTS_ROOT.is_symlink():
                        for path in sorted(EXPORTS_ROOT.glob('*.json'))[:200]:
                            if path.is_symlink() or path.stat().st_size>2_000_000 or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',path.stem):continue
                            value=json.loads(path.read_text(encoding='utf-8'))
                            projects.append({'project':path.stem,'publishedAt':value['publishedAt'],'documents':len(value['documents']),'tasks':len(value['tasks'])})
                    return self.reply(200,{'projects':projects})
                project=parse_qs(urlsplit(self.path).query).get('project',[''])[0]
                if not EXPORTS_ROOT or EXPORTS_ROOT.is_symlink() or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',project) or len(project)>60:raise ValueError()
                path=EXPORTS_ROOT/(project+'.json')
                if path.is_symlink() or not path.is_file() or path.stat().st_size>2_000_000:raise ValueError()
                return self.reply(200,json.loads(path.read_text(encoding='utf-8')))
            except (OSError,ValueError,KeyError):return self.reply(404,{'error':'Published Spark snapshot unavailable. Publish or refresh it from Spark Home.'})
        extra={'/spark':'index.html','/spark-view.js':'view.js','/spark-view.css':'view.css'}
        if route in extra:
            content=(SPARK_ASSETS/extra[route]).read_bytes()
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8' if route=='/spark' else 'text/javascript' if route.endswith('.js') else 'text/css')
            self.send_header('Content-Length',str(len(content)));self.end_headers();self.wfile.write(content);return
        if route in ('/'+upstream.PAGE, '/VYNDI_VAOS_Neural_Schema_Gesture_Hologram_v4.html'):
            page = route.lstrip('/')
            params = parse_qs(urlsplit(self.path).query)
            if page == upstream.PAGE and not params.get('workspace') and not params.get('embedded'):
                # Older running desktop managers still request this entry point.
                # Serve the studio with 200 so their startup health check also succeeds.
                page = 'VYNDI_VAOS_Neural_Schema_Gesture_Hologram_v4.html'
            content=(STATIC_ROOT/page).read_text(encoding='utf-8').replace(
                '<html lang="en">', '<html lang="en" data-spark-projects="true">')
            raw=content.encode('utf-8');self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
        if route != '/api/workspace':
            target = Path(self.translate_path(self.path)).resolve()
            allowed = target.is_relative_to(STATIC_ROOT) and (
                target.name in (upstream.PAGE, 'VYNDI_VAOS_Neural_Schema_Gesture_Hologram_v4.html')
                or target.is_relative_to(STATIC_ROOT / 'assets')
                or target.is_relative_to(STATIC_ROOT / 'views'))
            if not allowed or not target.is_file():
                return self.reply(404, {'error': 'Not found'})
        return super().do_GET()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--data-dir', type=Path, required=True)
    args = parser.parse_args()
    # Upstream stores ROOT/workspace-data; static assets remain read-only above.
    upstream.ROOT = args.data_dir.resolve()
    upstream.ROOT.mkdir(parents=True, exist_ok=True)
    with ThreadingHTTPServer(('127.0.0.1', args.port), Handler) as server:
        print(f'http://127.0.0.1:{server.server_port}/{upstream.PAGE}', flush=True)
        server.serve_forever()


if __name__ == '__main__':
    main()
