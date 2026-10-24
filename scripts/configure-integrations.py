"""Complete existing host registrations and import explicitly selected messaging accounts.

Run with SPARK's Python runtime. Credentials stay in backend/.env or the local
messaging file, never in command output. No message or provider write is sent.
"""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

MESSAGING_FIELDS = {
    'telegram': ('bot_token', 'allowed_chat_id'),
    'whatsapp': ('access_token', 'phone_number_id', 'allowed_recipient'),
    'whatsapp_bridge': ('bridge_url', 'allowed_recipient'),
    'slack': ('bot_token', 'allowed_channel'),
    'discord': ('webhook_url', 'allowed_channel_id'),
    'teams': ('webhook_url', 'allowed_channel_name'),
    'signal': ('rpc_url', 'account', 'allowed_recipient'),
}


def complete_registry(configuration, root=ROOT):
    """Add read tools only to our bundled adapters; preserve all host grants."""
    configuration = json.loads(json.dumps(configuration))
    adapter = (root / 'backend/spark_google_mcp.py').resolve()
    for name in ('gmail', 'google-drive', 'google-calendar'):
        entry = configuration.get(name, {})
        args = entry.get('args', [])
        if not args or Path(args[0]).resolve() != adapter:
            continue
        tools = entry.setdefault('read_tools', [])
        required = ['google_daily_briefing']
        if name == 'gmail':
            required += ['google_pending_email', 'google_search_email']
        if name == 'google-drive':
            required += ['google_search_drive']
        if name == 'google-calendar':
            required += ['google_tasks_briefing']
        for tool in required:
            if tool not in tools:
                tools.append(tool)
    binary = root / '.venv/Scripts/graphify-mcp.exe'
    graph = root / 'graphify-out/graph.json'
    if 'graphify' not in configuration and len(configuration) < 8 and binary.is_file() and graph.is_file():
        configuration['graphify'] = {'command': str(binary),
            'args': ['--graph', str(graph)], 'read_tools': ['query_graph']}
    return configuration


def messaging_template():
    channels = {name: {'enabled': False, **{key: '' for key in fields}}
                for name, fields in MESSAGING_FIELDS.items()}
    channels['whatsapp']['understood_pricing'] = False
    channels['whatsapp_bridge']['understood_risks'] = False
    return channels


def configure_messaging(hub, channels, slack_token=''):
    """Do not register placeholders as configured or choose recipients for the owner."""
    report = {}
    for name, fields in MESSAGING_FIELDS.items():
        entry = channels.get(name, {})
        if not isinstance(entry, dict):
            raise ValueError('Each messaging entry must be an object.')
        if entry.get('enabled') is not True:
            report[name] = {'state': 'setup_required', 'missing': list(fields)}
            continue
        config = {key: value for key, value in entry.items() if key != 'enabled'}
        if name == 'slack' and not config.get('bot_token'):
            config['bot_token'] = slack_token
        missing = [key for key in fields if not isinstance(config.get(key), str) or not config[key].strip()]
        consent = {'whatsapp': 'understood_pricing', 'whatsapp_bridge': 'understood_risks'}.get(name)
        if consent and config.get(consent) is not True:
            missing.append(consent)
        if missing:
            report[name] = {'state': 'setup_required', 'missing': missing}
            continue
        hub.configure(name, config)
        report[name] = {'state': 'configured_untested'}
    return report


def main():
    from dotenv import dotenv_values, set_key
    from spark_integrations import Integrations
    from spark_messaging_hub import MessagingHub
    from spark_credential_store import CredentialStore
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--messaging-file', type=Path)
    options = parser.parse_args()
    private = dotenv_values(ROOT / 'backend/.env')
    registry = complete_registry(json.loads(private.get('SPARK_MCP_SERVERS') or '{}'))
    Integrations(config=registry).catalog()
    base = Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.spark') / 'SPARK'
    messaging_file = options.messaging_file or base / 'accounts/messaging.json'
    if options.apply:
        set_key(str(ROOT / 'backend/.env'), 'SPARK_MCP_SERVERS', json.dumps(registry))
        if not messaging_file.exists():
            messaging_file.parent.mkdir(parents=True, exist_ok=True)
            messaging_file.write_text(json.dumps(messaging_template(), indent=2) + '\n', encoding='utf-8')
        channels = json.loads(messaging_file.read_text(encoding='utf-8'))
        workspace = Path(os.environ.get('SPARK_WORKSPACE_DATA_ROOT') or base / 'workspace')
        messaging = configure_messaging(
            MessagingHub(workspace, secret_store=CredentialStore()), channels,
            private.get('SPARK_SLACK_TOKEN', ''))
        # Telegram's token now lives only in DPAPI; never leave a copy in the
        # local accounts file after a successful apply.
        telegram = channels.get('telegram')
        if isinstance(telegram, dict) and 'bot_token' in telegram:
            telegram['bot_token'] = ''
            messaging_file.write_text(json.dumps(channels, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'registered': sorted(registry), 'messaging': messaging,
                          'messaging_file': str(messaging_file)}, indent=2))
    else:
        print(json.dumps({'proposed_registrations': sorted(registry), 'applied': False}))


if __name__ == '__main__':
    main()
