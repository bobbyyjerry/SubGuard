"""Security headers for every response, and a limit on failed logins."""
import time
from collections import deque

# Where the browser may load things from. Bootstrap, its icons and Chart.js
# come from jsDelivr; the Inter font comes from Google Fonts. Scripts written
# inside a page are blocked, which stops most injected-script attacks.
CONTENT_SECURITY_POLICY = "; ".join((
    "default-src 'self'",
    "script-src 'self' https://cdn.jsdelivr.net",
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com",
    "font-src 'self' https://cdn.jsdelivr.net https://fonts.gstatic.com",
    "img-src 'self' data:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
))

SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",  # never guess a file's type
    "X-Frame-Options": "DENY",  # the site cannot be shown inside another site
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}

# Tells browsers to use HTTPS only, for a year. Sent in production only,
# because local development runs on plain http://localhost.
HSTS = "max-age=31536000; includeSubDomains"


class LoginThrottle:
    """Block sign-in for a while after repeated wrong passwords.

    Failures are counted per (visitor address, email) and kept in memory, so
    the count is per server process and starts again when the server restarts.
    """

    MAX_FAILURES = 5
    WINDOW_SECONDS = 15 * 60
    MAX_TRACKED = 10_000

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._failures = {}

    def _recent(self, key):
        attempts = self._failures.get(key)
        if attempts is None:
            return ()
        oldest_allowed = self._clock() - self.WINDOW_SECONDS
        while attempts and attempts[0] <= oldest_allowed:
            attempts.popleft()
        if not attempts:
            del self._failures[key]
        return attempts

    def is_blocked(self, key):
        return len(self._recent(key)) >= self.MAX_FAILURES

    def record_failure(self, key):
        if len(self._failures) >= self.MAX_TRACKED:
            # Drop finished entries first; if it is still full, start over rather than grow forever.
            for tracked in list(self._failures):
                self._recent(tracked)
            if len(self._failures) >= self.MAX_TRACKED:
                self._failures.clear()
        self._failures.setdefault(key, deque()).append(self._clock())

    def reset(self, key):
        self._failures.pop(key, None)


def register_security(app):
    app.extensions["login_throttle"] = LoginThrottle()

    @app.after_request
    def add_security_headers(response):
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if app.config.get("SESSION_COOKIE_SECURE"):
            response.headers.setdefault("Strict-Transport-Security", HSTS)
        return response
