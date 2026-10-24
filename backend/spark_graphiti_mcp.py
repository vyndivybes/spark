"""Graphiti temporal knowledge graph sidecar, exposed as a read-only MCP service.

Runs the real Apache-2.0 `graphiti-core` package against an embedded Kuzu graph
(no database server) and answers from a temporal graph that SPARK's flat
`Memory` table cannot represent: facts carry `valid_at`/`invalid_at`, and a
contradicting episode invalidates the earlier fact instead of deleting it.

SPARK's backend never accepts executable paths from a socket. `start-spark.ps1`
is the only place this process is registered, through `SPARK_MCP_SERVERS`.

This process reads SPARK's own SQLite stores in read-only mode and writes only
to its own Kuzu database and ingest manifest. It never mutates SPARK state.
"""
import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Graphiti reports anonymous usage to us.i.posthog.com unless this is off.
# SPARK ships no tracking, so the kill switch is set before the import.
os.environ.setdefault('GRAPHITI_TELEMETRY_ENABLED', '0')

MAX_EPISODES_PER_REFRESH = 12
MAX_BODY = 4000
MAX_FACTS = 8
MAX_FACT_CHARS = 600
MAX_QUERY_CHARS = 400
MAX_ENTITY_CHARS = 120
MAX_GROUP_EDGES = 400
GRAPH_BUFFER_BYTES = 256 * 1024 * 1024
PROJECT = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')


class GraphitiUnavailable(RuntimeError):
    """Raised for any condition the caller should report as a plain sentence."""


class GraphitiRateLimited(GraphitiUnavailable):
    """Stop the batch at the first provider quota response."""


def strict_schema(schema):
    """Copy a Pydantic schema into Groq's closed, required-field form."""
    if isinstance(schema, list):
        return [strict_schema(value) for value in schema]
    if not isinstance(schema, dict):
        return schema
    result = {key:strict_schema(value) for key,value in schema.items() if key != 'default'}
    if result.get('type') == 'object' and 'properties' in result:
        result['additionalProperties'] = False
        result['required'] = list(result['properties'])
    return result


