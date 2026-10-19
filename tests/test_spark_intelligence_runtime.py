"""Acceptance contracts written before the persistent runtime implementation."""
import asyncio
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))

from spark_intelligence.runtime import Runtime, PolicyError


class RuntimeAcceptance(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.now=1000.
        self.calls=[]
        async def execute(action,args,project):
            self.calls.append((action,args,project))
            return {'ok':True,'value':args.get('value',1)}
        self.execute=execute
        self.runtime=Runtime(self.directory.name,executor=execute,clock=lambda:self.now)

    async def asyncTearDown(self):
        await self.runtime.close()
        self.directory.cleanup()

    def plan(self):
        return [{'action':'get_system_status','args':{},'depends':[]},
                {'action':'run_skill','args':{'name':'area','params':{'a':3,'b':4}},'depends':[0]}]

    async def test_checkpoint_persists_and_resume_does_not_repeat_completed_step(self):
        task=self.runtime.create('general','Status then area',self.plan())
        with self.assertRaises(PolicyError):await self.runtime.run('general',task['id'])
        self.runtime.authorize('general',task['id'],task['plan_hash'],approved=True)
        first=await self.runtime.run('general',task['id'],max_steps=1)
        self.assertEqual(first['cursor'],1)
        await self.runtime.close()
        self.runtime=Runtime(self.directory.name,executor=self.execute,clock=lambda:self.now)
        second=await self.runtime.run('general',task['id'])
        self.assertEqual(second['state'],'completed')
        self.assertEqual(len(self.calls),2)

    async def test_stale_scope_unsafe_actions_and_cross_project_requests_are_rejected(self):
        with self.assertRaises(PolicyError):self.runtime.create('general','Unsafe',[{'action':'run_shell','args':{'cmd':'whoami'},'depends':[]}])
        task=self.runtime.create('general','Status',self.plan())
        with self.assertRaises(PolicyError):self.runtime.authorize('general',task['id'],'bad',approved=True)
        with self.assertRaises(PolicyError):self.runtime.get('other',task['id'])
        with self.assertRaises(PolicyError):self.runtime.authorize('general',task['id'],task['plan_hash'],approved=False)

    async def test_scheduled_job_survives_restart_and_once_is_not_duplicated(self):
        task=self.runtime.create('general','Scheduled status',self.plan()[:1])
        self.runtime.authorize('general',task['id'],task['plan_hash'],approved=True)
        schedule=self.runtime.schedule('general',task['id'],{'kind':'once','at':1001},approved=True)
        await self.runtime.close()
        self.runtime=Runtime(self.directory.name,executor=self.execute,clock=lambda:self.now)
        self.now=1002
        self.assertEqual(await self.runtime.tick(),[])
        self.runtime.configure_scheduler(True,approved=True)
        await self.runtime.tick();await self.runtime.tick()
        self.assertEqual(len(self.calls),1)
        self.assertFalse(self.runtime.schedules('general')[0]['enabled'])
        self.assertEqual(schedule['kind'],'once')

    async def test_cancellation_keeps_checkpoint_and_explicit_resume_works(self):
        task=self.runtime.create('general','Cancel and resume',self.plan())
        self.runtime.authorize('general',task['id'],task['plan_hash'],approved=True)
        await self.runtime.run('general',task['id'],max_steps=1)
        self.runtime.cancel('general',task['id'])
        with self.assertRaises(PolicyError):await self.runtime.run('general',task['id'])
        self.runtime.resume('general',task['id'],approved=True)
        self.assertEqual((await self.runtime.run('general',task['id']))['state'],'completed')
        self.assertEqual(len(self.calls),2)

    async def test_unverified_results_never_become_successful_learning_evidence(self):
        async def bad(*args):return {'ok':False,'message':'unverified'}
        self.runtime.executor=bad
        task=self.runtime.create('general','Fail safely',self.plan()[:1])
        self.runtime.authorize('general',task['id'],task['plan_hash'],approved=True)
        result=await self.runtime.run('general',task['id'])
        self.assertEqual(result['state'],'failed')
        self.assertFalse(self.runtime.traces('general')[0]['verified'])

    async def test_dependency_validation_and_timeout_are_bounded(self):
        with self.assertRaises(PolicyError):self.runtime.create('general','Cycle',[{'action':'get_system_status','args':{},'depends':[0]}])
        async def stalled(*args):await asyncio.sleep(1)
        self.runtime.executor=stalled
        task=self.runtime.create('general','Timeout',self.plan()[:1],timeout=.01)
        self.runtime.authorize('general',task['id'],task['plan_hash'],approved=True)
        result=await self.runtime.run('general',task['id'])
        self.assertEqual(result['state'],'failed')
        self.assertEqual(result['failure_class'],'timeout')

    async def test_interval_coalesces_missed_runs_and_requires_scheduler_consent(self):
        task=self.runtime.create('general','Monitor',self.plan()[:1])
        self.runtime.authorize('general',task['id'],task['plan_hash'],approved=True)
        self.runtime.schedule('general',task['id'],{'kind':'interval','seconds':60},approved=True)
        self.runtime.configure_scheduler(True,approved=True)
        self.now+=600
        await self.runtime.tick()
        await self.runtime.tick()
        self.assertEqual(len(self.calls),1)
        self.now+=60
        await self.runtime.tick()
        self.assertEqual(len(self.calls),2)

    async def test_interrupted_effect_requires_explicit_resume_after_restart(self):
        task=self.runtime.create('general','Interrupted',self.plan()[:1])
        self.runtime.authorize('general',task['id'],task['plan_hash'],approved=True)
        task=self.runtime.get('general',task['id']);task['state']='running'
        self.runtime._save('job','general',task['id'],task)
        await self.runtime.close()
        self.runtime=Runtime(self.directory.name,executor=self.execute,clock=lambda:self.now)
        self.assertEqual(self.runtime.get('general',task['id'])['state'],'interrupted')
        with self.assertRaises(PolicyError):await self.runtime.run('general',task['id'])

    async def test_cron_runs_at_next_utc_minute_without_replaying_missed_minutes(self):
        task=self.runtime.create('general','Cron monitor',self.plan()[:1])
        self.runtime.authorize('general',task['id'],task['plan_hash'],approved=True)
        schedule=self.runtime.schedule('general',task['id'],{'kind':'cron','expression':'* * * * *','timezone':'UTC'},approved=True)
        self.runtime.configure_scheduler(True,approved=True)
        self.now=schedule['at']+300
        await self.runtime.tick();await self.runtime.tick()
        self.assertEqual(len(self.calls),1)
        self.assertGreater(self.runtime.schedules('general')[0]['at'],self.now)

    async def test_scheduler_configuration_snapshots_require_approved_restore(self):
        self.runtime.configure_scheduler(False,approved=True)
        old=self.runtime.configurations()[0]
        self.runtime.configure_scheduler(True,approved=True)
        with self.assertRaises(PolicyError):self.runtime.restore_configuration(old['id'],approved=False)
        restored=self.runtime.restore_configuration(old['id'],approved=True)
        self.assertFalse(restored['enabled'])
        self.assertFalse(self.runtime._get('setting','system','scheduler')['enabled'])

    async def test_second_worker_cannot_claim_the_same_store_until_owner_closes(self):
        other=None
        try:
            with self.assertRaises(PolicyError):other=Runtime(self.directory.name,executor=self.execute)
        finally:
            if other is not None:await other.close()

    async def test_terminal_workload_can_be_archived_without_erasing_verified_evidence(self):
        task=self.runtime.create('general','Archive status',self.plan()[:1])
        self.runtime.authorize('general',task['id'],task['plan_hash'],approved=True)
        await self.runtime.run('general',task['id'])
        with self.assertRaises(PolicyError):self.runtime.archive('general',task['id'],approved=False)
        self.assertEqual(self.runtime.archive('general',task['id'],approved=True)['state'],'archived')
        self.assertTrue(self.runtime.traces('general')[0]['verified'])

    async def test_operator_can_raise_bounded_concurrency_to_two_read_only_jobs(self):
        await self.runtime.close()
        running=[0,0]
        async def execute(*args):
            running[0]+=1;running[1]=max(running)
            await asyncio.sleep(.03)
            running[0]-=1
            return {'ok':True}
        self.runtime=Runtime(self.directory.name,executor=execute,concurrency=2)
        tasks=[self.runtime.create('general','Concurrent check',self.plan()[:1]) for _ in range(2)]
        for task in tasks:self.runtime.authorize('general',task['id'],task['plan_hash'],approved=True)
        await asyncio.gather(*(self.runtime.run('general',task['id']) for task in tasks))
        self.assertEqual(running[1],2)

if __name__=='__main__':unittest.main()
