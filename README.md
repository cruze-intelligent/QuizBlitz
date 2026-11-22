# QuizBlitz

A lightweight, self-hosted quiz game inspired by Kahoot for local network play.

## Features

- Quiz master dashboard for creating and running sessions
- QR code join flow for team phones
- Live question delivery via Flask-SocketIO
- Theme-based scoring and leaderboard updates
- Seed data for a demo quiz mastery flow

## Local setup

1. Create and activate a virtual environment.
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Seed the database:

   ```bash
   flask seed-db
   ```

4. Run the application:

   ```bash
   python run.py
   ```

   This serves on all network interfaces (port 5000) so phones on the same Wi-Fi can
   join, and prints the address to use. **Open the app on the quiz master's computer via
   that network address, not `localhost`**: the lobby QR code points at whatever address
   the browser used. On Windows, allow Python through the firewall when prompted.

   Options (environment variables): `QUIZBLITZ_HOST`, `QUIZBLITZ_PORT`, and
   `QUIZBLITZ_DEBUG=1` for debug mode with auto-reload. Debug mode is forced onto
   `127.0.0.1` because its interactive debugger would let anyone on the network run code.

   For production, prefer:

   ```bash
   gunicorn --worker-class eventlet -w 1 run:app
   ```

## Default credentials

- Quiz master: `master@quizblitz.com` / `master123`
- Admin: `admin@quizblitz.com` / `admin123`
- Dave: `dave@quizblitz.com` / `dave123`

## Operational notes

This app uses Flask-SocketIO with the `eventlet` async worker for live sessions. The database is SQLite for local MVP development and is easy to swap to PostgreSQL later.

Use the health check to verify the app and database are responsive:

```bash
curl http://localhost:5000/health
```

The app also writes operational activity to `logs/quizblitz.log` for session creation, quiz updates, and live gameplay actions.
