# Deploying SubGuard to PythonAnywhere (free plan)

This puts SubGuard online at `https://YOURNAME.pythonanywhere.com`. Replace `YOURNAME` everywhere below with your PythonAnywhere username.

## What the free plan can and cannot do

| | Free plan |
| --- | --- |
| Website | One web app, served over HTTPS. |
| Staying online | The web app switches off after one month unless you log in and select **Run until 1 month from today** on the Web page. PythonAnywhere emails a warning first. |
| Scheduled tasks | None on accounts created after 15 January 2026. This is why a daily GitHub job triggers the reminders (step 7). |
| Email | Only Gmail's SMTP server can be reached. |
| Database | The SQLite file works as it is. Disk space is 512 MB. |

## 1. Create the account

Sign up for a free "Beginner" account at https://www.pythonanywhere.com and confirm your email address.

## 2. Copy the project from GitHub

On the **Consoles** page, start a **Bash** console and run:

```bash
git clone https://github.com/bobbyyjerry/SubGuard.git
```

```bash
cd SubGuard && mkvirtualenv --python=/usr/bin/python3.13 subguard
```

```bash
pip install -r requirements.txt
```

## 3. Create the settings file

Still in the Bash console, inside the `SubGuard` folder:

```bash
cp .env.example .env && chmod 600 .env
```

Print two fresh secrets. The first is for `SECRET_KEY`, the second for `REMINDER_TRIGGER_TOKEN`:

```bash
python -c "import secrets; print(secrets.token_hex(32)); print(secrets.token_urlsafe(48))"
```

Open `.env` in PythonAnywhere's editor (**Files** page → `SubGuard` → `.env`) and set these lines. Remove the `#` in front of any you use.

```
FLASK_DEBUG=0
FLASK_CONFIG=production
SECRET_KEY=the first value printed above
REMINDER_TRIGGER_TOKEN=the second value printed above

MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_SECURITY=starttls
MAIL_USERNAME=your Gmail address
MAIL_PASSWORD=a Gmail app password
MAIL_DEFAULT_SENDER="SubGuard <your Gmail address>"
```

A Gmail **app password** is a 16-letter password made for one app. Create it at https://myaccount.google.com/apppasswords (your Google account needs 2-Step Verification switched on). Never use your normal Gmail password here, and never put any of these values in Git or in a chat.

You can leave the `MAIL_` lines out for now. The site works without them; it just sends no emails.

## 4. Create the database

```bash
flask init-db
```

It should print `Database tables are ready.`

## 5. Create the web app

On the **Web** page:

1. Select **Add a new web app** → **Manual configuration** → **Python 3.13**.
2. Under **Virtualenv**, enter `subguard`.
3. Under **Code**, set **Source code** and **Working directory** to `/home/YOURNAME/SubGuard`.
4. Open the **WSGI configuration file** link, delete everything in it, and paste:

   ```python
   import sys

   path = "/home/YOURNAME/SubGuard"
   if path not in sys.path:
       sys.path.insert(0, path)

   from wsgi import app as application
   ```

5. Under **Static files**, add URL `/static/` with directory `/home/YOURNAME/SubGuard/app/static`.
6. Under **Security**, switch **Force HTTPS** on.
7. Select the green **Reload** button.

## 6. Check the site

Open `https://YOURNAME.pythonanywhere.com`, create an account and add a subscription.

If you see an error page, open the **Error log** link on the Web page. The last lines say what went wrong. The most common causes are a typo in the WSGI file path or a missing `SECRET_KEY`.

## 7. Switch on the daily reminders

The repository already contains the job: `.github/workflows/reminders.yml`. It runs once a day and asks your site to send any reminders that are due. It needs two secrets.

On GitHub, open the repository → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**, and add:

| Name | Value |
| --- | --- |
| `SUBGUARD_URL` | `https://YOURNAME.pythonanywhere.com` |
| `REMINDER_TRIGGER_TOKEN` | exactly the same value as in the server's `.env` |

Then open the **Actions** tab → **Daily reminders** → **Run workflow** to try it straight away. A green tick means the site answered. The log shows how many emails were sent, for example `{"failed":0,"sent":1}`.

Things to know:

- The job runs at about 06:17 UTC. GitHub can start scheduled jobs late when it is busy.
- Reminders go out once a day, not every 15 minutes as with `flask reminders` on your own computer.
- GitHub pauses scheduled jobs in a repository with no activity for 60 days, and emails you first. Selecting **Enable workflow** on the Actions tab turns it back on.
- Running the job twice in a day is safe. Each reminder is recorded and sent only once.

## Updating the site later

In a PythonAnywhere Bash console:

```bash
cd ~/SubGuard && workon subguard && git pull && pip install -r requirements.txt && flask init-db
```

Then select **Reload** on the Web page.

## Backing up your data

Everything is in one file: `/home/YOURNAME/SubGuard/instance/subguard.db`. Download a copy from the **Files** page from time to time.
