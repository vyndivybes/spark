"""Import explicit inventory relationships through Graphiti's native graph models.

The packaged inventory already contains entities and typed edges. Preserve those
source assertions as reference data rather than asking an LLM to invent triples.
"""
import hashlib
import time
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from spark_neural_atlas import atlas_data_path, extract_inventory


async def import_inventory(graph, project, repository, *, progress=lambda value: None):
    from graphiti_core.nodes import EntityNode, EpisodicNode, EpisodeType
    from graphiti_core.edges import EntityEdge, EpisodicEdge
    from graphiti_core.utils.bulk_utils import add_nodes_and_edges_bulk

    client = await graph._client()
    inventory = extract_inventory(atlas_data_path(repository).read_text(encoding='utf-8'))
    pending = {row[3]:row for row in graph._pending(project, 100000)}
    indexed = {}
    for node in inventory['nodes']:
        prefix = 'bridge:' + project + ':' + hashlib.sha256(('inventory:' + node['id']).encode()).hexdigest()[:20] + ':'
        matches = [row for identity,row in pending.items() if identity.startswith(prefix)]
        if matches:
            indexed[node['id']] = matches
    if not indexed:
        return {'episodes_added':0, 'nodes':0, 'edges':0}
    now = datetime.now(timezone.utc)
    identity = lambda kind, key: str(uuid5(NAMESPACE_URL, 'spark:' + project + ':' + kind + ':' + key))
    nodes, episodes, mentions, records = [], [], [], []
    by_id = {node['id']:node for node in inventory['nodes']}
    edges = [edge for edge in inventory['edges'] if edge['source'] in indexed or edge['target'] in indexed]
    needed = set(indexed) | {edge[side] for edge in edges for side in ('source','target')}
    episode_ids = {}
    for node_id in indexed:
        episode_ids[node_id] = []
        for source_id,body,when,record_id in indexed[node_id]:
            episode_id = identity('episode', record_id)
            episode_ids[node_id].append(episode_id)
            episode = EpisodicNode(uuid=episode_id, name=source_id, group_id=project,
                source=EpisodeType.text, source_description='Packaged business reference inventory; not a live business ledger.',
                content=body, created_at=now, valid_at=datetime.fromtimestamp(when, timezone.utc))
            episodes.append(episode)
            mentions.append(EpisodicEdge(uuid=identity('mention',record_id), source_node_uuid=episode_id,
                target_node_uuid=identity('entity',node_id), group_id=project, created_at=now))
            records.append((record_id, project, episode_id, time.time()))
    for node_id in sorted(needed):
        node = by_id[node_id]
        nodes.append(EntityNode(uuid=identity('entity',node_id), name=node.get('title') or node_id,
            group_id=project, labels=['Entity'], created_at=now,
            summary=('Packaged reference inventory. Status: ' + str(node.get('status','unspecified')) + '. ' + str(node.get('summary','')))[:4000],
            attributes={'source_kind':'packaged-reference','inventory_id':node_id,'source_ids':node.get('source_ids',[])}))
    if graph._driver is not None:
        saved, _, _ = await graph._driver.execute_query(
            'MATCH (n:Entity) WHERE n.group_id=$group_id RETURN n.uuid AS uuid,n.name AS name,n.summary AS summary,n.name_embedding AS embedding', group_id=project)
        existing = {row['uuid']:row for row in saved}
        unchanged = set()
        for node in nodes:
            old = existing.get(node.uuid)
            if old and old['name'] == node.name and old['embedding']:
                node.name_embedding = old['embedding']
                if old['summary'] == node.summary:
                    unchanged.add(node.uuid)
        nodes = [node for node in nodes if node.uuid not in unchanged]
        saved_episodes, _, _ = await graph._driver.execute_query(
            'MATCH (e:Episodic) WHERE e.group_id=$group_id RETURN e.uuid AS uuid', group_id=project)
        existing_episodes = {row['uuid'] for row in saved_episodes}
        episodes = [episode for episode in episodes if episode.uuid not in existing_episodes]
    relations = []
    for edge in edges:
        source, target = edge['source'], edge['target']
        kind = edge.get('type') or 'related-to'
        fact = ('Packaged reference inventory records: ' + str(by_id[source].get('title') or source) +
                ' --' + kind + '--> ' + str(by_id[target].get('title') or target) + '. ' + str(edge.get('description') or ''))[:4000]
        relations.append(EntityEdge(uuid=identity('edge',source + ':' + kind + ':' + target),
            source_node_uuid=identity('entity',source), target_node_uuid=identity('entity',target),
            group_id=project, name=kind.replace('-','_').upper(), fact=fact, created_at=now,
            episodes=episode_ids.get(source,[]) + episode_ids.get(target,[]),
            attributes={'source_kind':'packaged-reference'}))
    # Persist via the library's own schema and embedding paths. Bounded chunks
    # expose progress without requiring a separate database server or LLM call.
    if episodes:
        await add_nodes_and_edges_bulk(client.driver, episodes, [], [], [], client.embedder)
    for offset in range(0,len(nodes),20):
        await add_nodes_and_edges_bulk(client.driver, [], [], nodes[offset:offset+20], [], client.embedder)
        if graph._driver is not None:
            await graph._driver.execute_query('CHECKPOINT')
        progress({'phase':'inventory_entities','completed':min(offset+20,len(nodes)),'total':len(nodes)})
    for offset in range(0,len(relations),30):
        await add_nodes_and_edges_bulk(client.driver, [], [], [], relations[offset:offset+30], client.embedder)
        if graph._driver is not None:
            await graph._driver.execute_query('CHECKPOINT')
        progress({'phase':'inventory_relationships','completed':min(offset+30,len(relations)),'total':len(relations)})
    await add_nodes_and_edges_bulk(client.driver, [], mentions, [], [], client.embedder)
    with graph._manifest:
        graph._manifest.executemany('INSERT OR REPLACE INTO ingested VALUES(?,?,?,?)', records)
    return {'episodes_added':len(records),'nodes':len(nodes),'edges':len(relations)}


