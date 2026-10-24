"""Verify a selected provider account, then register its read-only Spark tools.

This script never obtains credentials from Codex or prints provider responses.
Google authentication belongs to gws; Slack tokens belong in backend/.env.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))


async def connect(options):
    from dotenv import dotenv_values, load_dotenv, set_key
    load_dotenv(ROOT / 'backend/.env')
    private = dotenv_values(ROOT / 'backend/.env')
    configuration = json.loads(private.get('SPARK_MCP_SERVERS') or '{}')
    additions = {}
    python = str(ROOT / '.venv/Scripts/python.exe')
    if options.provider == 'google':
        from spark_google_mcp import GoogleReader, GOOGLE_WRITE_TOOLS
        binary = (Path(os.environ['LOCALAPPDATA']) /
                  'SPARK/tools/google-workspace/node_modules/@googleworkspace/cli/bin/gws.exe')
        reader = GoogleReader(binary, options.account)
        if getattr(options, 'enable_writes', False):
            import subprocess
            status = subprocess.run([str(binary), 'auth', 'status'], capture_output=True,
                text=True, encoding='utf-8', timeout=15, check=True)
            scopes = set(json.loads(status.stdout).get('scopes', []))
            needed = {'https://www.googleapis.com/auth/gmail.compose',
                      'https://www.googleapis.com/auth/drive',
                      'https://www.googleapis.com/auth/calendar.events'}
            if not needed <= scopes:
                print('Google write OAuth scopes are missing. Complete consent before enabling writes.')
                return 2
        for service in ('gmail', 'google-drive', 'google-calendar'):
            result = await asyncio.to_thread(reader.read, service, 'profile')
            if not result['ok']:
                print(f'{service}: {result["state"]}. Complete Google OAuth and enable its API.')
                return 2
            additions[service] = {
                'command':python,
                'args':[str(ROOT / 'backend/spark_google_mcp.py'), '--cli', str(binary),
                        '--account', options.account, '--service', service],
                'read_tools':['google_account_status', 'google_list_items', 'google_daily_briefing'],
            }
            if service == 'gmail':
                additions[service]['read_tools'].append('google_pending_email')
                additions[service]['read_tools'].append('google_search_email')
                previous = configuration.get(service, {}).get('args', [])
                for flag in ('--official-account', '--official-config-dir'):
                    if flag in previous:
                        index = previous.index(flag)
                        additions[service]['args'] += [flag, previous[index + 1]]
            if service == 'google-drive':
                additions[service]['read_tools'].append('google_search_drive')
            if service == 'google-calendar':
                additions[service]['read_tools'].append('google_tasks_briefing')
            if getattr(options, 'enable_writes', False):
                additions[service]['args'].append('--allow-writes')
                additions[service]['write_tools'] = GOOGLE_WRITE_TOOLS[service]
            elif configuration.get(service, {}).get('write_tools'):
                # Re-verifying a connection does not revoke an earlier host grant.
                additions[service]['args'].append('--allow-writes')
                additions[service]['write_tools'] = configuration[service]['write_tools']
    else:
        from spark_slack_mcp import SlackReader
        result = await SlackReader(options.team).read('account')
        if not result['ok']:
            print(f'Slack: {result["state"]}. Authorize the Spark app in the selected workspace.')
            return 2
        additions['slack'] = {
            'command':python,
            'args':[str(ROOT / 'backend/spark_slack_mcp.py'), '--team', options.team],
            'read_tools':['slack_account_status', 'slack_list_channels'],
        }
    configuration.update(additions)
    if len(configuration) > 8:
        raise ValueError('The host MCP registry is full; no registrations were changed.')
    if not options.check_only:
        set_key(str(ROOT / 'backend/.env'), 'SPARK_MCP_SERVERS', json.dumps(configuration))
    print(('Verified: ' if options.check_only else 'Verified and registered: ') + ', '.join(additions))
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('provider', choices=['google', 'slack'])
    parser.add_argument('--account')
    parser.add_argument('--team')
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--enable-writes', action='store_true', help='Enable pre-authorized drafts, text files and calendar events; never email sending.')
    options = parser.parse_args()
    if options.provider == 'google' and not options.account:
        parser.error('--account is required for Google')
    if options.provider == 'slack' and not options.team:
        parser.error('--team is required for Slack')
    sys.exit(asyncio.run(connect(options)))
