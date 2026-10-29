"""Opt-in local Fireflies MCP connection for SPARK (Windows DPAPI; no repository secrets)."""
import argparse
import getpass
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from spark_credential_store import CredentialStore
from spark_integrations import Integrations

FIREFLIES={
    'transport':'streamable-http',
    'url':'https://api.fireflies.ai/mcp',
    'secret_name':'fireflies_api_key',
    'read_tools':['get_user','get_transcripts','get_summary'],
    'write_tools':[],
}

def registry_with_fireflies(current):
    """Preserve existing MCP servers and permissions; never overwrite a named server."""
    if not isinstance(current,dict):
        raise ValueError('MCP registration must be an object.')
    if 'fireflies' in current:
        if current['fireflies'] != FIREFLIES:
            raise ValueError('An existing Fireflies entry requires manual review; nothing was overwritten.')
        updated=dict(current)
    else:
        if len(current)>=8:
            raise ValueError('MCP registry already has eight servers; review an existing slot first.')
        updated={**current,'fireflies':dict(FIREFLIES)}
    Integrations(config=updated).catalog()
    return updated

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true',help='Store key in Windows DPAPI and register read-only endpoint')
    parser.add_argument('--disconnect',action='store_true',help='Remove local token and Fireflies registry entry')
    options=parser.parse_args()
    if options.apply and options.disconnect:
        parser.error('Choose apply or disconnect, not both.')
    from dotenv import dotenv_values, set_key
    private_path=ROOT/'backend/.env'
    current=json.loads(dotenv_values(private_path).get('SPARK_MCP_SERVERS') or '{}')
    if options.disconnect:
        if 'fireflies' in current:
            remaining=dict(current)
            remaining.pop('fireflies')
            Integrations(config=remaining).catalog()
            set_key(str(private_path),'SPARK_MCP_SERVERS',json.dumps(remaining,separators=(',',':')))
        CredentialStore().delete('fireflies_api_key')
        print('Fireflies disconnected on this Windows user; relaunch SPARK to apply.')
        return
    proposed=registry_with_fireflies(current)
    if not options.apply:
        print(json.dumps({'configured': 'fireflies' in current,'eligible':True,
                          'credential_present':CredentialStore().exists('fireflies_api_key'),
                          'applied':False},indent=2))
        return
    # Secret is never put on the command line, the JSON registry or stdout.
    secret=getpass.getpass('Paste Fireflies API key (input hidden): ').strip()
    if not 8<=len(secret)<=2000 or '\r' in secret or '\n' in secret:
        raise ValueError('Invalid API key length or formatting; nothing changed.')
    CredentialStore().save('fireflies_api_key',secret)
    set_key(str(private_path),'SPARK_MCP_SERVERS',json.dumps(proposed,separators=(',',':')))
    print('Read-only Fireflies MCP registered with an encrypted Windows credential. Relaunch SPARK and probe; not yet verified.')

if __name__=='__main__':
    main()
