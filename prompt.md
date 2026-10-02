You are building "QuizBlitz Live" — a real-time, hosted quiz game
for groups. A quiz master controls the session from a dashboard;
teams join via QR code on their phones and answer together.
Think Kahoot, but self-hosted with Flask.

────────────────────────────────────────
TECH STACK
────────────────────────────────────────
Backend:    Python / Flask 3.x
WebSocket:  Flask-SocketIO (eventlet or gevent worker)
DB:         SQLite via Flask-SQLAlchemy (Postgres-ready)
Auth:       Flask-Login + Flask-WTF
QR codes:   qrcode[pil] library
Templates:  Jinja2 + vanilla JS (no frontend framework)
Hosting:    Runs on a single machine / local network for MVP

────────────────────────────────────────
PROJECT STRUCTURE
────────────────────────────────────────
quizblitz/
├── app/
│   ├── __init__.py          # App factory, init SocketIO
│   ├── models.py            # DB models
│   ├── auth/
│   │   └── routes.py        # Login / logout (quiz masters only)
│   ├── master/
│   │   └── routes.py        # Quiz master HTTP routes
│   ├── play/
│   │   └── routes.py        # Team join + play HTTP routes
│   ├── sockets/
│   │   └── events.py        # ALL SocketIO event handlers
│   ├── templates/
│   │   ├── base.html
│   │   ├── auth/login.html
│   │   ├── master/
│   │   │   ├── dashboard.html   # List quizzes, create session
│   │   │   ├── lobby.html       # Waiting room + QR display
│   │   │   ├── question.html    # Show Q + live answer count
│   │   │   ├── reveal.html      # Show correct answer + stats
│   │   │   └── leaderboard.html # Live rankings between rounds
│   │   └── play/
│   │       ├── join.html        # Enter team name after QR scan
│   │       ├── waiting.html     # Waiting for quiz to start
│   │       ├── question.html    # Team answer screen
│   │       └── result.html      # After reveal: correct / wrong
│   └── static/
│       ├── css/style.css
│       └── js/
│           ├── master.js        # Quiz master socket logic
│           └── play.js          # Team socket logic
├── config.py
├── run.py
└── requirements.txt

────────────────────────────────────────
DATABASE MODELS
────────────────────────────────────────

QuizMaster:
  id, username, email, password_hash, created_at

Quiz:
  id, title, category, created_by (FK→QuizMaster)

Question:
  id, quiz_id (FK→Quiz), text, round_number,
  order_in_round, time_limit_seconds (default 30),
  points (default 10)

Option:
  id, question_id (FK→Question), text, is_correct,
  order_index

GameSession:
  id, session_code (6-char unique, e.g. "XK92PL"),
  quiz_id (FK→Quiz), state (ENUM: lobby/question/
  reveal/leaderboard/finished), current_question_index,
  started_at, ended_at

Team:
  id, session_id (FK→GameSession), team_name,
  score (default 0), joined_at

TeamAnswer:
  id, team_id (FK→Team), question_id (FK→Question),
  option_id (FK→Option, nullable), is_correct,
  answered_at

────────────────────────────────────────
GAME SESSION — STATE MACHINE
────────────────────────────────────────
States (stored on GameSession.state):
  LOBBY       → teams scan QR and register team name
  QUESTION    → question is pushed to all screens; timer runs
  REVEAL      → correct answer shown, pass/fail counts shown
  LEADERBOARD → scores updated, rankings shown
  FINISHED    → final leaderboard, session over

Transitions (quiz master triggers all of these):
  LOBBY       → QUESTION    (master clicks "Start quiz")
  QUESTION    → REVEAL      (master clicks "Reveal answer"
                              OR timer expires)
  REVEAL      → LEADERBOARD (master clicks "Show scores")
  LEADERBOARD → QUESTION    (master clicks "Next question")
  LEADERBOARD → FINISHED    (after last question)

────────────────────────────────────────
SOCKETIO EVENTS
────────────────────────────────────────
All events use a room named after session_code so each
game session is isolated.

