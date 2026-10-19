import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from spark_intelligence.policy import Router, CircuitBreaker, parse_envelope, Improvements


class PolicyTests(unittest.TestCase):
    def test_complexity_and_declared_resource_budget_affect_local_selection(self):
        router=Router([{'id':'small','local':True,'available':True,'context':8192,'quality_tier':1,'additional_memory_mb':100}, {'id':'large','local':True,'available':True,'context':8192,'quality_tier':3,'additional_memory_mb':2000}])
        self.assertEqual(router.select('Prove this theorem step by step and analyze the algorithm',memory_limit_mb=3000)['id'],'large')
        self.assertEqual(router.select('Prove this theorem step by step and analyze the algorithm',memory_limit_mb=500)['id'],'small')

    def test_router_never_silently_uses_cloud_or_ignores_context_budget(self):
        router=Router([{'id':'local','local':True,'available':False,'context':2048}, {'id':'cloud','local':False,'available':True,'context':8192}])
        with self.assertRaises(ValueError):router.select('hello')
        self.assertEqual(router.select('hello',allow_cloud=True)['id'],'cloud')
        with self.assertRaises(ValueError):router.select('x'*40000,allow_cloud=True)

    def test_circuit_breaker_stops_retry_and_recovers_after_cooldown(self):
        now=[0]
        breaker=CircuitBreaker(clock=lambda:now[0],threshold=2,cooldown=30)
        breaker.failure('offline');breaker.failure('offline')
        self.assertFalse(breaker.allowed())
        now[0]=31
        self.assertTrue(breaker.allowed())
        breaker.success()
        self.assertEqual(breaker.status()['state'],'healthy')

    def test_repeated_connection_failures_increase_bounded_recovery_backoff(self):
        now=[0]
        breaker=CircuitBreaker(clock=lambda:now[0],threshold=2,cooldown=30)
        breaker.failure('offline');breaker.failure('offline')
        now[0]=31
        breaker.failure('offline')
        now[0]=62
        self.assertFalse(breaker.allowed())
        now[0]=92
        self.assertTrue(breaker.allowed())

    def test_react_parser_rejects_ambiguous_duplicate_and_non_json_actions(self):
        self.assertEqual(parse_envelope('{"action":"get_system_status","action_input":{}}')['action'],'get_system_status')
        for value in ['{"action":"a","action":"b"}', '{"action":"a","final":"done"}', '{"final":NaN}', '```json\n{}\n```']:
            with self.assertRaises(ValueError):parse_envelope(value)

    def test_improvements_require_measured_non_regressing_evidence_and_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            improvements=Improvements(directory)
            candidate=improvements.propose('general','Use concise answers','prompt')
            with self.assertRaises(ValueError):improvements.activate('general',candidate['id'],approved=True)
            result=improvements.evaluate('general',candidate['id'],[{'expected':2,'baseline':2,'candidate':1}])
            self.assertEqual(result['status'],'rejected')
            empty=improvements.propose('general','Unproven candidate','prompt')
            self.assertEqual(improvements.evaluate('general',empty['id'],[{'expected':2,'baseline':0,'candidate':0}])['status'],'rejected')
            with self.assertRaises(ValueError):improvements.activate('general',candidate['id'],approved=True)
            candidate=improvements.propose('general','Use verified examples','prompt')
            improvements.evaluate('general',candidate['id'],[{'expected':2,'baseline':1,'candidate':2}])
            with self.assertRaises(ValueError):improvements.activate('general',candidate['id'],approved=False)
            self.assertEqual(improvements.activate('general',candidate['id'],approved=True)['status'],'active')
            self.assertEqual(improvements.rollback('general',candidate['id'],approved=True)['status'],'rolled_back')
            improvements.close()
