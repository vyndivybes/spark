"""Bounded reference reads through Electron's existing business sessions."""
import json

from spark_jarvis import JarvisClient

BUSINESS_TOOLS = {
    'vyndi-os': {'name':'read_vyndi_engineering_authority',
        'description':'Read the signed-in VYNDI OS seeded engineering-authority reference. Not a live ledger; preserve release holds.'},
    'vedm': {'name':'read_vedm_library',
        'description':'Read published VEDM engineering-library metadata, configurations and gates. Not synchronization or release approval.'},
}


class BusinessClient(JarvisClient):
    async def read(self, portal):
        if portal not in BUSINESS_TOOLS or not self.enabled():
            return {'ok':False,'message':'Select an available host business connection.'}
        import aiohttp
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25),trust_env=False) as session:
                async with session.post(self.endpoint.rstrip('/')+'/business-read',
                        headers={'Authorization':'Bearer '+self.token},json={'portal':portal},
                        allow_redirects=False) as response:
                    if response.status!=200:
                        raise ValueError()
                    raw=await response.content.read(1_000_001)
                    if len(raw)>1_000_000:
                        raise ValueError()
                    result=json.loads(raw)
                    if not isinstance(result,dict) or type(result.get('ok')) is not bool:
                        raise ValueError()
                    expected='seeded-authority-reference' if portal=='vyndi-os' else 'published-engineering-library'
                    if result['ok'] and (result.get('readOnly') is not True or result.get('sourceKind')!=expected
                            or not isinstance(result.get('data'),dict) or not isinstance(result.get('limitation'),str)):
                        raise ValueError()
                    return result
        except (OSError,TimeoutError,ValueError,aiohttp.ClientError):
            return {'ok':False,'message':'Business read unavailable. Reopen Spark and check portal sign-in.'}
