"""Register a separately authenticated official Gmail account without replacing personal Gmail."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))


def connect(account, config_dir, *, check_only=False, allow_pending=False):
    from dotenv import dotenv_values, set_key
    from spark_google_mcp import GoogleReader
    configuration = json.loads(dotenv_values(ROOT / 'backend/.env').get('SPARK_MCP_SERVERS') or '{}')
    entry = configuration.get('gmail', {})
    arguments = list(entry.get('args', []))
    if '--cli' not in arguments:
        raise ValueError('Connect the primary Google account first.')
    cli = arguments[arguments.index('--cli') + 1]
    reader = GoogleReader(cli, account, config_dir)
    result = reader.read('gmail', 'profile')
    if not result.get('ok'):
        if not allow_pending or result.get('state') != 'permission_denied':
            print('Official email not registered: ' + result.get('state', 'verification_failed'))
            return 2
        import os
        import subprocess
        environment = dict(os.environ)
        for key in ('GOOGLE_WORKSPACE_CLI_TOKEN', 'GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE'):
            environment.pop(key, None)
        environment['GOOGLE_WORKSPACE_CLI_CONFIG_DIR'] = str(reader.config_dir)
        status = subprocess.run([cli, 'auth', 'status'], env=environment, capture_output=True,
                                text=True, encoding='utf-8', timeout=15, check=True)
        identity = json.loads(status.stdout)
        if identity.get('token_valid') is not True or str(identity.get('user', '')).lower() != reader.account:
            print('Official email not registered: signed-in identity is unverified.')
            return 2
    for flag in ('--official-account', '--official-config-dir'):
        if flag in arguments:
            index = arguments.index(flag)
            del arguments[index:index + 2]
    arguments += ['--official-account', reader.account, '--official-config-dir', str(reader.config_dir)]
    entry['args'] = arguments
    entry['read_tools'] = list(dict.fromkeys([*entry.get('read_tools', []), 'google_pending_email']))
    if not check_only:
        set_key(str(ROOT / 'backend/.env'), 'SPARK_MCP_SERVERS', json.dumps(configuration))
    if result.get('ok'):
        print('Official Gmail identity verified' + (' and registered alongside personal Gmail.' if not check_only else '.'))
    else:
        print('Official Google identity verified and saved; Gmail API access remains blocked by permission_denied (403).')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account', required=True)
    parser.add_argument('--config-dir', type=Path, required=True)
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--allow-pending', action='store_true', help='Save a verified Google identity whose Gmail API access is denied; never report mailbox access as verified.')
    options = parser.parse_args()
    raise SystemExit(connect(options.account, options.config_dir, check_only=options.check_only, allow_pending=options.allow_pending))