def structured_groq_client(config, cache_path=None):
    """Keep Graphiti's LLM interface, enforcing response values at the API boundary."""
    import groq
    from graphiti_core.llm_client.groq_client import GroqClient

    class StructuredGroqClient(GroqClient):
        def __init__(self, config):
            super().__init__(config=config)
            self.request_lock = asyncio.Lock()
            self.next_request = 0
            if cache_path is not None:
                db = sqlite3.connect(cache_path)
                try:
                    with db:
                        db.execute('CREATE TABLE IF NOT EXISTS responses(key TEXT PRIMARY KEY,body TEXT)')
                finally:
                    db.close()

        async def _generate_response(self, messages, response_model=None, max_tokens=None,
                                     model_size=None, *, model=None):
            key = hashlib.sha256(json.dumps([model or self.model,
                [(message.role,message.content) for message in messages],
                response_model.model_json_schema() if response_model else None],sort_keys=True).encode()).hexdigest()
            async with self.request_lock:
                if cache_path is not None:
                    db = sqlite3.connect(cache_path)
                    try:
                        row = db.execute('SELECT body FROM responses WHERE key=?',(key,)).fetchone()
                    finally:
                        db.close()
                    if row:
                        return json.loads(row[0])
                await asyncio.sleep(max(0,self.next_request-time.monotonic()))
                value = await self._request_response(messages,response_model,max_tokens,model=model)
                if cache_path is not None:
                    db = sqlite3.connect(cache_path)
                    try:
                        with db:
                            db.execute('INSERT OR REPLACE INTO responses VALUES(?,?)',(key,json.dumps(value)))
                    finally:
                        db.close()
                return value

        async def _request_response(self, messages, response_model=None, max_tokens=None, *, model=None):
            selected = model or self.model
            options = {}
            response_format = {'type':'json_object'}
            if selected in ('openai/gpt-oss-20b', 'openai/gpt-oss-120b'):
                options = {'reasoning_effort':'low', 'reasoning_format':'hidden'}
                if response_model is not None:
                    response_format = {'type':'json_schema', 'json_schema':{
                        'name':response_model.__name__, 'strict':True,
                        'schema':strict_schema(response_model.model_json_schema())}}
            for attempt in range(2):
                try:
                    response = await self.client.with_options(timeout=30, max_retries=0).chat.completions.create(
                    model=selected,
                    messages=[{'role':message.role, 'content':message.content} for message in messages],
                    temperature=0, max_completion_tokens=min(max_tokens or self.max_tokens, 4096),
                        response_format=response_format, **options)
                    break
                except groq.BadRequestError as error:
                    details = error.body.get('error', {}) if isinstance(error.body, dict) else {}
                    raw = details.get('failed_generation') if isinstance(details, dict) else None
                    # Groq can reject an otherwise complete values object for an
                    # extra schema keyword. Recover only actual model fields that
                    # independently pass Pydantic validation, never a schema copy.
                    if response_model is not None and raw and details.get('code') == 'json_validate_failed':
                        try:
                            generated = json.loads(raw)
                            if not isinstance(generated,dict) or not set(generated).intersection(response_model.model_fields):
                                raise ValueError('No response values.')
                            validated = response_model.model_validate(generated).model_dump(mode='json')
                        except (ValueError, TypeError):
                            raise GraphitiUnavailable('Groq returned invalid extraction values.') from None
                        self.next_request = time.monotonic()+(sum(len(message.content) for message in messages)+len(raw))/4*60/7000
                        return validated
                    raise GraphitiUnavailable('Groq rejected the structured extraction request.') from None
                except groq.RateLimitError as error:
                    details = error.body.get('error', {}) if isinstance(error.body, dict) else {}
                    message = details.get('message', '') if isinstance(details, dict) else ''
                    delay = re.search(r'Please try again in ([0-9.]+)s',message)
                    if not attempt and delay and float(delay[1]) <= 60:
                        await asyncio.sleep(float(delay[1])+1)
                        continue
                    numbers = re.findall(r'(?:Limit|Requested|Used)\s*[:=]?\s*[\d,.]+|(?:tokens per minute|tokens per day)|Please try again in [\d.hms ]+', message, re.I)
                    raise GraphitiRateLimited('Groq extraction rate limit reached. ' + '; '.join(numbers)) from None
                except groq.APITimeoutError:
                    raise GraphitiUnavailable('Groq extraction request timed out.') from None
            usage = getattr(response,'usage',None)
            tokens = getattr(usage,'total_tokens',0) or 1000
            self.next_request = time.monotonic()+tokens*60/7000
            value = json.loads(response.choices[0].message.content or '{}')
            if response_model is not None:
                response_model.model_validate(value)
            return value

    return StructuredGroqClient(config=config)


def paced_gemini_embedder(config, cache_path):
    """Reuse embeddings and stay below the provider's 100 requests/minute tier."""
    from graphiti_core.embedder.gemini import GeminiEmbedder
    from google.genai.errors import ClientError

    class PacedGeminiEmbedder(GeminiEmbedder):
        def __init__(self):
            super().__init__(config=config)
            self.request_lock = asyncio.Lock()
            self.next_request = 0
            db = sqlite3.connect(cache_path)
            try:
                with db:
                    db.execute('CREATE TABLE IF NOT EXISTS embeddings(key TEXT PRIMARY KEY,body TEXT)')
            finally:
                db.close()

        async def create(self, input_data):
            key = hashlib.sha256(json.dumps([config.embedding_model, config.embedding_dim, input_data], sort_keys=True).encode()).hexdigest()
            async with self.request_lock:
                db = sqlite3.connect(cache_path)
                try:
                    row = db.execute('SELECT body FROM embeddings WHERE key=?',(key,)).fetchone()
                    if row:
                        return json.loads(row[0])
                    for attempt in range(2):
                        await asyncio.sleep(max(0, self.next_request-time.monotonic()))
                        self.next_request = time.monotonic()+.8
                        try:
                            vector = await super().create(input_data)
                            break
                        except ClientError as error:
                            delay = re.search(r'Please retry in ([0-9.]+)s', str(error))
                            if error.code != 429 or attempt or not delay or float(delay[1]) > 60:
                                raise GraphitiUnavailable('Gemini embeddings unavailable; provider quota or request failed.') from None
                            self.next_request = time.monotonic()+float(delay[1])+1
                    with db:
                        db.execute('INSERT OR REPLACE INTO embeddings VALUES(?,?)',(key,json.dumps(vector)))
                    return vector
                finally:
                    db.close()

        async def create_batch(self, input_data_list):
            return [await self.create([item]) for item in input_data_list]

    return PacedGeminiEmbedder()


