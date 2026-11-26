# QuizBlitz

A self-hosted live quiz game. A quiz master runs the game from a laptop or projector and
teams join on their phones by scanning a QR code.

## Features

- Quiz master dashboard for creating, editing and running quizzes
- QR code join flow; phones resume where they were after a refresh or lost connection
- Timed questions with live answer counts, reveals and leaderboards
- Optional self-paced quizzes for registered players

## Local setup

Needs Python 3.11 or newer.

```bash
python -m venv .venv          # then activate it
pip install -r requirements.txt
flask init-db
flask seed-db                 # optional demo data; prints one-time passwords
python run.py
```

This serves on all network interfaces (port 5000) so phones on the same Wi-Fi can join,
and prints the address to use. **Open the app on the quiz master's computer via that
network address, not `localhost`**: the lobby QR code points at whatever address the
browser used. On Windows, allow Python through the firewall when prompted.

Options (environment variables): `QUIZBLITZ_HOST`, `QUIZBLITZ_PORT`, and
`QUIZBLITZ_DEBUG=1` for debug mode with auto-reload. Debug mode is forced onto
`127.0.0.1` because its interactive debugger would let anyone on the network run code.

## Accounts

There are no default accounts.

| Command | Purpose |
|---|---|
| `flask create-master` | Quiz master: creates quizzes and hosts games |
| `flask create-admin` | Admin: manages all quizzes |
| `flask set-password EMAIL` | Reset a password |
| `flask add-quizzes --master EMAIL` | Give a quiz master 9 ready-made quizzes as drafts (`--publish` to publish them) |

Public sign-up creates player accounts for self-paced quizzes. Teams in live games need
no account.

A quiz is hidden from players unless it is offered as self-paced, because the self-paced
results page shows every answer.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests
```

## Deployment

See [DEPLOY.md](DEPLOY.md). `run.py` is for trusted local networks only.

## Operational notes

- Health check: `/health` (503 if the database is unavailable).
- Logs: `logs/quizblitz.log` locally, the system journal in production.
- After changing `app/models.py`, create a migration with `flask db migrate -m "..."` and
  review it. `flask init-db` applies it.
