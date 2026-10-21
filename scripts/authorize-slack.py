"""Accept a Slack bot token locally, verify its workspace, and register it."""
import asyncio
from getpass import getpass
import importlib.util
import os
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))


async def authorize():
    from dotenv import set_key
    from spark_slack_mcp import SlackReader
    print('Spark Slack setup — vyndi (T0C0T8YQLLT)')
    print('Copy the Spark app Bot User OAuth Token from Slack, then paste below.')
    print('Input is hidden. Do not paste the token into chat.')
    token = getpass('Bot token: ').strip()
    if not token.startswith('xoxb-') or any(c.isspace() for c in token):
        print('A bot token is required. Nothing saved.')
        return
    reader = SlackReader('T0C0T8YQLLT', token=token)
    for operation in ('account', 'channels'):
        result = await reader.read(operation)
        if result.get('ok') is not True:
            print('Verification failed: ' + result['state'] + '. Nothing saved.')
            return
    set_key(str(ROOT / 'backend/.env'), 'SPARK_SLACK_TOKEN', token)
    os.environ['SPARK_SLACK_TOKEN'] = token
    spec = importlib.util.spec_from_file_location('spark_account_setup', ROOT / 'scripts/connect-accounts.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    await module.connect(SimpleNamespace(provider='slack', team='T0C0T8YQLLT', check_only=False))


if __name__ == '__main__':
    try:
        asyncio.run(authorize())
    except (KeyboardInterrupt, EOFError):
        print('Setup canceled.')
    except Exception:
        print('Setup could not finish. Check account access and try again.')
    input('Press Enter to close...')
