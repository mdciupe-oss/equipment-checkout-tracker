# Equipment Checkout Tracker

A small internal web app a university office could use to keep track of shared equipment.

## Features (planned)

- Add, edit, and retire equipment items (name, category, asset tag, condition)
- Check an item out to a borrower with a due date, and check it back in
- See what's checked out and what's overdue
- Staff log in to manage their own department's equipment; each department sees only its own items

## Tech

Python, Flask, SQLite, pytest

## Run it locally (Windows PowerShell)

One-time setup, from the project folder:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The app needs a secret key (used to sign login sessions). It is never stored in the code.
Create `instance/config.py`, which git ignores, with a random key:

```powershell
New-Item -ItemType Directory -Force instance | Out-Null
.\.venv\Scripts\python.exe -c "import secrets; print('SECRET_KEY = %r' % secrets.token_hex(32))" | Out-File -Encoding utf8 instance\config.py
```

Alternatively, set the `TRACKER_SECRET_KEY` environment variable (it takes precedence over the file).
This is the way to go on a hosting service such as Replit, using its Secrets settings.

Start the app, then open http://127.0.0.1:5000 and register an account:

```powershell
.\.venv\Scripts\python.exe -m flask --app tracker run --debug
```

The database (`instance/tracker.sqlite`) and its tables are created automatically on first start.

## Run the tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Tests use a temporary database and a test-only key; they never touch `instance/`.

## Status

In progress. Acceptance criteria are in [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md).