CLIENT → SERVER:
  join_room         {session_code, team_name}
                    → registers team, joins socket room
  submit_answer     {session_code, team_id, option_id}
                    → saves TeamAnswer, server-side scoring only

SERVER → CLIENT (emit to session room):
  team_joined       {team_name, team_count}
                    → master lobby shows new team in list
  session_started   {}
                    → moves all team screens from waiting→question
  question_pushed   {question_text, options[{id, text}],
                     round, question_num, total_questions,
                     time_limit_seconds}
                    → all screens show the question simultaneously
  answer_received   {answers_in, total_teams}
                    → master sees live "X of Y answered" count
  answer_revealed   {correct_option_id, correct_option_text,
                     passed_count, failed_count,
                     team_results[{team_name, is_correct}]}
                    → all screens show correct answer + result
  leaderboard_updated {rankings[{rank, team_name, score,
                        score_delta}]}
                    → all screens show updated leaderboard
  session_finished  {final_rankings}

────────────────────────────────────────
HTTP ROUTES
────────────────────────────────────────

AUTH (/auth)
  POST /auth/login   → login for quiz masters only
  GET  /auth/logout

MASTER (/master)  — @login_required
  GET  /master/                      → dashboard: list quizzes
  GET/POST /master/quiz/new          → create quiz + questions
  GET/POST /master/quiz/<id>/edit    → edit quiz
  POST /master/session/create        → create GameSession,
                                       generate session_code,
                                       generate QR code image,
                                       redirect to lobby
  GET  /master/session/<code>/lobby  → show QR, team list,
                                       "Start Quiz" button
  POST /master/session/<code>/start  → emit session_started,
                                       push first question
  POST /master/session/<code>/reveal → score submitted answers,
                                       emit answer_revealed
  POST /master/session/<code>/next   → advance question index,
                                       emit question_pushed OR
                                       emit leaderboard_updated
                                       (if round boundary) OR
                                       emit session_finished

PLAY (/play)  — no login required
  GET  /play/<session_code>          → show join form (team name)
  POST /play/<session_code>/join     → create Team record,
                                       return team_id in session,
                                       render waiting.html
  GET  /play/<session_code>/game     → main game page for team
                                       (JS handles all state via
                                       socket events from here)

────────────────────────────────────────
QR CODE GENERATION
────────────────────────────────────────
On session creation:
  import qrcode, io, base64
  join_url = f"{BASE_URL}/play/{session_code}"
  img = qrcode.make(join_url)
  buffer = io.BytesIO()
  img.save(buffer, format="PNG")
  qr_b64 = base64.b64encode(buffer.getvalue()).decode()

Embed in lobby template as:
  <img src="data:image/png;base64,{{ qr_b64 }}">

Store qr_b64 on the GameSession model or regenerate on page load.

────────────────────────────────────────
SCREEN BEHAVIOUR (JavaScript)
────────────────────────────────────────

master.js  (quiz master dashboard socket logic)
  - Connect to socket in session room on page load
  - On team_joined → append team name to lobby list, update count
  - On answer_received → update "X / Y answered" counter live
  - "Reveal Answer" button → POST to /master/session/<code>/reveal
  - "Next Question" button → POST to /master/session/<code>/next
  - On leaderboard_updated → animate rank changes

play.js  (team phone socket logic)
  - Connect to socket in session room on /play/<code>/game load
  - On question_pushed → display question + option buttons,
    start countdown timer matching time_limit_seconds
  - On option button click → emit submit_answer,
    disable all buttons (one answer per question per team),
    show "Answer submitted!" message
  - On timer expiry → disable buttons, show "Time's up!"
  - On answer_revealed → highlight correct option green,
    show team's own answer as correct (green) or wrong (red),
    display pass/fail count
  - On leaderboard_updated → show leaderboard screen
  - On session_finished → show final results

Both screens receive question_pushed → question renders on
BOTH the master's screen and all team phones simultaneously.

