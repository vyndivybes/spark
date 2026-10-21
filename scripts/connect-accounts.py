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
        from spark_google_mcp import GoogleReader
        binary = (Path(os.environ['LOCALAPPDATA']) /
                  'SPARK/tools/google-workspace/node_modules/@googleworkspace/cli/bin/gws.exe')
        reader = GoogleReader(binary, options.account)
        for service in ('gmail', 'google-drive', 'google-calendar'):
            result = await asyncio.to_thread(reader.read, service, 'profile')
            if not result['ok']:
                print(f'{service}: {result["state"]}. Complete Google OAuth and enable its API.')
                return 2
            additions[service] = {
                'command':python,
                'args':[str(ROOT / 'backend/spark_google_mcp.py'), '--cli', str(binary),
                        '--account', options.account, '--service', service],
                'read_tools':['google_account_status', 'google_list_items'],
            }
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
    options = parser.parse_args()
    if options.provider == 'google' and not options.account:
        parser.error('--account is required for Google')
    if options.provider == 'slack' and not options.team:
        parser.error('--team is required for Slack')
    sys.exit(asyncio.run(connect(options)))
