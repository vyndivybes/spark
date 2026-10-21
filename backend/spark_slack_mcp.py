"""Fixed read-only Slack methods, authenticated only by host configuration."""
import argparse
import asyncio
import os
from pathlib import Path

import httpx


class SlackReader:
    def __init__(self, team, token=None):
        if not isinstance(team, str) or not team.startswith('T') or not team.isalnum():
            raise ValueError('Configure the expected Slack workspace ID.')
        self.team = team
        self.token = token if token is not None else os.getenv('SPARK_SLACK_TOKEN', '')

    async def read(self, operation):
        if operation not in ('account', 'channels'):
            raise ValueError('Unsupported Slack read operation.')
        if not self.token:
            return {'ok':False, 'state':'authorization_required',
                    'message':'Authorize a Spark Slack app in the selected workspace first.'}
        try:
            async with httpx.AsyncClient(timeout=20, trust_env=False, follow_redirects=False) as client:
                async def request(method, data):
                    response = await client.post('https://slack.com/api/' + method, data=data,
                                                  headers={'Authorization':'Bearer ' + self.token})
                    response.raise_for_status()
                    if len(response.content) > 500_000:
                        raise ValueError('Response limit exceeded')
                    value = response.json()
                    if not isinstance(value, dict) or value.get('ok') is not True:
                        raise ValueError('Slack authorization failed')
                    return value

                identity = await request('auth.test', {})
                if identity.get('team_id') != self.team:
                    return {'ok':False, 'state':'account_mismatch',
                            'message':'The authorized Slack workspace differs from the host-selected workspace.'}
                data = ({key:identity.get(key) for key in ('team', 'team_id', 'user', 'user_id')}
                        if operation == 'account' else
                        await request('conversations.list', {'limit':20, 'exclude_archived':'true', 'types':'public_channel'}))
                return {'ok':True, 'workspace':self.team, 'read_only':True, 'data':data}
        except (httpx.HTTPError, ValueError):
            return {'ok':False, 'state':'authorization_required',
                    'message':'Slack access failed. Check the app installation and read permissions.'}


def main():
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).with_name('.env'))
    parser = argparse.ArgumentParser(description='SPARK read-only Slack account MCP')
    parser.add_argument('--team', required=True)
    reader = SlackReader(parser.parse_args().team)
    from mcp.server.fastmcp import FastMCP
    server = FastMCP('spark-slack')

    @server.tool()
    async def slack_account_status() -> dict:
        """Verify access to the host-selected Slack workspace."""
        return await reader.read('account')

    @server.tool()
    async def slack_list_channels() -> dict:
        """List up to twenty public channels in the host-selected workspace."""
        return await reader.read('channels')

    server.run(transport='stdio')


if __name__ == '__main__':
    main()
