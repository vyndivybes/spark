"""Fail-closed Windows-friendly SPARK -> VAOS Jarvis pairing preflight.

Default check is strictly offline. Live probe is an explicit opt-in and asks
only a harmless greeting. Never prints device secrets or business records.
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from spark_jarvis_bridge import JarvisBridge, JarvisBridgeError


def check_pairing(env, *, probe=False, bridge_factory=JarvisBridge):
    """Return (exit_code, safe_public_message); never return credential material."""
    try:
        bridge = bridge_factory(env.get('SPARK_JARVIS_URL', ''),
                                env.get('SPARK_JARVIS_TOKEN', ''),
                                env.get('SPARK_JARVIS_DEVICE_ID', ''))
    except Exception:
        return 2, 'HOLD: SPARK Jarvis device configuration is missing or invalid. No network call was made.'
    if not probe:
        return 0, 'PASS: SPARK Jarvis configuration format valid. Remote connection NOT tested; no production readiness claimed.'
    try:
        result = bridge.ask('Hello from SPARK')
    except Exception:
        return 3, 'HOLD: Live Jarvis greeting probe failed. No credentials or enterprise data have been logged.'
    if not isinstance(result, dict) or result.get('status') != 'READY' or result.get('sourceSystem') != 'VAOS_CONVERSATION':
        return 4, 'HOLD: VAOS did not return a verified read-only greeting; pairing is not commissioned.'
    return 0, 'PASS: Live VAOS Jarvis greeting verified. Signed VYNDI source reads, missions and production release are not verified.'


def main():
    parser = argparse.ArgumentParser(description='Safe SPARK VAOS Jarvis pairing check')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='Validate configuration offline (default)')
    mode.add_argument('--probe', action='store_true', help='Send one read-only greeting to the configured HTTPS endpoint')
    args = parser.parse_args()
    # Load only from the ignored Python backend environment file.
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=ROOT / 'backend' / '.env', override=False)
    except ImportError:
        print('HOLD: Python dependency python-dotenv is unavailable. Use the SPARK virtual environment.')
        return 2
    code, safe_message = check_pairing(os.environ, probe=args.probe)
    print(safe_message)
    return code


if __name__ == '__main__':
    sys.exit(main())
