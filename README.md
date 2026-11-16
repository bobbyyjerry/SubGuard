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
flask run
```

Open http://127.0.0.1:5000

## Run the tests

```powershell
pytest
```

## Tech stack

Flask · Flask-SQLAlchemy · SQLite · Flask-Login · Flask-WTF · Bootstrap 5 · Chart.js · APScheduler · Pytest
