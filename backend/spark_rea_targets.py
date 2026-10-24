"""Fixed read-only REA target routing; no navigation or arbitrary tool plans."""
import ipaddress
import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from spark_rea import ReaError


def public_url(value):
    if not isinstance(value,str) or len(value)>1000:
        raise ReaError('Use a public HTTPS URL without query parameters or fragments.')
    u=urlsplit(value)
    if u.scheme!='https' or not u.hostname or u.username or u.password or u.query or u.fragment or u.port not in (None,443):
        raise ReaError('Use a public HTTPS URL without credentials, query parameters or fragments.')
    host=u.hostname.lower().rstrip('.')
    if host=='localhost' or '.' not in host or host.endswith(('.localhost','.local','.internal')):
        raise ReaError('Private browser targets are outside automatic website analysis.')
    try:address=ipaddress.ip_address(host)
    except ValueError:address=None
    if address is not None and not address.is_global:raise ReaError('Private browser targets are prohibited.')
    return urlunsplit(('https',host,u.path or '/','',''))


def cdp_endpoint(value):
    if not isinstance(value,str):raise ReaError('Configure a host-owned SPARK_REA_CDP_ENDPOINT first.')
    u=urlsplit(value)
    if u.scheme!='http' or u.hostname!='127.0.0.1' or u.username or u.password or not u.port or u.path not in ('','/') or u.query or u.fragment:
        raise ReaError('CDP must use a host-configured literal http://127.0.0.1:PORT endpoint.')
    return value.rstrip('/')


def target_path(value,roots):
    if not isinstance(value,str) or not Path(value).is_absolute():raise ReaError('Choose an absolute local artifact path.')
    original=Path(value)
    if original.is_symlink():raise ReaError('Linked artifacts are prohibited.')
    target=original.resolve(strict=True)
    allowed=[Path(root).resolve(strict=True) for root in roots]
    if not any(target.is_relative_to(root) for root in allowed):raise ReaError('Target is outside host-approved REA roots.')
    if not target.is_file() or target.stat().st_size>200_000_000:raise ReaError('Select a regular artifact no larger than 200 MB.')
    packages={'.zip','.asar','.msix','.appx','.apk','.ipa','.dmg','.pkg'}
    native={'.exe','.dll','.so','.dylib'}
    if target.suffix.lower() not in packages|native:raise ReaError('Automatic analysis supports selected app packages and native binaries only; use repository tools for source.')
    return str(target), 'inspect_artifact' if target.suffix.lower() in packages else 'binary_overview'


def listed_targets(result):
    candidates=[result.get('structuredContent')] if isinstance(result,dict) else []
    for block in result.get('content',[]) if isinstance(result,dict) else []:
        if block.get('type')=='text':
            try:candidates.append(json.loads(block.get('text','')))
            except (ValueError,TypeError):pass
    for candidate in candidates:
        if not isinstance(candidate,dict):continue
        for item in (candidate,candidate.get('result')):
            if isinstance(item,dict):
                targets=(item.get('normalized_result') or {}).get('targets')
                if isinstance(targets,list):return targets
    raise ReaError('REA did not return a typed browser-target listing.')


async def select_analysis(rea,kind,target,*,endpoint=None,roots=()):
    # Only installed advertised tools are used. The MCP worker validates schemas again.
    if kind=='website':
        public_url(target);cdp_endpoint(endpoint)
    elif kind=='artifact':
        target_path(target,roots)
    else:raise ReaError('Choose website or artifact analysis.')
    catalog=await rea.request('rea_discover',{})
    names={t['name'] for t in catalog}
    if kind=='website':
        url=public_url(target);cdp=cdp_endpoint(endpoint)
        if not {'list_browser_targets','inspect_web_page'}<=names:raise ReaError('Installed REA does not advertise passive browser inspection.')
        origin='https://'+urlsplit(url).hostname
        result=await rea.request('rea_call',{'name':'list_browser_targets','arguments':{'cdp_endpoint':cdp,'allowed_origins':[origin]}})
        found=[]
        for item in listed_targets(result):
            try:
                if item.get('type')=='page' and public_url(item.get('url'))==url:found.append(item)
            except (ReaError,ValueError,TypeError):continue
        if len(found)!=1 or not isinstance(found[0].get('target_id'),str):
            raise ReaError('Open the exact public URL in the configured browser. One matching page is required; SPARK will not navigate or change debugging settings.')
        return {'name':'inspect_web_page','arguments':{'cdp_endpoint':cdp,'target_id':found[0]['target_id'],'allowed_origins':[origin],
                'include_accessibility_text':True,'include_script_sources':False,'include_storage_keys':False,'include_storage_fingerprints':False},'title':'Website teardown: '+url}
    if kind=='artifact':
        path,inspection=target_path(target,roots)
        if not {'open_binary',inspection}<=names:raise ReaError('The installed REA catalog lacks the required artifact tools.')
        return {'calls':[{'name':'open_binary','arguments':{'path':path}},{'name':inspection,'arguments':{}}],
                'title':'Local artifact teardown: '+Path(path).name}
    raise ReaError('Choose website or artifact analysis.')
