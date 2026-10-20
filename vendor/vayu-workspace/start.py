"""Local wiki and separate durable personal/business action stores. Python stdlib only."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
import json, os, threading, webbrowser, sys
ROOT = Path(__file__).resolve().parent
PAGE = 'VAYU-Knowledge-Sphere-Live.html'
LOCK = threading.Lock()
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw): super().__init__(*a,directory=str(ROOT),**kw)
    def reply(self,code,value):
        raw=json.dumps(value).encode(); self.send_response(code); self.send_header('Content-Type','application/json'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def valid_host(self): return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'
    def space(self):
        s=parse_qs(urlsplit(self.path).query).get('space',[''])[0]
        return s if s in ('personal','business') else None
    def do_GET(self):
        if not self.valid_host(): return self.reply(403,{'error':'Use the printed loopback URL.'})
        if urlsplit(self.path).path == '/api/workspace':
            s=self.space()
            if not s: return self.reply(400,{'error':'Invalid workspace'})
            with LOCK:
                p=ROOT/'workspace-data'/f'{s}.json'
                try: value=json.loads(p.read_text()) if p.exists() else {'revision':0,'items':[]}
                except (OSError,ValueError): return self.reply(500,{'error':'Workspace file cannot be read. Restore your exported backup.'})
            return self.reply(200,value)
        # Private action files are accessible only through the API, not directory listings.
        if Path(self.translate_path(self.path)).is_relative_to(ROOT/'workspace-data') or urlsplit(self.path).path.endswith('/'):
            return self.reply(403,{'error':'Directory access disabled'})
        return super().do_GET()
    def do_HEAD(self):
        return self.reply(405,{'error':'HEAD disabled'})
    def do_POST(self):
        if not self.valid_host() or self.headers.get('Origin') != f'http://127.0.0.1:{self.server.server_port}': return self.reply(403,{'error':'Same-origin requests only'})
        s=self.space()
        if urlsplit(self.path).path != '/api/workspace' or not s: return self.reply(400,{'error':'Invalid workspace'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0 < size <= 2000000 or self.headers.get_content_type()!='application/json': raise ValueError()
            value=json.loads(self.rfile.read(size)); items=value['items']
            if not isinstance(items,list) or len(items)>3000 or not isinstance(value.get('revision'),int): raise ValueError()
            ids=set()
            for x in items:
                if not isinstance(x,dict) or not isinstance(x.get('id'),str) or x['id'] in ids or not x.get('title') or any(not isinstance(v,str) or len(v)>20000 for v in x.values()): raise ValueError()
                ids.add(x['id'])
            with LOCK:
                folder=ROOT/'workspace-data'; folder.mkdir(exist_ok=True); p=folder/f'{s}.json'
                old=json.loads(p.read_text()) if p.exists() else {'revision':0}
                if old['revision']!=value['revision']: return self.reply(409,{'error':'Another tab saved changes. Reload before editing.'})
                value={'revision':value['revision']+1,'items':items}
                tmp=p.with_suffix('.tmp'); tmp.write_text(json.dumps(value),encoding='utf-8'); os.replace(tmp,p)
            return self.reply(200,value)
        except (ValueError,KeyError,TypeError): return self.reply(400,{'error':'Invalid workspace data'})
        except OSError: return self.reply(500,{'error':'Could not save. Export a backup before closing.'})
if __name__=='__main__':
    with ThreadingHTTPServer(('127.0.0.1',0),Handler) as server:
        url=f'http://127.0.0.1:{server.server_port}/{PAGE}'
        print(url,flush=True)
        print('Keep this window open. Ctrl+C stops the server.',flush=True)
        if '--no-browser' not in sys.argv: webbrowser.open(url)
        try: server.serve_forever()
        except KeyboardInterrupt: pass
