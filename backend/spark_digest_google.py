"""Read-only scheduled Google snapshots without starting separate MCP servers."""
import asyncio
from pathlib import Path

from spark_google_mcp import GoogleReader
from spark_integrations import Integrations
from spark_productivity import WorkbenchError

SERVICES = ('gmail', 'google-calendar', 'google-drive')
ADAPTER = Path(__file__).with_name('spark_google_mcp.py').resolve()


class ScheduledGoogleReads:
    def __init__(self, **options):
        self.host = Integrations(**options)

    def list(self):
        return [item for item in self.host.list() if item['name'] in SERVICES]

    async def execute(self, service, action, payload):
        tool = payload.get('name')
        if (service not in SERVICES or action != 'mcp_call'
                or payload.get('arguments') != {}
                or tool not in ('google_daily_briefing', 'google_tasks_briefing')
                or tool == 'google_tasks_briefing' and service != 'google-calendar'):
            raise WorkbenchError('Scheduled digest permits only approved Google briefing reads.')
        entry = self.host.catalog().get(service, {})
        args = entry.get('args', [])
        try:
            if tool not in entry.get('read_tools', []) or not args or Path(args[0]).resolve() != ADAPTER:
                raise ValueError()
            if args[args.index('--service') + 1] != service:
                raise ValueError()
            reader = GoogleReader(args[args.index('--cli') + 1], args[args.index('--account') + 1])
        except (ValueError, IndexError):
            raise WorkbenchError('Configure the bundled, account-bound Google briefing adapter.') from None
        value = await asyncio.to_thread(reader.read,
                                       'google-tasks' if tool == 'google_tasks_briefing' else service,
                                       'briefing')
        self.host._record({'server': service, 'action': 'scheduled_digest_read',
                           'tool': tool, 'ok': value.get('ok') is True})
        return {'structuredContent': value, 'isError': value.get('ok') is not True}

    async def close(self):
        await self.host.close()
