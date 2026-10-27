# Word Hunt Roadmap

Where Word Hunt goes next: from a game you play with friends on a call, to one where you can find friends, invite them, and talk while you play. It still costs $0 a month.

Written October 2026. Each phase ships on its own, so the game is finished at the end of every phase, not only the last one.

| Phase | What players get | Status |
|---|---|---|
| 0. Steadier today | The current game holds up on real phones and networks | In progress |
| 1. Foundation | Nothing visible: the base the social features stand on | Next |
| 2. Google sign-in | Sign in with Google, real profiles, match history | |
| 3. Friends | Friend requests, friends list, who's online | |
| 4. Play together | Invite a friend; random matches, with Robo as the fallback | |
| 5. Voice in games | Talk to up to 3 others during a game | |
| 6. Voice rooms | Rooms where up to 8 people talk | |

## The $0 budget

Every phase has to fit these free tiers (checked October 2026):

| Service | Free allowance | What uses it up |
|---|---|---|
| Render web service | 512 MB RAM, 0.1 CPU, 750 hours/month (enough for one always-on service), **5 GB outbound/month** | Every page, static file and WebSocket message sent |
| Neon Postgres | **100 CU-hours/month** (about 400 hours awake at 0.25 CU), 1 GB storage, 5 GB egress | Any query wakes it; it sleeps 5 minutes after the last one |
| Cloudflare Realtime (TURN + SFU) | 1,000 GB egress/month, shared by both | Relayed and forwarded audio |
| Google sign-in | Free | — |

At a limit, Render (with no card on file) switches the app off until the 1st, and Neon suspends the database until the next month. So the four rules below are about keeping the game online, not only about saving money:

1. **Audio never passes through Render.** Voice goes browser to browser, or through Cloudflare. Render only takes HTTP and WebSocket traffic anyway.
2. **Nothing queries Postgres on a timer.** The uptime pinger keeps Render awake around the clock, so a timed query would keep Neon awake too: 0.25 CU × 730 hours ≈ 182 CU-hours, and Neon would stop about 17 days into the month. Online status, queues, invites and live rooms stay in memory. Only what a person owns (accounts, friendships, results) goes to Postgres.
3. **Every byte Render sends counts.** Keep messages small and images at the size they're shown. Keep static files cached for good, which WhiteNoise's hashed names already do. Load avatars straight from Google's CDN.
4. **One server, state in memory.** No Redis while there is one instance. A restart loses live rooms, so anything that must survive a restart goes to Postgres.

Once a month, check the Bandwidth graph in Render and the Usage page in Neon.

## Phase 0 — Steadier today

Make what exists hold up on real phones and real networks before adding anything new.

- [x] `/healthz` for the uptime pinger, and a 23 KB icon in the install prompt instead of a 254 KB one (`87621a7`).
- [x] **A lobby seat survives a trip to another app.** If a lobby socket drops (sharing the code on WhatsApp, a locked phone), the player keeps their seat, and host if they were host, for two minutes, shown as "Away". Leave gives the seat up at once. A game starts with whoever is there.
- [x] **Pages stop knocking on closed doors.** A socket that can't join (room gone after a restart, room full, game already playing, signed out) is closed with code 4004. The page then opens `/join/<code>/`, which says why, instead of retrying into a frozen screen.
- [x] **Coming back from another app reconnects at once**, instead of waiting out the back-off.
- [x] **Request errors reach Render's logs.** With DEBUG off, Django emailed them to ADMINS, and there are none.
- [x] **Game timers and Robo's moves run as tracked tasks.** One that crashes is logged instead of vanishing.
- [x] **Results are added inside the database**, one `UPDATE … SET x = x + n` per player, so two saves can't overwrite each other. A failed save is logged instead of silently dropped.
- [x] **Wrong PINs (10 per 15 minutes) and new accounts (10 per hour) are limited per address**, so nobody can guess a 4-character PIN or flood a 0.1-CPU server with password hashing.
- [x] **Icons load two pinned stylesheets** (bold and duotone, v2.1.2) instead of an unpinned script that pulled in all six.
- [ ] **Tests run on GitHub Actions** on every push. The workflow is in `.github/workflows/tests.yml`; it first runs on the next push.

## Phase 1 — Foundation

The changes the social features stand on. Players should notice nothing.

1. **Players are keyed by user id, not username.** Rooms (`GameRoom.players`), turn order, saved results and the client all identify players by name today. With Google sign-in, names stop being unique and people can change them. Messages carry `{id, name}`, and the client compares ids.
2. **A room is one page.** Lobby and game merge into `/room/<code>/` with two views and one socket. This way a voice call (Phase 5) survives the game starting and ending.
3. **A room runs its own clock.** The turn loop (`_auto_pick_timer`, `_wait_and_start_hunt`, `monitor_timers`, `finish_round`) moves out of `GameConsumer` into a runner task owned by the room. Invited and matchmade rooms need this, because no player's socket "owns" them.

   The runner also settles what happens when a player drops mid-game. Today the round waits until that player's time bank drains, which can take up to 100 seconds. Simply not waiting for them is wrong: rounds where they're the only hunter would end instantly, they'd stop losing time, and an absent player could outlast the ones still playing. One candidate rule: a player gone for more than 30 seconds is out.
