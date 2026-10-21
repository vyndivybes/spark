"""Read-only Google Workspace adapter using the host's encrypted gws login.

The host selects the account and native CLI. No tool can request scopes,
export credentials, change accounts, or execute an arbitrary CLI operation.
"""
import argparse
import asyncio
import json
from pathlib import Path
import re
import subprocess


class GoogleReader:
    def __init__(self, cli, account):
        self.cli = Path(cli)
        if not self.cli.is_absolute() or not self.cli.is_file():
            raise ValueError('Configure the installed native Google Workspace CLI.')
        if not isinstance(account, str) or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', account):
            raise ValueError('Configure the expected Google account on the host.')
        self.account = account.lower()

    def _run(self, command, params):
        result = subprocess.run([str(self.cli), *command, '--params', json.dumps(params)],
                                stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                encoding='utf-8', timeout=30, shell=False)
        if result.returncode or len(result.stdout.encode('utf-8')) > 500_000:
            raise ValueError('Google access unavailable. Complete the local OAuth login and check API permissions.')
        value = json.loads(result.stdout)
        if not isinstance(value, dict) or 'error' in value:
            raise ValueError('Google returned an unsupported response.')
        return value

    def read(self, service, operation):
        commands = {
            ('gmail', 'profile'): (['gmail', 'users', 'getProfile'], {'userId':'me'}),
            ('gmail', 'list'): (['gmail', 'users', 'messages', 'list'], {'userId':'me', 'maxResults':10}),
            ('google-drive', 'profile'): (['drive', 'about', 'get'], {'fields':'user(emailAddress,displayName)'}),
            ('google-drive', 'list'): (['drive', 'files', 'list'],
                                      {'pageSize':10, 'fields':'files(id,name,mimeType,webViewLink)', 'q':'trashed = false'}),
            ('google-calendar', 'profile'): (['calendar', 'calendars', 'get'], {'calendarId':'primary'}),
            ('google-calendar', 'list'): (['calendar', 'calendarList', 'list'], {'maxResults':10}),
        }
        if (service, operation) not in commands:
            raise ValueError('Unsupported Google read operation.')
        try:
            # Gmail profile gives an authoritative account identity, without
            # reading mail content, before any selected service returns data.
            profile = self._run(*commands[('gmail', 'profile')])
            if str(profile.get('emailAddress', '')).lower() != self.account:
                return {'ok':False, 'state':'account_mismatch',
                        'message':'The signed-in Google account differs from the host-selected account.'}
            data = profile if (service, operation) == ('gmail', 'profile') else self._run(*commands[(service, operation)])
            return {'ok':True, 'account':self.account, 'service':service, 'read_only':True, 'data':data}
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return {'ok':False, 'state':'authorization_required',
                    'message':'Complete Google OAuth for this account, enable the selected API, then verify again.'}


def main():
    parser = argparse.ArgumentParser(description='SPARK read-only Google account MCP')
    parser.add_argument('--cli', required=True)
    parser.add_argument('--account', required=True)
    parser.add_argument('--service', choices=['gmail', 'google-drive', 'google-calendar'], required=True)
    options = parser.parse_args()
    reader = GoogleReader(options.cli, options.account)
    from mcp.server.fastmcp import FastMCP
    server = FastMCP('spark-' + options.service)

    @server.tool()
    async def google_account_status() -> dict:
        """Verify the host-selected Google account and selected service access."""
        return await asyncio.to_thread(reader.read, options.service, 'profile')

    @server.tool()
    async def google_list_items() -> dict:
        """List up to ten items in the host-selected service: mail IDs, files or calendars."""
        return await asyncio.to_thread(reader.read, options.service, 'list')

    server.run(transport='stdio')


if __name__ == '__main__':
    main()
