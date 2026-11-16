# SubGuard

A smart subscription and free-trial reminder platform built with Flask.

> 🚧 Work in progress. A full README with screenshots comes on Day 12.

## Run it locally (Windows / PowerShell)

```powershell
cd D:\Robert\SubGuard
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # then set SECRET_KEY inside .env
flask init-db
flask run
```

Open http://127.0.0.1:5000 and select **Get started** to create an account.
If you already have a virtual environment and `.env`, start at `flask init-db` after activating it. Rerun this command when new tables are added to keep your existing data and create the missing tables.
The database defaults to `instance/subguard.db`.

After logging in, use **Subscriptions** to add and manage subscriptions or free trials.
The **Dashboard** shows your saved subscriptions, monthly and annual estimates by currency, upcoming payments, and active free trials.
Open **Analytics** for monthly and annual spending by category. When available, use the currency buttons to switch between estimates.
Open **Calendar** to browse upcoming renewal dates and free-trial endings by month.

## Email reminders

Set `MAIL_SERVER` and `MAIL_DEFAULT_SENDER` in `.env` using your SMTP provider's settings. Set `MAIL_USERNAME` and `MAIL_PASSWORD` if your relay requires authentication. The default is STARTTLS on port 587. Use `MAIL_SECURITY=ssl` for implicit TLS (port 465 by default) or `MAIL_SECURITY=none` for a local test relay without credentials.

Run this in an activated virtual environment. Keep the reminder worker running in its own terminal alongside the web app.

```powershell
flask init-db
flask reminders
```

The worker checks every 15 minutes and sends one reminder per saved subscription date, starting three days before the renewal or trial end. Set `REMINDER_DAYS` to change the lead time for the app. The first check runs at startup and catches upcoming events still inside the window. To check once and exit, use `flask reminders --once`.

The database records each handoff. The worker retries messages that SMTP definitively rejects and logs unconfirmed handoffs for review to avoid duplicate sends.

## Run the tests

```powershell
pytest
```

## Tech stack

Flask · Flask-SQLAlchemy · SQLite · Flask-Login · Flask-WTF · Bootstrap 5 · Chart.js · APScheduler · Pytest
