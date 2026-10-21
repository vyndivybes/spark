import json
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from spark_repo_upgrade import analysis_context
from spark_evolution import generate_json
from spark_maintenance import MaintenanceError
from spark_groq import classify_groq_http_error


class BudgetTests(unittest.IsolatedAsyncioTestCase):
    def test_large_inventory_and_unicode_sources_fit_without_mutating_evidence(self):
        evidence={'inventory':[f'src/module_{i}.py' for i in range(5000)],
            'sources':[{'path':f'src/module_{i}.py','sha256':'a'*64,'content':'工程 "quoted"\\line\n'*4000} for i in range(16)],
            'limitations':['Static source only.']}
        original=json.dumps(evidence)
        result=analysis_context(evidence,'Review behavior',['backend/example.py'])
        self.assertLessEqual(len(json.dumps(result,ensure_ascii=False).encode()),7000)
        self.assertTrue(result['sources'])
        self.assertTrue(all(s['excerpt_truncated'] for s in result['sources']))
        self.assertEqual(json.dumps(evidence),original)
        self.assertIn('bounded source excerpts',' '.join(result['limitations']))

    async def test_json_generation_reserves_bounded_output_and_rejects_oversize_before_network(self):
        reply={'choices':[{'finish_reason':'stop','message':{'content':'{"summary":"OK","opportunities":[]}'}}]}
        with patch('spark_groq.GroqClient._http',new_callable=AsyncMock,return_value=reply) as http,patch.dict('os.environ',{'GROQ_API_KEY':'test-only'}):
            value=await generate_json('Return JSON',{'source':'small'})
            self.assertEqual(value['summary'],'OK')
            self.assertEqual(http.await_args.kwargs['body']['max_completion_tokens'],2048)
            http.reset_mock()
            with self.assertRaisesRegex(MaintenanceError,'no request was sent'):
                await generate_json('Return JSON',{'source':'x'*20000})
            http.assert_not_awaited()
            reply['choices'][0]['finish_reason']='length'
            with self.assertRaisesRegex(MaintenanceError,'reached its budget'):
                await generate_json('Return JSON',{})

    def test_413_explains_size_and_does_not_suggest_outage(self):
        error=str(classify_groq_http_error('chat',413))
        self.assertIn('size/token budget',error)
        self.assertNotIn('dashboard',error)
