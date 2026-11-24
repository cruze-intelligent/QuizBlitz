# Deploying to quizblitz.cruzegames.store

Target: one small Linux server (Ubuntu 24.04, 1 GB RAM) you control, with Caddy for HTTPS.
The database is a file, so don't use a host that wipes its disk on redeploy.

## 1. DNS

At the DNS provider for cruzegames.store, add:

| Type | Name | Value |
|---|---|---|
| A | `quizblitz` | the server's IPv4 address |

Add an AAAA record only if the server has working IPv6. Wait until
`nslookup quizblitz.cruzegames.store` shows the server before step 5, because Caddy needs
it to get a certificate. On Cloudflare, start with the record set to "DNS only".

## 2. Server packages

```bash
sudo apt update && sudo apt install -y python3-venv sqlite3 git caddy ufw
sudo ufw allow OpenSSH && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw enable
sudo useradd --system --home /opt/quizblitz --shell /usr/sbin/nologin quizblitz
```

Port 8000 must stay closed: the app trusts the proxy's headers.

## 3. Code and settings

```bash
sudo git clone YOUR_REPOSITORY_URL /opt/quizblitz
cd /opt/quizblitz
sudo python3 -m venv .venv
sudo .venv/bin/pip install -r requirements.txt
sudo cp .env.example .env
python3 -c "import secrets; print(secrets.token_hex(32))"   # paste as SECRET_KEY in .env
sudo nano .env
sudo chown root:quizblitz .env && sudo chmod 640 .env
```

The app refuses to start without a private `SECRET_KEY`. Changing it later logs everyone out.

## 4. Start the app

```bash
sudo cp deploy/quizblitz.service deploy/quizblitz-backup.service deploy/quizblitz-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now quizblitz quizblitz-backup.timer
curl http://127.0.0.1:8000/health
```

If it fails: `sudo journalctl -u quizblitz -n 50`.

## 5. HTTPS

This replaces Caddy's configuration. If the server already hosts other sites, add the
block to the existing file instead.

```bash
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

## 6. Accounts

There are no default accounts. Each command asks for a password (10+ characters).

```bash
cd /opt/quizblitz
sudo -u quizblitz .venv/bin/flask --app wsgi create-master
sudo -u quizblitz .venv/bin/flask --app wsgi create-admin
sudo -u quizblitz .venv/bin/flask --app wsgi set-password someone@example.com   # if forgotten
```

## 7. Check before inviting people

- `https://quizblitz.cruzegames.store/health` says `ok`.
- The lobby QR code starts with `https://quizblitz.cruzegames.store/`.
- Play a short game with two real phones on mobile data. Lock one mid-question, unlock it,
  and check the question comes back.

## Updating

Between games, because a restart briefly disconnects phones:

```bash
cd /opt/quizblitz
sudo systemctl start quizblitz-backup
sudo git pull && sudo .venv/bin/pip install -r requirements.txt
sudo systemctl restart quizblitz
```

Database changes are applied automatically on start.

## Backups

Daily at 03:30 into `/var/lib/quizblitz/backups`, kept 14 days. They are on the same
server, so copy them elsewhere regularly. To restore:

```bash
sudo systemctl stop quizblitz
sudo rm -f /var/lib/quizblitz/quizblitz.db-wal /var/lib/quizblitz/quizblitz.db-shm
gunzip -c BACKUP_FILE.db.gz | sudo -u quizblitz tee /var/lib/quizblitz/quizblitz.db > /dev/null
sudo systemctl start quizblitz
```

## Limits

Keep one worker: live rooms are in its memory. Each phone holds one of its 200 threads, so
plan for about 150 connected phones in total across all games.