async def import_source_records(graph, project, *, progress=lambda value: None):
    """Preserve structured source responses and code inventories without inferred claims."""
    from graphiti_core.nodes import EntityNode, EpisodicNode, EpisodeType
    from graphiti_core.edges import EntityEdge, EpisodicEdge
    from graphiti_core.utils.bulk_utils import add_nodes_and_edges_bulk
    from spark_knowledge_bridge import BUSINESS

    pending = [row for row in graph._pending(project,100000)
               if row[1].splitlines()[0].removesuffix(' cached evidence') in BUSINESS or row[1].splitlines()[0] == 'Graphify architecture']
    if not pending:
        return {'episodes_added':0}
    client = await graph._client()
    identity = lambda kind,key: str(uuid5(NAMESPACE_URL,'spark:'+project+':'+kind+':'+key))
    now = datetime.now(timezone.utc)
    for index,(source_id,body,when,record_id) in enumerate(pending):
        architecture = body.splitlines()[0] == 'Graphify architecture'
        service = 'graphify' if architecture else body.splitlines()[0].removesuffix(' cached evidence')
        source_kind = 'local-code-architecture' if architecture else 'cached-business-evidence'
        recorded = datetime.fromtimestamp(when,timezone.utc)
        episode_id, node_id, source_node_id = identity('episode',record_id), identity('source-record',record_id), identity('business-source',service)
        episode = EpisodicNode(uuid=episode_id,name=source_id,group_id=project,source=EpisodeType.text,
            source_description='Cached business source response; preserve recorded date, reader state and limitations.',
            content=body,created_at=now,valid_at=recorded)
        source = EntityNode(uuid=source_node_id,name=service+' cached evidence source',group_id=project,
            labels=['Entity'],created_at=now,summary='Source of cached responses in Spark; not a live business ledger.',
            attributes={'source_kind':'cached-business-source'})
        node = EntityNode(uuid=node_id,name=service+' snapshot '+recorded.isoformat(),group_id=project,
            labels=['Entity'],created_at=now,summary=body,
            attributes={'source_kind':source_kind,'source_record_id':record_id,'recorded_at':recorded.isoformat()})
        fact = service+' has a cached source response recorded at '+recorded.isoformat()+'. '
        header = body.split('\n',1)[1].split('\n',1)[0] if '\n' in body else ''
        fact += header[:1000]
        edge = EntityEdge(uuid=identity('source-record-edge',record_id),source_node_uuid=source_node_id,
            target_node_uuid=node_id,group_id=project,name='HAS_CACHED_EVIDENCE',fact=fact,created_at=now,
            valid_at=recorded,episodes=[episode_id],attributes={'source_kind':source_kind})
        mentions = [EpisodicEdge(uuid=identity('source-record-mention',record_id+target),
            source_node_uuid=episode_id,target_node_uuid=target,group_id=project,created_at=now)
            for target in (source_node_id,node_id)]
        await add_nodes_and_edges_bulk(client.driver,[episode],mentions,[source,node],[edge],client.embedder)
        if graph._driver is not None:
            await graph._driver.execute_query('CHECKPOINT')
        with graph._manifest:
            graph._manifest.execute('INSERT OR REPLACE INTO ingested VALUES(?,?,?,?)',
                (record_id,project,episode_id,time.time()))
        progress({'phase':'cached_business_sources','completed':index+1,'total':len(pending)})
    return {'episodes_added':len(pending)}