def bounded_kuzu_driver(path):
    """Adapt pinned graphiti-core 0.31.x without Kuzu's 80%-of-RAM default.

    Only construction differs from upstream KuzuDriver. Its schema, operations
    and query implementation remain upstream's Apache-2.0 implementation.
    """
    import kuzu
    from graphiti_core.driver import kuzu_driver as upstream

    class BoundedDriver(upstream.KuzuDriver):
        def __init__(self):
            self._database = ''
            self.db = kuzu.Database(str(path), buffer_pool_size=GRAPH_BUFFER_BYTES,
                                    max_num_threads=2, max_db_size=2 * 1024**3)
            self.setup_schema()
            self.client = kuzu.AsyncConnection(self.db, max_concurrent_queries=1)
            for attribute, operation in (
                ('entity_node', 'EntityNode'), ('entity_edge', 'EntityEdge'),
                ('episode_node', 'EpisodeNode'), ('episodic_edge', 'EpisodicEdge'),
                ('community_node', 'CommunityNode'), ('community_edge', 'CommunityEdge'),
                ('has_episode_edge', 'HasEpisodeEdge'), ('next_episode_edge', 'NextEpisodeEdge'),
                ('saga_node', 'SagaNode'), ('search', 'Search'), ('graph', 'GraphMaintenance'),
            ):
                setattr(self, f'_{attribute}_ops', getattr(upstream, f'Kuzu{operation}Operations')())

    return BoundedDriver()


def _project(value):
    if not isinstance(value, str) or not PROJECT.fullmatch(value) or len(value) > 60:
        raise GraphitiUnavailable('Invalid project identifier.')
    return value


def _read_only(path):
    """Open a SQLite file without write access; absent files are not an error."""
    resolved = Path(path)
    if not resolved.exists():
        return None
    if resolved.is_symlink():
        raise GraphitiUnavailable('Linked intelligence storage is prohibited.')
    return sqlite3.connect(f'file:{resolved.as_posix()}?mode=ro', uri=True, timeout=5)


