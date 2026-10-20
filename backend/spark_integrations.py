"""Host-configured MCP services. Socket clients never supply executables or secrets."""
import json
import os
import re
import time
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit
from spark_intelligence.policy import CircuitBreaker
from spark_rea import ReaClient, ReaError
from spark_productivity import WorkbenchError
from spark_jarvis import JarvisClient, JARVIS_TOOL

ADAPTERS=('vaos','vyndi-os','vedm','vaos-jarvis','gmail','google-drive','google-calendar','github','slack')


class Integrations:
    def __init__(self, config=None, *, audit_dir=None):
        self.clients = {}
        self.config = config
        self.breakers = {}
        self.audit = []
        self.audit_dir=Path(audit_dir) if audit_dir is not None else None
        self.jarvis=JarvisClient(enabled=lambda: True)

    def _audit_db(self):
        self.audit_dir.mkdir(parents=True,exist_ok=True)
        path=self.audit_dir/'mcp-audit.sqlite3'
        if self.audit_dir.is_symlink() or path.is_symlink():raise WorkbenchError('Linked audit storage is prohibited.')
        db=sqlite3.connect(path)
        db.execute('CREATE TABLE IF NOT EXISTS audit(body TEXT)')
        return db

    def _record(self,record):
        safe={key:value for key,value in record.items() if key in ('server','action','tool','ok','elapsed_ms')}
        safe['at']=time.time()
        self.audit=(self.audit+[safe])[-200:]
        if self.audit_dir is not None:
            db=self._audit_db()
            try:
                with db:
                    db.execute('INSERT INTO audit VALUES (?)',(json.dumps(safe),))
                    db.execute('DELETE FROM audit WHERE rowid NOT IN (SELECT rowid FROM audit ORDER BY rowid DESC LIMIT 200)')
            finally:db.close()

    def history(self):
        if self.audit_dir is None:return list(reversed(self.audit))
        db=self._audit_db()
        try:return [json.loads(row[0]) for row in db.execute('SELECT body FROM audit ORDER BY rowid DESC LIMIT 200')]
        finally:db.close()

    def catalog(self):
        try:
            config = self.config if self.config is not None else json.loads(os.environ.get("SPARK_MCP_SERVERS", "{}"))
            if not isinstance(config, dict) or len(config) > 8:
                raise ValueError()
            for name, item in config.items():
                if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{1,31}", name): raise ValueError()
                if not isinstance(item, dict) or set(item)-{"command", "args", "env", "read_tools", "transport", "url", "headers"}: raise ValueError()
                if not isinstance(item.get("read_tools", []), list) or any(not isinstance(tool,str) or not 1<=len(tool)<=200 for tool in item.get("read_tools", [])): raise ValueError()
                transport=item.get('transport','stdio')
                if transport not in ('stdio','streamable-http'):raise ValueError()
                if transport=='stdio' and (not isinstance(item.get("command"), str) or not item["command"].strip()): raise ValueError()
                if transport=='streamable-http':
                    endpoint=urlsplit(item.get('url',''))
                    if endpoint.scheme not in ('https','http') or not endpoint.hostname or endpoint.username or endpoint.password or endpoint.fragment or (endpoint.scheme=='http' and endpoint.hostname not in ('localhost','127.0.0.1','::1')):raise ValueError()
                    if not isinstance(item.get('headers',{}),dict) or any(not isinstance(key,str) or not isinstance(value,str) or '\n' in key+value or '\r' in key+value for key,value in item.get('headers',{}).items()):raise ValueError()
                if not isinstance(item.get("args", []), list) or any(not isinstance(a, str) for a in item.get("args", [])): raise ValueError()
                if not isinstance(item.get("env", {}), dict) or any(not isinstance(k, str) or not isinstance(v, str) for k,v in item.get("env", {}).items()): raise ValueError()
            return config
        except (ValueError, TypeError):
            raise WorkbenchError("Host SPARK_MCP_SERVERS configuration is invalid.") from None

    def list(self):
        config=self.catalog()
        configured=[{"name": name, "transport": item.get('transport','stdio'), "configured": True, "read_tools": item.get("read_tools",[]), "health": self.breakers[name].status() if name in self.breakers else {"state":"unprobed"}} for name,item in config.items()]
        if 'vaos-jarvis' not in config and self.jarvis.configured():
            configured.append({'name':'vaos-jarvis','transport':'electron-session','configured':True,
                'state':'session-managed','read_tools':['ask_vaos_jarvis'],
                'setup':'Sign in from Experience Deck → VAOS Jarvis. Each question verifies the VAOS founder session.'})
        names={item['name'] for item in configured}
        return configured+[{'name':name,'configured':False,'state':'unconnected','read_tools':[],
                           'setup':'Configure a real authorized MCP endpoint or stdio server under this name in SPARK_MCP_SERVERS, with host-scoped credentials and explicit read_tools. SPARK does not create a duplicate business ledger.'}
                          for name in ADAPTERS if name not in names]

    async def execute(self, server, action, args):
        config = self.catalog()
        if server=='vaos-jarvis' and server not in config and self.jarvis.configured():
            if action=='mcp_discover':
                return [{'name':JARVIS_TOOL['name'],'description':JARVIS_TOOL['description'],
                         'inputSchema':JARVIS_TOOL['parameters']}]
            if action!='mcp_call' or args.get('name')!='ask_vaos_jarvis' or not isinstance(args.get('arguments'),dict) or set(args['arguments'])!={'question'}:
                raise WorkbenchError('Select the Jarvis advisory question tool with a question argument.')
            result=await self.jarvis.ask(args['arguments']['question'])
            self._record({'server':server,'action':action,'tool':'ask_vaos_jarvis','ok':result.get('ok') is True})
            return {'content':[{'type':'text','text':json.dumps(result)}],'isError':result.get('ok') is not True}
        if not isinstance(server, str) or server not in config:
            raise WorkbenchError("Select a host-configured MCP service.")
        if action not in ('mcp_discover','mcp_call'):
            raise WorkbenchError('Unsupported MCP operation.')
        if action == 'mcp_call' and args.get('name') not in config[server].get('read_tools',[]):
            self._record({'server':server,'action':'denied_tool','ok':False})
            raise WorkbenchError('Tool is not host-approved for read-only execution. Writes are disabled.')
        breaker = self.breakers.setdefault(server,CircuitBreaker())
        if not breaker.allowed():
            raise WorkbenchError('MCP circuit is open after repeated failures; wait before reconnecting.')
        if server not in self.clients:
            item = config[server]
            self.clients[server] = ReaClient(item.get("command"), item.get("args", []), item.get("env"),url=item.get('url') if item.get('transport')=='streamable-http' else None,headers=item.get('headers'))
        try:
            started=time.monotonic()
            result=await self.clients[server].request("rea_discover" if action == "mcp_discover" else "rea_call", args)
            breaker.success()
            self._record({'server':server,'action':action,'tool':args.get('name'),'ok':not (isinstance(result,dict) and result.get('isError')),'elapsed_ms':round((time.monotonic()-started)*1000)})
            return result
        except ReaError:
            breaker.failure('connection_or_schema')
            self._record({'server':server,'action':action,'ok':False})
            raise WorkbenchError("MCP service unavailable or arguments invalid. Check its host configuration, credentials and tool schema.") from None

    async def close(self):
        for client in self.clients.values():
            await client.close()

    async def restart(self,server,*,approved=False):
        if approved is not True or not isinstance(server,str) or server not in self.catalog():
            raise WorkbenchError('Explicit approval for a host-configured MCP client is required.')
        client=self.clients.pop(server,None)
        if client is not None:
            await client.close()
        self.breakers.pop(server,None)
        tools=await self.execute(server,'mcp_discover',{})
        value={'server':server,'verified':isinstance(tools,list),'scope':'owned MCP client and stdio child only','tools':len(tools)}
        self._record({'server':server,'action':'approved_reconnect','ok':value['verified']})
        return value
