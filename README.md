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

## Run the tests

```powershell
pytest
```

## Tech stack

Flask · Flask-SQLAlchemy · SQLite · Flask-Login · Flask-WTF · Bootstrap 5 · Chart.js · APScheduler · Pytest
