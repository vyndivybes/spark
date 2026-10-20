from pathlib import Path
p = Path("src/App.jsx")
s = p.read_text(encoding="utf-8")
needle = """                                <button type="button" disabled={!!experienceBusy} onClick={()=>openExperience('hermes')}>
                                    <b>{experienceBusy==='hermes'?'Opening…':'Hermes → learned skills &amp; memories'}</b>
                                </button>
                            </div>"""
add = """                                <button type="button" disabled={!!experienceBusy} onClick={()=>openExperience('hermes')}>
                                    <b>{experienceBusy==='hermes'?'Opening…':'Hermes → learned skills &amp; memories'}</b>
                                </button>
                                <button type="button" disabled={!!experienceBusy} onClick={()=>openExperience('obsidian')}>
                                    <b>{experienceBusy==='obsidian'?'Opening…':'Obsidian → vault browser'}</b>
                                </button>
                            </div>"""
if needle not in s:
    print("no")
else:
    s = s.replace(needle, add)
    p.write_text(s, encoding="utf-8")
    print("ok")
