"""Local, source-labelled projections for Spark, Obsidian and Graphiti.

Only an explicit host configuration enables this bridge. Graph extraction is a
separate Graphiti operation; refreshing local projections never calls an LLM.
"""
import hashlib
import json
import os
import re
import sqlite3
import stat
import secrets
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from spark_neural_atlas import extract_inventory, atlas_data_path, choose_node_names, links_by_node, node_markdown
from spark_obsidian_integration import ObsidianIntegration

BUSINESS = {'vaos-jarvis', 'vyndi-os', 'vedm'}


def checked(path):
    path = Path(path).absolute()
    if any(part.exists() and (part.is_symlink() or
           getattr(part.lstat(), 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0))
           for part in (path, *path.parents)):
        raise ValueError('Linked bridge storage is prohibited.')
    return path


def bridge_records(workspace, vault, repository):
    """Yield stable IDs, labels, source timestamps and bounded source text."""
    inventory = extract_inventory(atlas_data_path(repository).read_text(encoding='utf-8'))
    names, links = choose_node_names(inventory), links_by_node(inventory)
    when = atlas_data_path(repository).stat().st_mtime
    for node in inventory['nodes']:
        yield ('inventory:' + node['id'], 'Packaged business reference: ' + names[node['id']], when,
               'Packaged reference inventory, not a live business ledger.\n' +
               node_markdown(inventory, links, names, node))
    graph_path = Path(repository) / 'graphify-out/graph.json'
    if graph_path.is_file():
        graph = json.loads(graph_path.read_text(encoding='utf-8'))
        yield ('graphify:architecture', 'Graphify architecture', graph_path.stat().st_mtime,
               'Local code architecture inventory. Source: ' + str(graph_path) + '\n' +
               json.dumps({'nodes': len(graph.get('nodes', [])), 'edges': len(graph.get('links', graph.get('edges', []))),
                           'usage': 'Use query_graph for code symbols and source files.'}))
    integration = ObsidianIntegration()
    integration.vault = Path(vault)
    for note in integration.snapshot(exclude_folders=('Spark-Connected',))['notes']:
        if Path(note['path']).parts[0] == 'Spark-Connected':
            continue
        yield ('obsidian:' + note['path'], 'Obsidian: ' + note['name'], note['modified'],
               'User note. Source: ' + note['path'] + '\n' + note['text'])
    path = checked(Path(workspace) / 'integration-sync/snapshots.sqlite3')
    if path.is_file():
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
            for service, tool, body, last_success, state in db.execute(
                    'SELECT service,tool,body,last_success,state FROM snapshots WHERE body IS NOT NULL'):
                if service not in BUSINESS:
                    continue
                # Failed readers retain old snapshots. Preserve that fact in the
                # episode instead of claiming the retained body is current.
                value = json.loads(body)
                yield ('snapshot:' + service + '/' + tool, service + ' cached evidence', last_success,
                       f'Source: {service}/{tool}. Reader state: {state}. '
                       f'Last successful read: {datetime.fromtimestamp(last_success, timezone.utc).isoformat()}. '
                       f'Source limitation: {value.get("limitation", "See source evidence")}. '
                       'Cached evidence; preserve source limitations, missing evidence and release holds.\n' +
                       json.dumps(value, ensure_ascii=False, sort_keys=True))


def project_knowledge(workspace, project, vault, repository):
    if not isinstance(project, str) or len(project) > 60 or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', project):
        raise ValueError('Invalid project identifier.')
    workspace, vault = checked(workspace), checked(vault)
    if not vault.is_dir():
        raise ValueError('Configured Obsidian vault unavailable.')
    folder = checked(vault / 'Spark-Connected' / project)
    folder.mkdir(parents=True, exist_ok=True)
    database = checked(workspace / 'knowledge-bridge/episodes.sqlite3')
    database.parent.mkdir(parents=True, exist_ok=True)
    records = list(bridge_records(workspace, vault, repository))
    inventory_targets = {title.removeprefix('Packaged business reference: '):
                         hashlib.sha256(identity.encode()).hexdigest()[:20]
                         for identity, title, _, _ in records if identity.startswith('inventory:')}
    with closing(sqlite3.connect(database)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS episodes(project TEXT,record_id TEXT,body TEXT,created REAL, PRIMARY KEY(project,record_id))')
        for identity, title, when, body in records:
            # Include provenance and reader state in content identity, not export
            # time. Repeated refreshes must not create duplicate graph episodes.
            full_body = title + '\n' + body
            body = full_body if len(full_body) <= 4000 else full_body[:3900] + '\n[Source excerpt truncated to fit graph episode.]'
            fingerprint = re.sub(r'Last successful read: \S+\. ', '', body) if identity.startswith('snapshot:') else body
            digest = hashlib.sha256(fingerprint.encode('utf-8')).hexdigest()
            record_id = 'bridge:' + project + ':' + hashlib.sha256(identity.encode()).hexdigest()[:20] + ':' + digest
            db.execute('INSERT OR IGNORE INTO episodes VALUES(?,?,?,?)', (project, record_id, body, when))
            name = hashlib.sha256(identity.encode()).hexdigest()[:20] + '.md'
            target = checked(folder / name)
            rendered = body
            if identity.startswith('inventory:'):
                def linked(match):
                    label = match[1]
                    target_id = inventory_targets.get(label)
                    return f'[[Spark-Connected/{project}/{target_id}|{label}]]' if target_id else match[0]
                rendered = re.sub(r'\[\[([^\]|]+)\]\]', linked, body)
            text = f'# {title}\n\n[[Spark-Connected/{project}/Spark connected knowledge|Spark connected knowledge]]\n\nSource ID: {identity}\n\n{rendered}\n'
            if not target.exists() or target.read_text(encoding='utf-8') != text:
                scratch = checked(target.with_suffix('.' + secrets.token_hex(5) + '.tmp'))
                try:
                    scratch.write_text(text, encoding='utf-8')
                    os.replace(scratch, target)
                finally:
                    scratch.unlink(missing_ok=True)
        total = db.execute('SELECT count(*) FROM episodes WHERE project=?', (project,)).fetchone()[0]
    index = checked(folder / 'Spark connected knowledge.md')
    index.write_text('# Spark connected knowledge\n\n'
                     'Local projections. Historical snapshots may be stale. Graphiti extraction is separate.\n\n' +
                     '\n'.join(f'- [[Spark-Connected/{project}/{hashlib.sha256(identity.encode()).hexdigest()[:20]}|{title}]]'
                               for identity, title, _, _ in records) + '\n', encoding='utf-8')
    return {'project': project, 'records': len(records), 'episodes_staged': total,
            'vault_folder': str(folder), 'graph_extraction': 'Run refresh_project_graph for this project.'}


def configured_projection(workspace):
    config = checked(Path(workspace) / 'knowledge-bridge/config.json')
    if not config.exists():
        return None
    value = json.loads(config.read_text(encoding='utf-8'))
    return project_knowledge(workspace, value['project'], value['vault'], value['repository'])
