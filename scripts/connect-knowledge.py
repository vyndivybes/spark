"""Connect the selected project's local business references, notes and cached evidence."""
import argparse
import asyncio
import json
import os
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from spark_knowledge_bridge import checked, project_knowledge


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', default='default')
    parser.add_argument('--workspace', type=Path, default=Path(os.environ.get('LOCALAPPDATA', Path.home() / '.spark')) / 'SPARK/workspace')
    parser.add_argument('--vault', type=Path)
    parser.add_argument('--refresh-graph', action='store_true', help='Send staged text to the configured Groq/Gemini Graphiti providers, up to 12 episodes.')
    parser.add_argument('--drain-graph', action='store_true', help='Process pending Graphiti batches until complete; stop on failures or lack of progress.')
    parser.add_argument('--import-inventory', action='store_true', help='Import explicit inventory entities and relationships using Graphiti models and Gemini embeddings.')
    args = parser.parse_args()
    preferences = json.loads((ROOT / 'spark.local.json').read_text(encoding='utf-8'))
    vault = args.vault or Path(preferences['ObsidianVault'])
    result = project_knowledge(args.workspace, args.project, vault, ROOT)
    config = checked(args.workspace / 'knowledge-bridge/config.json')
    config.write_text(json.dumps({'project': args.project, 'vault': str(vault.absolute()), 'repository': str(ROOT)}, indent=2), encoding='utf-8')
    if args.refresh_graph or args.drain_graph or args.import_inventory:
        from dotenv import load_dotenv
        load_dotenv(ROOT / 'backend/.env')
        from spark_graphiti_mcp import TemporalGraph
        graph = TemporalGraph(args.workspace, args.workspace / 'graphiti')
        async def refresh():
            try:
                if args.import_inventory:
                    from spark_graphiti_inventory import import_inventory, import_source_records
                    imported = await import_inventory(graph, args.project, ROOT,
                        progress=lambda value:print(json.dumps(value), flush=True))
                    print(json.dumps({'inventory':imported}), flush=True)
                    sources = await import_source_records(graph,args.project,
                        progress=lambda value:print(json.dumps(value),flush=True))
                    print(json.dumps({'business_sources':sources}),flush=True)
                    if not args.refresh_graph and not args.drain_graph:
                        return {**imported,'remaining':len(graph._pending(args.project,100000))}
                batches, added, quota_retries = 0, 0, 0
                while True:
                    batch = await graph.refresh(args.project, time_limit_seconds=600 if args.drain_graph else 120,
                                                combined_extraction=args.drain_graph)
                    batches += 1
                    added += batch['episodes_added']
                    print(json.dumps({'batch':batches, **batch}), flush=True)
                    # A provider-specified short reset is a real state change,
                    # not a blind retry. Back off once, then stop if no progress.
                    errors = ' '.join(batch.get('errors', []))
                    delay = re.search(r'Please try again in ([0-9.]+)s', errors)
                    if batch['episodes_added']:
                        quota_retries = 0
                    if args.drain_graph and delay and float(delay[1]) <= 60 and quota_retries < 1:
                        quota_retries += 1
                        await asyncio.sleep(float(delay[1]) + 1)
                        continue
                    if (not args.drain_graph or not batch['remaining'] or
                            batch['episodes_failed'] or not batch['episodes_added']):
                        return {**batch, 'batches':batches, 'total_added':added}
            finally:
                if graph._graphiti is not None:
                    await graph._graphiti.close()
                graph._manifest.close()
        result['graphiti'] = asyncio.run(refresh())
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
