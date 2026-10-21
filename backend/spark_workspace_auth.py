"""Keep workspace capabilities within the local cockpit trust boundary."""
import hmac


def workspace_access_allowed(provided, expected, *, face_required=False, face_authenticated=False):
    """Authorize the desktop workspace independently of microphone/model state.

    Only Electron's trusted root can obtain this per-launch token. Unlike the
    voice-development helper below, a browser Origin alone grants no access.
    """
    token_ok=bool(isinstance(expected,str) and len(expected)==64
                  and isinstance(provided,str) and len(provided)==64
                  and hmac.compare_digest(provided,expected))
    return token_ok and (not face_required or bool(face_authenticated))


def workspace_client_allowed(environ, provided, expected):
    origin = (environ or {}).get('HTTP_ORIGIN', '')
    if origin in ('http://localhost:5173', 'http://127.0.0.1:5173'):
        return True
    return bool(isinstance(expected, str) and len(expected) == 64
                and isinstance(provided, str) and len(provided) == 64
                and hmac.compare_digest(provided, expected))
