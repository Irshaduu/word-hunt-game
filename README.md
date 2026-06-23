# Word Hunt 🎯

A real-time, multiplayer word-finding game built with **Django** and **WebSockets**. Designed for quick, low-friction multiplayer sessions during voice calls and casual gatherings, the project prioritizes a "zero-friction" user experience: offering instant home-screen installation via PWA, utilizing lightweight PIN authentication, and featuring 3-letter room codes for verbal sharing.

> 🌐 **Play now:** [word-hunt-game.onrender.com](https://word-hunt-game.onrender.com) (Free — hosted on Render)

## Features ✨

- **Real-time Multiplayer:** Powered by Django Channels and WebSockets for instant interactions.
- **Dynamic Gameplay:** One player secretly picks a word from a chaotic board of **71 randomized words** (varied fonts, sizes, colors, and rotations), and the others scramble to find it.
- **Time Bank System:** Every player starts with **100 seconds**. Time ticks down while you're hunting. If your timer hits zero, you're eliminated!
- **Modern UI:** A vibrant, glassmorphism design with a deep-space arena, neon floating banners, gradient accents, and smooth micro-animations. Fully optimized for mobile, tablet, and desktop.
- **Reconnection Handling:** Players are soft-disconnected on connection loss, allowing safe browser refreshes without being kicked from the game. Clients reconnect with exponential backoff and receive a full state sync.
- **Authentication:** Username + 4-character PIN registration system with persistent player profiles.
- **Player Profiles & Stats:** Tracks total earned seconds, 1st–5th place finishes, and global rank across all games.
- **Global Leaderboard:** Paginated leaderboard showing top hunters worldwide, accessible from the landing page.
- **Installable PWA:** Service worker + web manifest allows players to install Word Hunt as a native-like app on mobile.
- **Screen Wake Lock:** Prevents mobile devices from sleeping during gameplay (requires HTTPS).
- **Procedural Audio:** All sound effects (game start fanfare, tick countdown, elimination, victory chord) are synthesized in real-time via the Web Audio API — zero audio files needed.
- **Haptic Feedback:** Vibration pattern on "Your Turn!" for mobile devices.
- **Auto-Pick Safety Net:** If the picker doesn't choose a word within 20 seconds, a random word is auto-selected so the game keeps flowing.
- **Stale Room Cleanup:** Rooms in GAME_OVER state are automatically purged after 10 minutes to free memory.

## The $0 System Philosophy 💸

This game is designed to operate at zero recurring infrastructure cost:

| Component | Choice | Cost |
|-----------|--------|------|
| Hosting | Render Free Tier | $0 |
| Database | SQLite (file-based) | $0 |
| Message Broker | InMemoryChannelLayer (no Redis) | $0 |
| Static Files | WhiteNoise (no CDN) | $0 |
| Sound Effects | Web Audio API (no audio files) | $0 |
| SSL/HTTPS | Render provides free TLS | $0 |
| Domain | `*.onrender.com` subdomain | $0 |

The system comfortably supports the intended usage pattern of friends, family, and office gatherings.

## Tech Stack 🛠️

- **Backend:** Python 3.12, Django 5.1, Django Channels 4.1 (WebSockets)
- **ASGI Server:** Daphne (serves both HTTP and WebSocket traffic)
- **State Management:** Pure in-memory — global `ROOMS` dict for game state, `InMemoryChannelLayer` for WebSocket groups. Zero external dependencies.
- **Database:** SQLite — only used for user accounts, profiles, and session storage.
- **Frontend:** HTML5, Vanilla JavaScript (IIFE pattern), CSS3 with custom properties — no frameworks, no build step.
- **Static Files:** WhiteNoise with `CompressedManifestStaticFilesStorage` for compression and cache-busting.
- **Fonts:** Google Fonts (Fredoka, Baloo 2, Bubblegum Sans, Chewy, Boogaloo, Righteous, Nunito)
- **Icons:** Phosphor Icons (duotone set)
- **Dependencies:** Only 4 — `django`, `channels`, `daphne`, `whitenoise`

## How to Play 🎮

1. **Register/Login:** Create an account with a username and a 4-character PIN.
2. **Create or Join:** Create a new room or join a friend's room using a 3-letter code (e.g., `XKQ`).
3. **The Picker:** Each turn, one player gets **20 seconds** to secretly pick a word from the chaotic board of 71 words.
4. **The Reveal:** The chosen word is displayed on everyone's screen for **6 seconds** — memorize it!
5. **The Hunt:** The word display disappears and the hunt begins! Find and tap the word on the board as fast as you can.
6. **Survival:** Every second you spend searching drains your time bank. If it hits zero — you're out!
7. **Victory:** The last player standing with time remaining wins the game! 🏆

## Architecture Overview 🏗️

> **Detailed Design Document:** Please read [ARCHITECTURE.md](ARCHITECTURE.md) for a deep dive into the $0 infrastructure constraints, the single-instance state management strategy, and DevOps workarounds.


```
Client (Browser)                    Server (Render)
┌─────────────┐                     ┌──────────────────────┐
│  landing.html│──── HTTP ──────────▶│  views.py            │
│  lobby.html  │                     │  (Auth, Room CRUD)   │
│  game.html   │                     └──────────┬───────────┘
│              │                                │
│  lobby.js    │──── WebSocket ────▶│  consumers.py         │
│  game.js     │     (wss://)       │  ├─ LobbyConsumer     │
│              │◀─── Broadcasts ────│  └─ GameConsumer      │
└─────────────┘                     └──────────┬───────────┘
                                               │
                                    ┌──────────▼───────────┐
                                    │  game_manager.py      │
                                    │  (GameRoom state      │
                                    │   machine — pure      │
                                    │   Python, no Django)   │
                                    └──────────┬───────────┘
                                               │
                                    ┌──────────▼───────────┐
                                    │  ROOMS = {} (RAM)     │
                                    │  SQLite (users only)  │
                                    └──────────────────────┘
```

## Local Setup 🚀

1. Clone the repository:
   ```bash
   git clone https://github.com/Irshaduu/word-hunt-game.git
   cd word-hunt-game
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run database migrations:
   ```bash
   python manage.py migrate
   ```

5. Start the development server (uses Daphne for WebSockets):
   ```bash
   python manage.py runserver
   ```

6. Open your browser to `http://127.0.0.1:8000`. Open a second incognito window to test multiplayer!

## Deploy to Render 🌐

1. Push your code to a GitHub repository.
2. Create a new **Web Service** on [Render](https://render.com) and connect your repo.
3. Set the following:
   - **Build Command:** `pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate`
   - **Start Command:** `daphne -b 0.0.0.0 -p $PORT wordhunt.asgi:application`
4. Add environment variables:
   - `DJANGO_SECRET_KEY` — a strong random secret key
   - `DJANGO_DEBUG` — `False`
5. Deploy! Render provides free HTTPS which enables WebSocket (`wss://`), Screen Wake Lock, and PWA installation.
