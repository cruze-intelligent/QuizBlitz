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

   For production or SocketIO eventlet compatibility, prefer:

   ```bash
   gunicorn --worker-class eventlet -w 1 run:app
   ```

## Default credentials

- Quiz master: `master@quizblitz.com` / `master123`
- Admin: `admin@quizblitz.com` / `admin123`

## Notes

This app uses Flask-SocketIO with the `eventlet` async worker for live sessions. The database is SQLite for local MVP development and is easy to swap to PostgreSQL later.