────────────────────────────────────────
SCORING LOGIC — SERVER SIDE ONLY
────────────────────────────────────────
On reveal (POST /master/session/<code>/reveal):
  1. Load current question and its correct Option
  2. For each TeamAnswer for this question:
       if option_id == correct_option_id:
         team.score += question.points
         answer.is_correct = True
       else:
         answer.is_correct = False
  3. Count passed = answers where is_correct=True
  4. Count failed = teams that answered incorrectly or didn't answer
  5. Emit answer_revealed with all data
  6. Save to DB

Never send correct_option_id to team clients before reveal.
Team clients only receive it inside answer_revealed.

────────────────────────────────────────
ROUNDS
────────────────────────────────────────
Questions have a round_number field.
After the last question in a round, show full leaderboard.
Master selects which round to play when starting the session.
Leaderboard shows cumulative score across all rounds played.

────────────────────────────────────────
SECURITY
────────────────────────────────────────
- Only quiz masters have accounts; teams are anonymous + ephemeral
- CSRF on all master forms
- Scoring is server-side only; clients never receive the answer key
- Session codes expire when session state = FINISHED
- Rate-limit answer submissions: one per team per question
  (enforce with DB: unique constraint on team_id + question_id
  in TeamAnswer)
- Validate session_code and team_id on every socket event

────────────────────────────────────────
UI / STYLE
────────────────────────────────────────
Primary:    #534AB7  (purple)
Success:    #3B6D11  (green)
Danger:     #A32D2D  (red)
Amber:      #BA7517  (for reveal/leaderboard highlights)
Background: #F8F8F6
Card:       #FFFFFF  with 0.5px border

Master screens are designed for a large display (laptop/projector).
Team screens are optimised for mobile (large touch targets,
min button height 56px, font-size ≥ 16px).

Components needed:
  - QR code display card (large, centred)
  - Team roster list (name pills, live count)
  - Question card (big text, round badge, timer bar)
  - Option buttons (A/B/C/D colour coded, full width on mobile)
  - Answer reveal card (correct option highlighted, pass/fail bar)
  - Leaderboard table (rank, team name, score, delta badge)
  - Live answer progress bar on master screen ("14 / 20 answered")

────────────────────────────────────────
REQUIREMENTS.TXT
────────────────────────────────────────
Flask>=3.0
Flask-SocketIO>=5.3
Flask-SQLAlchemy>=3.1
Flask-Login>=0.6
Flask-WTF>=1.2
Werkzeug>=3.0
qrcode[pil]>=7.4
python-dotenv>=1.0
eventlet>=0.35          # async worker for SocketIO
gunicorn>=21.0          # production server

────────────────────────────────────────
SEED DATA  (flask seed-db)
────────────────────────────────────────
- 1 quiz master: master@quizblitz.com / master123
- 1 quiz: "General Knowledge" with 3 rounds, 5 Qs each
  - Round 1: Science
  - Round 2: History
  - Round 3: Sports
- Each question has 4 options, one correct

────────────────────────────────────────
DELIVERABLE CHECKLIST
────────────────────────────────────────
[ ] App factory with SocketIO initialized
[ ] All models with relationships + unique constraints
[ ] Auth (quiz master login/logout)
[ ] QR code generation on session create
[ ] Master lobby: QR display + live team join list
[ ] State machine transitions via HTTP POST routes
[ ] All 7 SocketIO events implemented
[ ] Team join flow (scan QR → enter name → wait → play)
[ ] Question screen on both master + team simultaneously
[ ] Server-side scoring on reveal
[ ] Answer reveal: pass/fail counts + correct option highlight
[ ] Leaderboard update after every round
[ ] Master and team JS files with full socket event handling
[ ] Mobile-friendly team screens (large tap targets)
[ ] seed-db CLI command
[ ] README with run instructions (including eventlet note)

Start with: models.py → app factory → SocketIO events →
HTTP routes → templates → JS files.