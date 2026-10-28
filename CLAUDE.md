# Word Hunt: notes for Claude

A real-time multiplayer word game: Django 5 and Channels on Daphne, plain JavaScript, hosted for $0 on Render's free plan with Postgres on Neon's. The owner builds it phase by phase.

Read these first:

- [ROADMAP.md](ROADMAP.md): the phases, their status, and "Where it stands": where the last session stopped and what's next.
- [ARCHITECTURE.md](ARCHITECTURE.md): what was decided and why, a section per phase.
- [SETUP.md](SETUP.md): what only the owner can do (keys and settings on Render, Google and Cloudflare).

## The $0 rules decide most designs

From "The $0 budget" in ROADMAP.md:

1. Audio never passes through Render. Voice goes peer to peer, or through Cloudflare.
2. Nothing queries Postgres on a timer, or Neon's free 100 CU-hours run out.
3. Every byte Render sends counts: 5 GB a month.
4. One server with state in memory, no Redis. A restart loses live rooms; what must survive goes to Postgres.

## Where things are

- `game/`: the lobby and game sockets (`consumers.py`), the game's state machine (`game_manager.py`), random matches (`matchmaking.py`), and `tasks.spawn` for timers.
- `accounts/`: PIN and Google sign-in (`google.py`), profiles, the privacy page.
- `social/`: friends and blocks (`rules.py`), who is online (`presence.py`), notices on every page over `/ws/me/` (`me.js`).
- `voice/`: voice in games, peer to peer (`VoiceConsumer`, `ice.py`, `voice.js`), and voice rooms (`rooms.py`, `RoomConsumer`, `sfu.py`, `room.js`), with reports.
- One stylesheet, `game/static/game/css/style.css`. No build step.

## Working here

- This is a Windows machine. Use `venv/Scripts/python.exe`: the `python` on PATH may be the Microsoft Store stub.
- Run `python manage.py collectstatic --noinput` before `python manage.py test`, because static files use the manifest storage. CI (`.github/workflows/tests.yml`) does the same on every push, on Python 3.12.
- Socket tests use `TransactionTestCase` and keep a reference to every `WebsocketCommunicator`: a dropped one gets collected mid-connect.
- With DEBUG on, static URLs aren't hashed, so a browser can keep an old file. Bump the `?v=` on its tag (most have one) when a CSS or JS file changes.
- Each phase gets tests for its rules, small commits, its section in ARCHITECTURE.md, its status in ROADMAP.md, and the owner's steps in SETUP.md.
- No git identity is set on this machine. Commit with the owner's name and email from earlier commits: `git -c user.name=... -c user.email=... commit`.
- `main` deploys to Render on every push. Push, merge or open pull requests only when the owner asks.