class TemporalGraph:
    """Owns the Kuzu database, the graphiti client and the ingest manifest."""

    def __init__(self, workspace, directory, *, llm_model=None):
        self.workspace = Path(workspace)
        self.directory = Path(directory)
        if self.directory.is_symlink():
            raise GraphitiUnavailable('Linked graph storage is prohibited.')
        self.directory.mkdir(parents=True, exist_ok=True)
        self.llm_model = llm_model or os.environ.get('SPARK_GRAPHITI_MODEL', 'openai/gpt-oss-120b')
        self._graphiti = None
        self._driver = None
        self._manifest = sqlite3.connect(self.directory/'ingest.sqlite3', timeout=10)
        self._manifest.execute('CREATE TABLE IF NOT EXISTS ingested(record_id TEXT PRIMARY KEY,project TEXT,episode_uuid TEXT,ingested REAL)')
        self._manifest.commit()

    # -- construction -----------------------------------------------------
    async def _client(self):
        if self._graphiti is not None:
            return self._graphiti
        groq_key = os.environ.get('GROQ_API_KEY', '')
        gemini_key = os.environ.get('GEMINI_API_KEY', '')
        if not groq_key or not gemini_key:
            raise GraphitiUnavailable('Graph extraction needs GROQ_API_KEY and GEMINI_API_KEY in backend/.env.')
        try:
            from graphiti_core import Graphiti
            from graphiti_core.cross_encoder.gemini_reranker_client import GeminiRerankerClient
            from graphiti_core.driver.driver import GraphProvider
            from graphiti_core.driver.kuzu_driver import KuzuDriver
            from graphiti_core.embedder.gemini import GeminiEmbedder, GeminiEmbedderConfig
            from graphiti_core.graph_queries import get_fulltext_indices, get_range_indices
            from graphiti_core.llm_client.groq_client import GroqClient, LLMConfig
        except ImportError:
            raise GraphitiUnavailable('Install the optional graph stack: pip install -r requirements-graphiti.txt') from None

        import warnings
        with warnings.catch_warnings():
            # Kuzu is deprecated upstream; the message is noise on every start.
            warnings.simplefilter('ignore', DeprecationWarning)
            driver = bounded_kuzu_driver(self.directory/'graph.kuzu')
        # graphiti-core 0.31.1: KuzuDriver never assigns GraphDriver._database,
        # but _resolve_request_scope reads it for any non-None group_id. Kuzu has
        # no per-group databases (clone() is a no-op) and isolates by a group_id
        # column, so the default-database sentinel is the correct value.
        driver._database = ''
        await self._ensure_indices(driver, get_range_indices(GraphProvider.KUZU) + get_fulltext_indices(GraphProvider.KUZU))
        self._graphiti = Graphiti(
            graph_driver=driver,
            llm_client=structured_groq_client(LLMConfig(api_key=groq_key, model=self.llm_model, max_tokens=8192), self.directory/'extraction-cache.sqlite3'),
            embedder=paced_gemini_embedder(GeminiEmbedderConfig(api_key=gemini_key, embedding_model='gemini-embedding-001'), self.directory/'embeddings.sqlite3'),
            cross_encoder=GeminiRerankerClient(config=LLMConfig(api_key=gemini_key)),
        )
        self._driver = driver
        return self._graphiti

    async def _ensure_indices(self, driver, statements):
        """graphiti-core 0.31.1: KuzuDriver.build_indices_and_constraints() is a
        no-op that shadows the working ops implementation, so the fulltext
        indices its own search path requires are never created. Create them here,
        one statement at a time so an already-present index is tolerated."""
        for statement in statements:
            try:
                await driver.execute_query(statement)
            except Exception:
                pass

    async def _await(self, coroutine):
        """Translate any graphiti/driver/HTTP failure into one plain sentence.

        FastMCP invokes tools inside a running event loop, so these coroutines
        are awaited rather than driven with asyncio.run()."""
        try:
            return await coroutine
        except GraphitiUnavailable:
            raise
        except Exception as error:
            raise GraphitiUnavailable(f'Graphiti could not complete the request ({type(error).__name__}).') from None

    # -- ingestion --------------------------------------------------------
    def _pending(self, project, limit):
        """Uningested SPARK records, oldest first, as (record_id, body, when)."""
        already = {row[0] for row in self._manifest.execute('SELECT record_id FROM ingested WHERE project=?', (project,))}
        found = []
        memory = _read_only(self.workspace/'intelligence'/'memory.sqlite3')
        if memory is not None:
            try:
                rows = memory.execute('SELECT id,body,source,kind,created FROM memories WHERE project=? AND expires>? ORDER BY created', (project, time.time())).fetchall()
            except sqlite3.Error:
                rows = []
            finally:
                memory.close()
            for record_id, body, source, kind, created in rows:
                if record_id in already:
                    continue
                found.append((f'memory:{record_id}', f'[{kind}] {body} (source: {source})', created, record_id))
        knowledge = _read_only(self.workspace/'knowledge'/project/'sources.sqlite3')
        if knowledge is not None:
            try:
                rows = knowledge.execute('SELECT p.doc_id,p.title,p.body,d.uploaded FROM passages p JOIN documents d ON d.id=p.doc_id LIMIT 400').fetchall()
            except sqlite3.Error:
                rows = []
            finally:
                knowledge.close()
            for doc_id, title, body, uploaded in rows:
                record_id = f'{doc_id}:{hashlib.sha256(body.encode()).hexdigest()[:16]}'
                if record_id in already:
                    continue
                when = _epoch(uploaded)
                found.append((f'document:{record_id}', f'[{title}] {body[:MAX_BODY]}', when, record_id))
        bridge = _read_only(self.workspace/'knowledge-bridge'/'episodes.sqlite3')
        if bridge is not None:
            try:
                rows = bridge.execute('SELECT record_id,body,created FROM episodes WHERE project=? ORDER BY created', (project,)).fetchall()
            finally:
                bridge.close()
            for record_id, body, created in rows:
                if record_id not in already:
                    found.append((record_id, body, created, record_id))
        found.sort(key=lambda item: _epoch(item[2]))
        return found[:limit]

    async def refresh(self, project, *, time_limit_seconds=120, combined_extraction=False):
        project = _project(project)
        graphiti = await self._client()
        from graphiti_core.nodes import EpisodeType
        pending = self._pending(project, MAX_EPISODES_PER_REFRESH)
        ingested, failures = 0, 0
        errors = []
        deadline = time.monotonic() + time_limit_seconds
        timed_out = False
        for source_id, body, when, record_id in pending:
            remaining_seconds = deadline - time.monotonic()
            if remaining_seconds <= 0:
                timed_out = True
                break
            try:
                # graphiti-core 0.31.1: add_episode(uuid=...) is documented as
                # "optional uuid of the episode" but is implemented as a lookup of
                # an EXISTING episode, so a caller-supplied uuid for a new record
                # always raises NodeNotFoundError. Idempotency comes from the
                # ingest manifest instead, which is written on success below.
                if combined_extraction:
                    from graphiti_core.utils.bulk_utils import RawEpisode
                    result = await asyncio.wait_for(self._await(graphiti.add_episode_bulk([
                        RawEpisode(name=source_id[:200], content=body[:MAX_BODY],
                            source_description='SPARK local intelligence record; preserve source limitations and release holds.',
                            reference_time=_as_datetime(when), source=EpisodeType.text)],
                        group_id=project, use_combined_extraction=True)), timeout=remaining_seconds)
                    episode = result.episodes[0]
                else:
                    result = await asyncio.wait_for(self._await(graphiti.add_episode(
                    name=source_id[:200],
                    episode_body=body[:MAX_BODY],
                    source_description='SPARK local intelligence record',
                    reference_time=_as_datetime(when),
                    source=EpisodeType.text,
                    group_id=project,
                    # Bridge records are self-contained source excerpts. Avoid
                    # replaying unrelated cached episodes into every extraction;
                    # entity/edge resolution still queries the temporal graph.
                    previous_episode_uuids=[] if source_id.startswith('bridge:') else None,
                    )), timeout=remaining_seconds)
                    episode = getattr(result, 'episode', None)
            except asyncio.TimeoutError:
                timed_out = True
                break
            except GraphitiRateLimited as error:
                failures += 1
                errors.append(str(error))
                break
            except Exception as error:
                failures += 1
                # _await exposes a bounded, credential-free diagnosis. Keep
                # raw provider responses and episode text out of tool results.
                if isinstance(error, GraphitiUnavailable) and str(error) not in errors:
                    errors.append(str(error)[:200])
                continue
            ingested += 1
            with self._manifest:
                self._manifest.execute('INSERT OR REPLACE INTO ingested VALUES (?,?,?,?)',
                                       (record_id, project, str(getattr(episode, 'uuid', '') or ''), time.time()))
        remaining = len(self._pending(project, 100000))
        return {'project': project, 'episodes_added': ingested, 'episodes_failed': failures,
                'remaining': remaining, 'batch_limit': MAX_EPISODES_PER_REFRESH,
                'time_limit_seconds': time_limit_seconds, 'time_limit_reached': timed_out,
                'errors': errors[:3],
                'note': 'Source-labelled reference records and model-extracted associations; not independently verified.'}

    # -- queries ----------------------------------------------------------
    async def search(self, project, question, limit=MAX_FACTS):
        project = _project(project)
        if not isinstance(question, str) or not 3 <= len(question.strip()) <= MAX_QUERY_CHARS:
            raise GraphitiUnavailable(f'Ask a question of 3 to {MAX_QUERY_CHARS} characters.')
        graphiti = await self._client()
        # graphiti.search() returns facts (edges) only. An episode whose entities
        # the extractor related to nothing yields no edge, so its content would be
        # invisible; search_ returns nodes too and keeps those episodes reachable.
        from graphiti_core.search.search_config_recipes import COMBINED_HYBRID_SEARCH_RRF
        from graphiti_core.search.search_filters import SearchFilters
        results = await self._await(graphiti.search_(
            query=question.strip(), config=COMBINED_HYBRID_SEARCH_RRF, group_ids=[project],
            search_filter=SearchFilters()))
        bound = max(1, min(MAX_FACTS, int(limit)))
        return {'project': project, 'question': question.strip(),
                'facts': [_fact(edge) for edge in results.edges][:bound],
                'entities': [_entity(node) for node in results.nodes][:bound],
                'episode_count': len(results.episodes),
                'note': 'Source-labelled inventory relationships and model-extracted associations; not independently verified.'}

    async def timeline(self, project, entity):
        project = _project(project)
        if not isinstance(entity, str) or not 1 <= len(entity.strip()) <= MAX_ENTITY_CHARS:
            raise GraphitiUnavailable(f'Name an entity in at most {MAX_ENTITY_CHARS} characters.')
        graphiti = await self._client()
        from graphiti_core.edges import EntityEdge
        from graphiti_core.search.search_config_recipes import NODE_HYBRID_SEARCH_RRF
        from graphiti_core.search.search_filters import SearchFilters
        wanted = entity.strip()
        results = await self._await(graphiti.search_(query=wanted, config=NODE_HYBRID_SEARCH_RRF,
                                                     group_ids=[project], search_filter=SearchFilters()))
        lowered = wanted.lower()
        matches = [node for node in results.nodes if lowered in (getattr(node, 'name', '') or '').lower()]
        matches = (matches or list(results.nodes))[:3]
        endpoints = {getattr(node, 'uuid', None) for node in matches} - {None}
        # The node recipe returns nodes only, so an entity resolved by name would
        # otherwise report an empty history. Both endpoints are tested because the
        # Kuzu edge match graphiti generates is source-directional.
        edges = await self._await(EntityEdge.get_by_group_ids(self._driver, [project], limit=MAX_GROUP_EDGES))
        facts = [_fact(edge) for edge in edges
                 if {getattr(edge, 'source_node_uuid', None), getattr(edge, 'target_node_uuid', None)} & endpoints]
        facts.sort(key=lambda item: (item['invalid_at'] is not None, item['valid_at'] or ''))
        return {'project': project, 'entity': wanted,
                'entities': [_entity(node) for node in matches],
                'facts': facts[:MAX_FACTS],
                'fact_count': len(facts),
                'invalidated_count': sum(1 for item in facts if item['invalid_at'] is not None),
                'note': 'invalid_at marks a fact a later episode contradicted; it is retained, not deleted.'}

    def status(self):
        configured = bool(os.environ.get('GROQ_API_KEY')) and bool(os.environ.get('GEMINI_API_KEY'))
        # A readiness query must not import the full inference stack on the MCP
        # event loop. Native graph initialization happens only for graph work.
        installed = all(importlib.util.find_spec(name) is not None
                        for name in ('graphiti_core', 'kuzu'))
        counts = {}
        for project_row in self._manifest.execute('SELECT project,count(*) FROM ingested GROUP BY project'):
            counts[project_row[0]] = project_row[1]
        return {'backend': 'graphiti-core + embedded Kuzu', 'installed': installed, 'credentials_configured': configured,
                'model': self.llm_model, 'telemetry': os.environ.get('GRAPHITI_TELEMETRY_ENABLED', '0'),
                'episodes_ingested_by_project': counts, 'graph_path': str(self.directory/'graph.kuzu')}


