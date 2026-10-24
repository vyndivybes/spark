import asyncio
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from spark_graphiti_mcp import paced_gemini_embedder, structured_groq_client, GraphitiUnavailable


class EmbeddingTests(unittest.IsolatedAsyncioTestCase):
    async def test_extraction_enforces_values_schema_and_bounds_reasoning_budget(self):
        from pydantic import BaseModel, ValidationError
        class Response(BaseModel):
            edges: list[str]
        output = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"edges":["VAOS uses Vyndi OS references"]}'))])
        create = AsyncMock(return_value=output)
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        client.with_options = lambda **kwargs: client
        class Base:
            def __init__(self, config):
                self.model, self.max_tokens, self.client = config.model, 16384, client
        modules = {'graphiti_core.llm_client.groq_client':SimpleNamespace(GroqClient=Base),
                   'groq':SimpleNamespace(RateLimitError=type('QuotaError',(Exception,),{}), APITimeoutError=TimeoutError,
                                         BadRequestError=type('StructuredError',(Exception,),{}))}
        with patch.dict(sys.modules, modules), patch.object(asyncio,'sleep',new=AsyncMock()):
            adapter = structured_groq_client(SimpleNamespace(model='openai/gpt-oss-20b'))
            result = await adapter._generate_response([SimpleNamespace(role='user',content='Extract facts.')], Response, 16384)
            self.assertEqual(result['edges'], ['VAOS uses Vyndi OS references'])
            self.assertEqual(create.await_args.kwargs['response_format']['json_schema']['strict'], True)
            self.assertEqual(create.await_args.kwargs['max_completion_tokens'], 4096)
            self.assertEqual(create.await_args.kwargs['reasoning_effort'], 'low')
            output.choices[0].message.content = '{"type":"object","properties":{"edges":{"type":"array"}}}'
            with self.assertRaises(ValidationError):
                await adapter._generate_response([SimpleNamespace(role='user',content='Extract facts.')], Response)

    async def test_provider_rejection_can_recover_valid_values_but_never_a_schema_copy(self):
        from pydantic import BaseModel
        class Response(BaseModel):
            edges: list[str]
        class Rejection(Exception):
            body = {'error':{'code':'json_validate_failed','failed_generation':'{"edges":["VAOS uses Vyndi OS"],"type":"object"}'}}
        create = AsyncMock(side_effect=Rejection())
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        client.with_options = lambda **kwargs: client
        class Base:
            def __init__(self, config):
                self.model, self.max_tokens, self.client = config.model, 4096, client
        modules = {'graphiti_core.llm_client.groq_client':SimpleNamespace(GroqClient=Base),
                   'groq':SimpleNamespace(BadRequestError=Rejection, RateLimitError=type('Quota',(Exception,),{}), APITimeoutError=TimeoutError)}
        with patch.dict(sys.modules, modules), patch.object(asyncio,'sleep',new=AsyncMock()):
            adapter = structured_groq_client(SimpleNamespace(model='openai/gpt-oss-20b'))
            self.assertEqual(await adapter._generate_response([SimpleNamespace(role='user',content='Extract.')], Response), {'edges':['VAOS uses Vyndi OS']})
            Rejection.body['error']['failed_generation'] = '{"type":"object","properties":{"edges":{"type":"array"}}}'
            with self.assertRaises(GraphitiUnavailable):
                await adapter._generate_response([SimpleNamespace(role='user',content='Extract.')], Response)

    async def test_cache_reuses_vectors_after_restart_and_batches_keep_the_same_order(self):
        provider = AsyncMock(side_effect=[[1.,0.],[0.,1.]])
        class Base:
            def __init__(self, config):
                self.config = config
            async def create(self, value):
                return await provider(value)
        class Error(Exception):
            code = 429
        modules = {'graphiti_core.embedder.gemini':SimpleNamespace(GeminiEmbedder=Base),
                   'google.genai.errors':SimpleNamespace(ClientError=Error)}
        config = SimpleNamespace(embedding_model='fixture', embedding_dim=2)
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(sys.modules, modules), patch.object(asyncio, 'sleep', new=AsyncMock()):
                first = paced_gemini_embedder(config, Path(folder)/'cache.sqlite3')
                self.assertEqual(await first.create(['VAOS']), [1.,0.])
                restarted = paced_gemini_embedder(config, Path(folder)/'cache.sqlite3')
                self.assertEqual(await restarted.create_batch(['VAOS','VEDM']), [[1.,0.],[0.,1.]])
                self.assertEqual(provider.await_count, 2)

    async def test_short_quota_reset_retries_once_and_never_caches_a_failure(self):
        class Error(Exception):
            code = 429
        provider = AsyncMock(side_effect=Error('Please retry in 0s.'))
        class Base:
            def __init__(self, config):
                self.config = config
            async def create(self, value):
                return await provider(value)
        modules = {'graphiti_core.embedder.gemini':SimpleNamespace(GeminiEmbedder=Base),
                   'google.genai.errors':SimpleNamespace(ClientError=Error)}
        config = SimpleNamespace(embedding_model='fixture', embedding_dim=2)
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(sys.modules, modules), patch.object(asyncio, 'sleep', new=AsyncMock()):
                embedder = paced_gemini_embedder(config, Path(folder)/'cache.sqlite3')
                with self.assertRaises(GraphitiUnavailable):
                    await embedder.create(['VAOS'])
                self.assertEqual(provider.await_count, 2)
                provider.side_effect = None
                provider.return_value = [1.,0.]
                self.assertEqual(await embedder.create(['VAOS']), [1.,0.])


if __name__ == '__main__':
    unittest.main()
