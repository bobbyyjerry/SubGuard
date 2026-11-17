# SubGuard security checklist

What SubGuard does to protect accounts and data, where each piece lives, and what it does not do yet.

## In place

| Area | What is done | Where |
| --- | --- | --- |
| Passwords | Stored only as salted hashes (Werkzeug), never as text. At least 12 characters. | `app/models.py`, `app/forms.py` |
| Changing password or email | Both need the current password. A new password signs out every other browser and device. | `app/routes/settings.py`, `app/models.py` |
| Failed logins | After 5 wrong passwords for one email from one address, sign-in is blocked for 15 minutes. Unknown emails get the same message, the same limit, and take the same time to check. | `app/security.py`, `app/routes/auth.py` |
| Sessions | The session is cleared at login. Cookies are `HttpOnly` and `SameSite=Lax`, and HTTPS-only in production. | `app/config.py`, `app/routes/auth.py` |
| Forms | Every form that changes something carries a CSRF token, including log out, pause, cancel and delete. | Flask-WTF, templates |
| Private data | Every page and action looks up records by the signed-in account, so one account cannot read or change another's. Private pages are not cached. | `app/routes/` |
| Input | Forms check types, lengths and allowed choices on the server. Cancellation links must be `http` or `https` with no login details in them. | `app/forms.py` |
| Output | Templates escape everything by default. Pages run no inline scripts. | Jinja2, `app/templates/` |
| Browser protections | Content Security Policy, no framing by other sites, no content-type guessing, limited referrer, HTTPS-only (HSTS) in production. | `app/security.py` |
| Database | Queries go through SQLAlchemy with bound values. Foreign keys are enforced, so deleting a subscription or account removes its related rows. | `app/extensions.py`, `app/models.py` |
| Secrets | Read from environment variables. `.env` is git-ignored. Production refuses to start with the example `SECRET_KEY`. | `app/config.py`, `app/__init__.py` |
| Request size | Requests over 1 MB are refused. | `app/config.py` |
| Scope | No bank connections and no payment processing. SubGuard only stores what you type in. | by design |

## Known limits

- **The failed-login count is kept in memory.** It is per server process and starts again when the server restarts. A shared store would be needed for a site with several server processes.
- **Email changes are not confirmed by email.** The new address is used immediately.
- **There is no "forgot password" reset** and no two-factor sign-in.
- **CDN files are not pinned with integrity hashes** (Bootstrap, Bootstrap Icons, the Inter font). Chart.js is.
- **Inline `style` attributes are allowed** by the Content Security Policy, because a few templates use them.
- **Reminder emails are plain text** and include the cancellation link exactly as you saved it.

## Before going live

1. Set `FLASK_CONFIG=production` and turn `FLASK_DEBUG` off.
2. Generate a new `SECRET_KEY`: `python -c "import secrets; print(secrets.token_hex(32))"`.
3. Serve the site over HTTPS only.
4. Run `flask init-db` once after each update.
5. Keep `.env` and `instance/subguard.db` out of Git and out of any public folder.