def _fact(edge):
    return {'fact': (getattr(edge, 'fact', '') or '')[:MAX_FACT_CHARS],
            'source_kind':(getattr(edge,'attributes',None) or {}).get('source_kind','model-extracted'),
            'name': getattr(edge, 'name', None),
            'valid_at': _iso(getattr(edge, 'valid_at', None)),
            'invalid_at': _iso(getattr(edge, 'invalid_at', None)),
            'expired_at': _iso(getattr(edge, 'expired_at', None)),
            'episodes': list(getattr(edge, 'episodes', []) or [])[:3]}


def _entity(node):
    return {'name': getattr(node, 'name', None),
            'source_kind':(getattr(node,'attributes',None) or {}).get('source_kind','model-extracted'),
            'summary': (getattr(node, 'summary', '') or '')[:MAX_FACT_CHARS],
            'uuid': getattr(node, 'uuid', None)}


def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else (str(value) if value else None)


def _as_datetime(value):
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)) and value > 0:
        return datetime.fromtimestamp(value, tz=timezone.utc)
    return datetime.now(timezone.utc)


def _parse_uploaded(value):
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None
    return None


def _epoch(value):
    """Memories store epoch floats while knowledge passages store ISO timestamps;
    ordering a mixed refresh batch needs one comparable scale."""
    if isinstance(value, str):
        value = _parse_uploaded(value)
    if isinstance(value, datetime):
        return value.timestamp() if value.tzinfo else value.replace(tzinfo=timezone.utc).timestamp()
    if isinstance(value, (int, float)) and value > 0:
        return float(value)
    return 0.0


