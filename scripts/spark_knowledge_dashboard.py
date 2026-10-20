#!/usr/bin/env python3
"""Tiny FastAPI dashboard for Graphify/Graphiti/Hermes status + endpoints."""
import argparse
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title="SPARK Knowledge Dashboards")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:*", "http://localhost:*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

mode = "graphify"
root = Path.cwd()

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>SPARK {mode_upper}</title>
  <style>
    body{{margin:0;padding:40px;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#070b13;color:#e5e7eb}}
    .card{{max-width:860px;margin:0 auto;background:rgba(15,23,42,0.8);border:1px solid rgba(34,211,238,0.25);border-radius:16px;padding:40px;box-shadow:0 20px 80px -40px rgba(34,211,238,0.8)}}
    h1{{margin:0;color:#22d3ee;font-size:40px;letter-spacing:4px}}
    p{{opacity:.85;line-height:1.6}}
    .tag{{display:inline-block;padding:4px 10px;border-radius:999px;background:rgba(34,211,238,0.15);border:1px solid rgba(34,211,238,0.4);margin-top:16px}}
    .grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:40px}}
    .item{{background:rgba(2,6,23,0.6);border:1px solid rgba(148,163,184,0.25);border-radius:12px;padding:20px}}
    code{{background:#0b122b;padding:2px 6px;border-radius:6px}}
    a{{color:#22d3ee}}
  </style>
</head>
<body>
  <div class="card">
    <h1>{mode_upper}</h1>
    <span class="tag">{mode} knowledge layer</span>
    <p>Graphify = static SPARK architecture graph. Graphiti = temporal/episodic knowledge graph. Hermes = learned agent memory.</p>
    <div class="grid">
      <div class="item">
        <h3>Status</h3>
        <p>Mode: <code>{mode}</code><br/>Backend: <code>http://127.0.0.1:8000</code></p>
      </div>
      <div class="item">
        <h3>Quick test</h3>
        <p>POST <code>/graphify/query</code>, <code>/graphiti/query</code> or call via SPARK voice with <code>cinematic_tools</code>.</p>
        <p><a href="http://127.0.0.1:8000/status" target="_blank">Check /status</a></p>
      </div>
    </div>
  </div>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def index():
    return DASHBOARD_HTML.format(mode=mode, mode_upper=mode.upper())


def main():
    global mode, root
    p = argparse.ArgumentParser()
    p.add_argument("--mode", required=True, choices=["graphify", "graphiti", "hermes"])
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--root", type=str, default=".")
    args = p.parse_args()
    mode = args.mode
    root = Path(args.root)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
