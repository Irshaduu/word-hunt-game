# Word Hunt Game - Architecture & Trade-Offs

This document outlines the core architectural decisions made for the Word Hunt Game. Our primary constraint was creating a real-time, low-latency multiplayer experience with a strict operating cost of **$0 per month**.

## 1. Product Context: The "Zero-Friction" Requirement
This project was built to solve a specific UX problem: enabling immediate, frictionless multiplayer engagement during casual group calls with friends and family. 

Standard multiplayer web apps often suffer from high barriers to entry (app store downloads, email verification, complex lobbies). To ensure players could join a game mid-conversation without breaking the flow of a call, the architecture was driven by a strict "zero-friction" requirement:
- **PWA Integration:** Installable directly to the home screen, avoiding mandatory app-store distribution.
- **Frictionless Authentication:** Lightweight identity using a display name and 4-digit PIN, suitable for the intended casual multiplayer use case.
- **3-Letter Room Codes:** Ultra-short room codes (`XKQ`) specifically designed to be easily spoken out loud over a voice call.

The technical trade-offs detailed below (such as in-memory state and SQLite) were chosen explicitly because they perfectly satisfy this small-scale, high-speed UX requirement without introducing unnecessary backend complexity or cost.

## 2. Zero-Cost Infrastructure Constraint ($0 Philosophy)

Most real-time web applications default to using managed services (e.g., managed Redis, hosted PostgreSQL, Vercel/Supabase). While these are excellent for massive scale, they introduce recurring monthly costs. 

To achieve a true $0 operating cost while supporting our target audience, we made the following intentional design trade-offs:

- **Neon PostgreSQL vs. SQLite:** User profiles, leaderboard stats, and sessions are stored in a managed PostgreSQL instance on [Neon](https://neon.tech) (free tier). This provides true persistence that survives Render service restarts and deployments — the root cause of the original ephemeral data loss on free-tier SQLite. Neon's free tier (1 GB of storage, 100 compute-hours a month) is more than sufficient for the intended user base. [ROADMAP.md](ROADMAP.md) lists every free-tier limit the game has to fit, and the rules that keep it inside them.
- **Local Development Fallback:** When the `DB_HOST` environment variable is absent (i.e., on a developer's machine), `settings.py` automatically falls back to SQLite. This means contributors can clone and run the project locally with zero external setup — no Neon account or credentials required.

## 3. In-Memory State Management & YAGNI

The system uses Django Channels with the `InMemoryChannelLayer` and a global Python dictionary (`ROOMS = {}`) to manage the entire game state.

- **Why Not Redis?** Introducing a message broker like Redis is standard practice for horizontal scaling. However, our target scale is **up to 100-200 concurrent users** (friends, family, and extended social circles). Deploying a distributed caching layer for 200 users violates the YAGNI (You Aren't Gonna Need It) principle. 
- **The Trade-Off:** The `InMemoryChannelLayer` locks the application to a **single server instance**. For our specified user base, this single-instance architecture is not a bottleneck; rather, it's a highly efficient design that eliminates network latency between the app server and a cache layer, keeping latency low and avoiding unnecessary infrastructure complexity.
- **Spectators & State Hardening:** Since all room state (including player lists, spectator sets, and active game phases) is tracked purely in memory, we enforce strict state-machine rules (preventing unauthorized re-entry to LOBBY) and utilize dictionary copying during iterations to prevent concurrency issues common in asynchronous WebSocket environments.

## 4. Hybrid Audio System

The game uses two complementary audio strategies:

**Procedural Audio (Web Audio API):** All core game sound effects — the start fanfare, countdown ticks, elimination buzzer, and victory chord — are synthesized mathematically in real-time using the browser's native **Web Audio API**. This requires zero audio files, adds zero latency, and reduces the application's static footprint.

**Soundboard (Static `.mp3` Files):** The post-game soundboard (Airhorn, Clap) uses two small, compressed `.mp3` files served directly from WhiteNoise as static assets. These are pre-loaded by the browser when the game page loads, so playback is instant. This choice was made because these sounds are intended to replicate realistic, recognizable audio effects that are not feasible to synthesize with the Web Audio API's oscillator model.

The two systems co-exist cleanly: the Web Audio API handles all in-game real-time audio, and the static files handle the post-game social soundboard.

## 5. Real-Time Reconnection Strategy

Real-world mobile networks are flaky. To handle this:
- We don't instantly remove players from a game upon WebSocket disconnect.
- Instead, the server marks them as `is_connected = False`.
- When the client reconnects (using exponential backoff), the server automatically resyncs the entire current game state payload, allowing them to resume exactly where they left off without losing their time bank.
- **The lobby keeps seats too.** A dropped lobby socket (sharing the code in another app, a locked phone) keeps the player's seat, and host, for two minutes (`LOBBY_GRACE_SECONDS`), shown as "Away". The Leave button gives the seat up at once. A game starts with whoever is present, so no round waits on an empty seat.
- **Pages know when to stop.** A socket that can't join (the room is gone after a restart, full or already playing, or nobody is signed in) is accepted and then closed with code `4004`. The page stops retrying and opens `/join/<code>/`, which says why.
- **Back from the background.** Returning to a lobby or game page reconnects at once instead of waiting out the backoff.
- **Mid-game, the grace is 30 seconds.** A player whose last socket has been closed for 30 seconds (`GAME_GRACE_SECONDS`) is out of the game and ranked last, so a round never waits for an absent player's time bank to drain. The game page's Leave button does the same at once. Sockets are counted per player, so a second tab, or a socket left over from before Play Again, never marks anyone away. The timer moves the game on through `driver_for(room)`, a `GameConsumer` with no socket: the turn loop only needs the channel layer and the room's group.

## 6. Soundboard Architecture & Spam Prevention

The post-game soundboard allows all players in a room to trigger shared sound effects (Airhorn 📣, Clap 👏) that every connected client hears simultaneously. The design prioritizes fun without compromising server performance:

- **Transport:** Sound trigger events use the existing game WebSocket connection (`game_{room_code}` channel group). No new connections or infrastructure is required.
- **Server-Side Rate Limiting:** Each `GameConsumer` instance tracks `self.last_sound_time`. If a player sends a `play_sound` message within **2 seconds** of their last one, the server silently discards it. This makes spam physically impossible regardless of client-side behavior.
- **Allowlisting:** The server only broadcasts sounds whose names are in the explicit allowlist `['airhorn', 'clap']`, preventing injection of arbitrary sound names.
- **Client-Side UX:** The soundboard buttons are visually disabled for 2 seconds after each press, providing immediate feedback and discouraging repeated tapping.
- **Playback:** The client clones the pre-loaded `Audio` node before playing, which allows overlapping sounds from different users to play simultaneously without conflict.
- **Attribution:** A lightweight toast notification (visible for 1 second) displays the sender's username and the sound emoji, providing social context for who triggered the sound.

---
*By constraining the system to $0 and acknowledging the <200 user limit, these constraints led to custom state machines and a hybrid audio synthesis model, resulting in a lightweight and efficient MVP without introducing unnecessary infrastructure complexity.*