def main(argv=None):
    # NumPy's Windows DLL initialization can deadlock when its first import is
    # inside a FastMCP request after AnyIO's stdio worker threads have started.
    # Load that native dependency before starting the server event loop.
    if os.name == 'nt' and importlib.util.find_spec('numpy') is not None:
        os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
        importlib.import_module('numpy')
    # MCP transports inherit only a minimal environment. Load this checkout's
    # private provider configuration in the sidecar, never in tool arguments.
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).with_name('.env'))
    parser = argparse.ArgumentParser(description='SPARK Graphiti temporal graph MCP service')
    parser.add_argument('--workspace', required=True, help='SPARK workspace root (read-only source of records)')
    parser.add_argument('--db', required=True, help='Directory for the Kuzu graph and ingest manifest')
    parser.add_argument('--model', default=None, help='Groq chat model used for fact extraction')
    arguments = parser.parse_args(argv)

    graph = TemporalGraph(arguments.workspace, arguments.db, llm_model=arguments.model)

    from mcp.server.fastmcp import FastMCP
    server = FastMCP('spark-graphiti')

    @server.tool()
    async def search_temporal_facts(question: str, project: str, limit: int = MAX_FACTS) -> dict:
        """Search SPARK's temporal knowledge graph for facts, including when each became valid and whether a later record contradicted it."""
        try:
            return await graph.search(project, question, limit)
        except GraphitiUnavailable as error:
            return {'facts': [], 'entities': [], 'error': str(error)}

    @server.tool()
    async def get_entity_timeline(entity: str, project: str) -> dict:
        """Return what SPARK knows about one entity over time, separating current facts from invalidated ones."""
        try:
            return await graph.timeline(project, entity)
        except GraphitiUnavailable as error:
            return {'facts': [], 'entities': [], 'error': str(error)}

    @server.tool()
    async def refresh_project_graph(project: str) -> dict:
        """Ingest new SPARK memory and knowledge records into the temporal graph. Reads SPARK storage read-only and writes only the graph."""
        try:
            return await graph.refresh(project)
        except GraphitiUnavailable as error:
            return {'episodes_added': 0, 'error': str(error)}

    @server.tool()
    async def graph_status() -> dict:
        """Report whether the temporal graph backend, credentials and ingested episode counts are available."""
        try:
            return graph.status()
        except GraphitiUnavailable as error:
            return {'installed': False, 'error': str(error)}

    server.run(transport='stdio')
    return 0


if __name__ == '__main__':
    sys.exit(main())
