"""Pure protocol primitives. No Home Assistant dependency."""
import hashlib
import hmac
import re
import secrets
import time
from collections import deque

TOKEN = re.compile(r"[0-9a-f]{64}\Z")
CODE = re.compile(r"[0-9]{8}\Z")


def digest(token):
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def matches(token, expected):
    return (isinstance(token, str) and TOKEN.fullmatch(token) is not None
            and isinstance(expected, str) and hmac.compare_digest(digest(token), expected))


class PairingPool:
    """Bounded pending requests. A code only identifies a request; an admin approves it."""
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.pending = {}
        self.starts = deque()

    def prune(self):
        now = self.clock()
        self.pending = {c: (h, t) for c, (h, t) in self.pending.items() if t > now}
        while self.starts and self.starts[0] <= now - 60:
            self.starts.popleft()

    def start(self):
        self.prune()
        if len(self.pending) >= 12 or len(self.starts) >= 6:
            return None
        code = f"{secrets.randbelow(100_000_000):08d}"
        while code in self.pending:
            code = f"{secrets.randbelow(100_000_000):08d}"
        token = secrets.token_hex(32)
        self.pending[code] = (digest(token), self.clock() + 600)
        self.starts.append(self.clock())
        return code, token

    def consume(self, code):
        self.prune()
        if not isinstance(code, str) or not CODE.fullmatch(code):
            return None
        item = self.pending.pop(code, None)
        return item[0] if item else None

    def waiting(self, token):
        self.prune()
        return any(matches(token, h) for h, _ in self.pending.values())


def apply_pairing(options, pool, code, revoke):
    """Replace a profile token only after an administrator submits a valid code."""
    if code and revoke:
        return 'revoke_first'
    if code:
        replacement = pool.consume(code)
        if not replacement:
            return 'invalid_code'
        options['token_hash'] = replacement
    elif revoke:
        options.pop('token_hash', None)
    return None


def action_allowed(entity, action, controls):
    return (isinstance(entity, str) and entity in controls
            and entity.partition('.')[0] in ('light', 'switch')
            and action in ('turn_on', 'turn_off'))