4. **One app-wide socket.** `/ws/me/`, opened from `base.html` on every page, carries online status, friend requests and invites.
5. **The `game` app splits** into `accounts` (sign-in, profile), `social` (friends), `play` (rooms, engine, matchmaking) and `voice` (signalling, TURN credentials). Keep Django's `User` + `PlayerProfile`: switching to a custom user model isn't worth the migration.
6. **Hardening:** `ALLOWED_HOSTS` from Render's `RENDER_EXTERNAL_HOSTNAME`, DEBUG off unless switched on, HSTS, and pinned versions for every CDN file.

Done when: all tests pass, with new ones for the runner, and two phones play a full game with no visible change.

## Phase 2 — Google sign-in and profiles

- `django-allauth` with Google only, using the `openid`, `email` and `profile` scopes.
- Existing PIN players link Google once from their profile. PIN sign-in then closes to new accounts, and later closes entirely.
- Each profile has:
  - a display name (not unique)
  - a friend code (unique, short, easy to share)
  - an avatar URL straight from Google's CDN, never re-hosted on Render
  - stats and the last 20 games
- New tables: `Match` (room code, start and end time, practice or not) and `MatchPlayer` (match, user, place, words found, seconds left). Both are written once per game, in one transaction.
- A privacy-policy page, which Google's consent screen needs.

Done when: a new person signs in with Google in two taps, and an existing PIN player keeps their stats after linking.

## Phase 3 — Friends

- `FriendRequest(from_user, to_user, created, status)`, unique per pair. Two requests that cross become a friendship. `Friendship` is one row per pair, lower id first. `Block` hides two people from each other everywhere.
- Find people by friend code, since names aren't unique.
- **Online status** is an in-memory count of each user's open `/ws/me/` sockets, with about 10 seconds of grace so a page load doesn't flicker you offline. Friends get "online", "in a game" or "offline" pushed over their own socket. None of it is written to Postgres (rule 2).
- Friend requests are limited per user per day.

Done when: two accounts friend each other and see each other come online without refreshing.

## Phase 4 — Play together

- **Invites.** Tap "Play" on a friend. They get a toast on any page they have open. Accept, and both of you land in a new room. Invites live in memory, expire after 60 seconds, and are limited per user.
- **Random matches.** An in-memory queue that makes groups of 2–4. With few people online the queue is often empty, so after about 20 seconds it offers Robo.
- Later: credit far-away players with half their measured round trip when they find a word, since one Render region serves everyone.

Done when: a friend is in your room two taps after you open the friends list, and a random match (or a Robo game) starts within 30 seconds.

## Phase 5 — Voice in games

- WebRTC, peer to peer, in rooms of up to 4. More than that would mean each phone uploads its voice once for every other player. Signalling (offer, answer, ICE candidates) goes over the room socket.
- STUN from Google's public servers. TURN from Cloudflare, with short-lived credentials that Django creates per user, so the Cloudflare key never reaches a browser. Some players on mobile data can't connect directly, and TURN relays them.
- The microphone is off by default and only asked for when the player taps it. Mute, push-to-talk, and a ring on the avatar of whoever is speaking.
- Voice is friends-only by default. Random matches stay text-only.
- Budget: a relayed one-to-one call uses about 45 MB an hour of Cloudflare's 1,000 GB. Render carries only a few KB of signalling.

Done when: two phones on different mobile networks talk through a whole game.

## Phase 6 — Voice rooms (up to 8)

- Cloudflare Realtime SFU: each person sends one audio stream and receives the others'. Django creates the sessions and hands out the tracks.
- Moderation tools come first: the owner can mute, kick and lock, and everyone can report and block. Rooms are listed publicly only once these exist.
- Room text chat is either not stored, or kept for 7 days at most (Postgres has 1 GB).
- Budget: a full 8-person room uses roughly 1–1.3 GB an hour, so about 800 room-hours a month fit in the free allowance. For comparison, LiveKit Cloud's free plan covers about 10 hours of full rooms.

Done when: 8 people talk in a room for an hour, and the owner can mute and kick.

## How each phase is built

- `main` always deploys. A phase lands as small commits, and each one passes CI.
- Game rules, limits and permissions get tests before the code that uses them.
- Each phase adds a section to [ARCHITECTURE.md](ARCHITECTURE.md): what was decided and why, with the numbers.
- Before a phase is merged, its author can explain it without help. For example: what happens when two friend requests cross? When a socket drops in the middle of an invite? Why does voice need TURN?
