"""Measure the local intelligence slice with synthetic data and actual tools.

No provider, camera, microphone, network, model or external device is started.
"""
import argparse
import asyncio
from datetime import datetime,timezone
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))


async def measure():
    tracemalloc.start()
    started=time.perf_counter()
    cpu_started=time.process_time()
    from spark_workspace import SparkWorkspace
    from spark_workbench import Workbench
    latencies=[]
    with tempfile.TemporaryDirectory(prefix='spark-intelligence-benchmark-') as directory:
        workbench=Workbench(SparkWorkspace(directory))
        try:
            for index in range(5):
                before=time.perf_counter()
                job=await workbench.execute('agent_create','benchmark',{'title':'Measured local status '+str(index),'plan':[{'action':'get_system_status','args':{},'depends':[]}]})
                await workbench.execute('agent_authorize','benchmark',{'id':job['id'],'plan_hash':job['plan_hash'],'approved':True})
                result=await workbench.execute('agent_run','benchmark',{'id':job['id']})
                if result['state']!='completed':raise RuntimeError('Real status workload did not verify')
                latencies.append((time.perf_counter()-before)*1000)
            document=workbench.intelligence.workspace.execute('import_document','benchmark',{'name':'synthetic-units.md','data':b'Use metric units for this synthetic benchmark.'})
            retrieval=await workbench.execute('memory_benchmark','benchmark',{'cases':[{'query':'metric','expected_ids':[document['id']]}]})
            health=await workbench.execute('intelligence_health','benchmark',{})
            evidence=await workbench.execute('intelligence_evidence','benchmark',{})
        finally:
            await workbench.intelligence.close()
            await workbench.integrations.close()
        disk=sum(path.stat().st_size for path in Path(directory).rglob('*') if path.is_file())
    _,peak=tracemalloc.get_traced_memory()
    tracemalloc.stop()
    revision=subprocess.run(['git','-C',str(ROOT),'rev-parse','HEAD'],capture_output=True,text=True,timeout=5).stdout.strip()
    return {'generated_utc':datetime.now(timezone.utc).isoformat(),'source_revision':revision,'platform':platform.system(),'python':platform.python_version(),'scope':'isolated intelligence services and five real local system-status jobs; excludes Electron, voice and model inference','samples':len(latencies),'mean_job_ms':statistics.mean(latencies),'max_job_ms':max(latencies),'wall_seconds':time.perf_counter()-started,'process_cpu_seconds':time.process_time()-cpu_started,'peak_traced_python_bytes':peak,'temporary_data_bytes':disk,'host_vitals':health['host_vitals'],'verified_steps':evidence['verified_steps'],'retrieval_fixture':{'queries':retrieval['queries'],'hit_rate':retrieval['hit_rate'],'mean_reciprocal_rank':retrieval['mean_reciprocal_rank'],'scope':'one synthetic labeled query; not a general retrieval quality claim'},'heavy_modules_loaded':{name:name in sys.modules for name in ('torch','dspy','gepa','faiss','sentence_transformers')},'energy_wh':None,'model_cost':None,'model_ttft_seconds':None}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path)
    options=parser.parse_args()
    report=asyncio.run(measure())
    encoded=json.dumps(report,indent=2)
    if options.output:
        options.output.parent.mkdir(parents=True,exist_ok=True)
        options.output.write_text(encoded+'\n',encoding='utf-8')
    print(encoded)
