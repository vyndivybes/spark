"""Keep workspace capabilities within the local cockpit trust boundary."""
import hmac


def workspace_client_allowed(environ, provided, expected):
    origin = (environ or {}).get('HTTP_ORIGIN', '')
    if origin in ('http://localhost:5173', 'http://127.0.0.1:5173'):
        return True
    return bool(isinstance(expected, str) and len(expected) == 64
                and isinstance(provided, str) and len(provided) == 64
                and hmac.compare_digest(provided, expected))
