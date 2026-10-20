#!/usr/bin/env python3
import argparse
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title="SPARK Obsidian")
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:*","http://localhost:*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
vault = Path(os.path.expanduser("~/Documents/Obsidian Vault"))

DASH = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>SPARK - Obsidian</title>
<style>body{margin:0;font-family:system-ui;background:#070b13;color:#e5e7eb}header{padding:16px 24px;border-bottom:1px solid rgba(148,163,184,0.2);background:#0f172a;display:flex;gap:16px;align-items:center}h1{margin:0;color:#22d3ee;letter-spacing:3px}input{flex:1;padding:10px 14px;border-radius:999px;border:1px solid rgba(148,163,184,0.4);background:#0b122b;color:#e5e7eb}main{display:grid;grid-template-columns:320px 1fr;height:calc(100vh - 65px)}aside{overflow:auto;padding:16px;border-right:1px solid rgba(148,163,184,0.1)}section{overflow:auto;padding:32px}pre{white-space:pre-wrap;font-family:ui-monospace,Consolas,monospace;line-height:1.7}.item{padding:8px 10px;border-radius:8px;cursor:pointer;margin-bottom:4px}.item.active{background:rgba(34,211,238,0.12);border:1px solid rgba(34,211,238,0.4)}</style>
</head><body><header><h1>OBSIDIAN</h1><input id="q" placeholder="Search notes..."><div id="vault" style="opacity:.7"></div></header>
<main><aside id="list"></aside><section><pre id="content">Select a note</pre></section></main>
<script>
fetch('/api/vault').then(r=>r.json()).then(j=>document.getElementById('vault').textContent=j.path);
async function load(t=''){const r=await fetch('/api/notes?q='+encodeURIComponent(t));const notes=await r.json();const list=document.getElementById('list');list.innerHTML='';for(const n of notes){const d=document.createElement('div');d.className='item';d.textContent=n.name;d.onclick=async()=>{document.querySelectorAll('.item').forEach(x=>x.classList.remove('active'));d.classList.add('active');const rr=await fetch('/api/note?path='+encodeURIComponent(n.path));const dd=await rr.json();document.getElementById('content').textContent=dd.text||'';};list.appendChild(d);}}
document.getElementById('q').oninput=e=>load(e.target.value);load('');
</script></body></html>"""

@app.get("/", response_class=HTMLResponse)
def index():
    return DASH

@app.get("/api/vault")
def api_vault():
    return {"path": str(vault)}

@app.get("/api/notes")
def api_notes(q: str = Query("")):
    notes = []
    if not vault.exists(): return []
    for p in vault.rglob("*.md"):
        if not p.is_file(): continue
        rel = str(p.relative_to(vault))
        if q:
            ql = q.lower()
            if ql not in rel.lower():
                try:
                    if ql not in p.read_text(encoding="utf-8", errors="ignore").lower(): continue
                except: continue
        notes.append({"name": p.stem, "path": rel})
    notes.sort(key=lambda x: x["name"].lower())
    return notes[:200]

@app.get("/api/note")
def api_note(path: str = Query(...)):
    target = (vault / path).resolve()
    vres = vault.resolve()
    if not str(target).startswith(str(vres)): raise HTTPException(status_code=403)
    if not target.exists() or not target.is_file(): raise HTTPException(status_code=404)
    return {"text": target.read_text(encoding="utf-8", errors="ignore")}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--vault", type=str, required=True)
    p.add_argument("--root", type=str, default=".")
    args = p.parse_args()
    global vault
    vault = Path(os.path.expanduser(args.vault))
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")

if __name__ == "__main__":
    main()
