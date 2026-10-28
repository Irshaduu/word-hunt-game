# Word Hunt Roadmap

Where Word Hunt goes next: from a game you play with friends on a call, to one where you can find friends, invite them, and talk while you play. It still costs $0 a month.

Written October 2026. Each phase ships on its own, so the game is finished at the end of every phase, not only the last one.

| Phase | What players get | Status |
|---|---|---|
| 0. Steadier today | The current game holds up on real phones and networks | Done |
| 1. Foundation | Nothing visible: the base the social features stand on | Done |
| 2. Google sign-in | Sign in with Google, real profiles, match history | Done; needs a Google client ID |
| 3. Friends | Friend requests, friends list, who's online | Done |
| 4. Play together | Invite a friend; random matches, with Robo as the fallback | Done |
| 5. Voice in games | Talk to up to 3 others during a game | Done; try on two phones |
| 6. Voice rooms | Rooms where up to 8 people talk | Done; needs Cloudflare SFU keys |

## Where it stands (28 October 2026)

- Phases 1–6 are built on the branch `phases-1-to-6`, pushed to GitHub and not merged. `main`, which Render runs, has Phase 0 only.
- To ship them: the steps in [SETUP.md](SETUP.md). Each feature stays hidden or falls back until its key is in, so merging before adding keys is safe.
- Cloudflare Realtime (the voice relay and the voice-room server) asks for a card or PayPal before it turns on, even for the free 1,000 GB. Without it, voice in games still connects directly on most networks, and voice rooms are text only. A no-card option for the relay is not built yet: Metered's free Open Relay (20 GB a month, ports 80 and 443), used by `voice/ice.py` when its key is set.
- Still to try for real: voice on two phones over mobile data, voice rooms through the SFU, and 8 people in a room for an hour.
- Later: give far-away players back half their round trip when they find a word (Phase 4).

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
- [x] **Tests run on GitHub Actions** on every push and pull request (`.github/workflows/tests.yml`); first green on PR #1.

## Phase 1 — Foundation

The changes the social features stand on. Players should notice nothing, except that a game no longer waits for someone who left.

Decided while building it:

- **Usernames stay the key.** They are unique and chosen by the player. Google sign-in (Phase 2) asks a new player to choose one too, so nothing has to move to ids, and friends can be found by name.
- **Lobby and game stay two pages.** Voice (Phase 5) rejoins on its own when the page changes, at the cost of about a second of silence when a game starts and ends. That is less risk than rebuilding both pages as one.
- **The turn loop stays in `GameConsumer`.** Its methods only need the channel layer and the room's group, so a consumer with no socket (`driver_for`) can move a game on from a timer. No player's socket has to "own" the room.
- **New features get their own apps** (`accounts`, `social`, `voice`), and `game` stays the game. Renaming an installed app would mean moving tables on Neon for nothing a player sees.
- **The app-wide socket** (`/ws/me/`) arrives with its first user, friends, in Phase 3.
- **`ALLOWED_HOSTS` is opt-in** (`DJANGO_ALLOWED_HOSTS`). A wrong value would answer every request with 400, so it isn't guessed while nobody is watching the deploy. DEBUG stays on by default so the local setup still needs no `.env`.

Done:

- [x] **A player who drops mid-game is out after 30 seconds** (`GAME_GRACE_SECONDS`), so nobody waits up to 100 seconds for their time bank to drain. Coming back sooner keeps them in the game. A dropped picker gets a word picked at once.
- [x] **The game page's Leave button puts you out at once**, as its dialog always said it would. Everyone else sees "left the game" instead of "out of time".
- [x] **Each player's open pages are counted.** Closing one of two tabs doesn't make you away, and a socket left over from before Play Again can't either.
- [x] **The hunt never starts after the game has ended**, for example when someone leaves during the 6-second word reveal.
- [x] **Hardening:** HSTS for a month when DEBUG is off, and an opt-in Host-header allow list.

Done when: all tests pass, with new ones for dropping, leaving and tabs (129 pass).

## Phase 2 — Google sign-in and profiles

Decided while building it:

- **Google's own button, with the token checked on the server, instead of django-allauth.** Google Identity Services hands the page a signed ID token. `accounts/google.py` checks Google's signature (with PyJWT, against Google's published keys, which it caches), that the token is for this app (its audience is our client ID), and that it hasn't expired. That is one view and two profile fields, instead of allauth's tables, settings and pages. The only setting is the client ID, and it isn't a secret.
- **No separate display name and no friend code.** A new player chooses a unique game name once, under the same rules as a PIN sign-up, so friends find each other by name.
- **PIN sign-up stays open.** It's the zero-friction way in, and the demo still needs no account at all. Google is offered first once it's set up.
- **No email is stored**, only Google's account id and the link to the account's picture.

Done:

- [x] Sign in with Google on the home page, hidden until `GOOGLE_CLIENT_ID` is set. A new player picks a name; a returning one goes straight in.
- [x] PIN players link Google from their profile and keep their name and stats.
- [x] Profiles show the player's picture, stats, rank, and last 20 games with who was in them. Anyone signed in can open anyone's.
- [x] Every game between people is kept as a `Match`, with each player's `MatchPlayer` result, in the same transaction as the stats.
- [x] Google pictures show in the lobby, loaded from Google's CDN. Only `googleusercontent.com` links are kept.
- [x] "Delete my account" on the profile page removes the player and everything kept about them.
- [x] A privacy page, linked from the menu and the home page.
- [x] The server now accepts only letters and digits in names, and the leaderboard escapes names.
- [x] Saving a user no longer re-saves their profile. That happened on every sign-in, and it could write a stale copy back over newer stats.

Done when: a new person signs in with Google in two taps, and an existing PIN player keeps their stats after linking. Every flow passes with Google's check mocked; a real sign-in needs the client ID ([SETUP.md](SETUP.md)).

## Phase 3 — Friends

Done:

- [x] **Friend requests**, one per pair, answered with accept or decline; the sender can cancel. Two requests that cross become a friendship at once. `Friendship` is one row per pair, lower id first, and the database enforces both rules.
- [x] **Find people by name** (names are unique), on the friends page or from anyone's profile: tap a name in your recent games.
- [x] **Block** ends a friendship and any requests, stops new ones both ways, and hides your profile from them. Which of you blocked the other is never shown.
- [x] **Online status** comes from an in-memory count of each player's open `/ws/me/` sockets (`social/presence.py`), with 10 seconds of grace so moving between pages never flickers you offline. Friends see "Online", "In a game" (a game page is open) or "Offline", pushed over their own socket. None of it touches Postgres (rule 2). Postgres is read only when a socket opens or friends change.
- [x] **Every page knows**: a friend request shows as a notice on whatever page is open, with a count on the home page's Friends button. An open friends page refreshes itself when its lists change.
- [x] Each player can send 20 friend requests a day. Demo guests can't use friends.

Done when: two accounts friend each other and see each other come online without refreshing. Checked in the browser with two players in two tabs: request, notice, accept, both online, then offline 10 seconds after one left.

## Phase 4 — Play together

Done:

- [x] **Invites.** Tap **Play** next to a friend who is online, on the friends page. You go to a new room's lobby, and they get a notice on whatever page they have open, with **Join** and **Not now**. From a lobby, its **Invite friends** list invites them to that room. "Not now" tells you, and only someone whose invite arrived can send it. An invite is just a notice with a room code, so nothing is stored. The notice goes away after 60 seconds, and each player can send 10 invites in 10 minutes. Friends who are offline or in a game can't be invited.
- [x] **Random matches** (`game/matchmaking.py`). An in-memory queue: once two players are waiting, it waits 4 more seconds for others, then makes matches of up to 4, oldest first. Two people who blocked each other are never put together; that is the one Postgres read, once per match. The match's lobby starts by itself once everyone has arrived. After 20 seconds it starts with whoever came, or, if only one did, sends them back to the queue. The waiting page offers Robo after 20 seconds. Random matches have no voice.

Later: give far-away players back half their measured round trip when they find a word, since one Render region serves everyone.

Done when: a friend is in your room two taps after you open the friends list, and a random match (or a Robo game) starts within 30 seconds. Checked in the browser with two players: Play, notice, Join, both in one lobby; then both on the random page, matched within 7 seconds, and the game started by itself.

## Phase 5 — Voice in games

Decided while building it:

- **Signalling has its own socket**, `/ws/voice/<room>/`, so the game's sockets stay as they were and voice can be off without touching them.
- **No push-to-talk yet.** Mute is one tap, and phones' echo cancellation and noise suppression are on.
- **"Friends-only" means rooms people join by code or invite.** Random matches have no voice at all.

Done:

- [x] **WebRTC, peer to peer, up to 4 in a room** (`voice/consumers.py`). The server introduces players, and passes each pair's offer, answer and network candidates only to the player they're for. The newcomer calls everyone already talking. If a path fails after a network change, the same side always calls again. A fifth player is told voice is full.
- [x] **STUN from Google and Cloudflare. TURN from Cloudflare**, with credentials made on the server (`voice/ice.py`): four hours long, fetched once an hour, port 53 dropped. Credentials go only to players in a room with voice, so nobody can fetch them to relay anything else. Without the keys, voice uses STUN alone.
- [x] **The microphone is only asked for when the player taps Voice.** Mute (the others see it), a speaking ring on each person's chip, and Leave. The bar floats at the bottom of the lobby and sits in the game header, where it never covers the board.
- [x] **Voice follows the player from the lobby to the game and back.** The next page rejoins by itself; the newer socket replaces the old one, and the old one closing can't take the player out.
- [x] **People who blocked each other are never introduced**, and the server passes nothing between them.

Done when: two phones on different mobile networks talk through a whole game. Checked with two browser tabs, using a test tone in place of a microphone (the in-app browser blocks real ones): connected both ways, about 23 KB of audio each way in the lobby and again from the game header, and mute showed on the other side. Two real phones on mobile data still need trying once it's deployed with the TURN keys.

## Phase 6 — Voice rooms (up to 8)

Decided while building it:

- **Rooms live in memory** (rule 4), like game rooms: a restart closes them. Only reports go to Postgres.
- **Room chat isn't stored.** The server passes each message along and forgets it.
- **Demo guests can't use rooms.** Strangers need a real name someone can report.
- **A reload isn't leaving.** An owner who leaves has 30 seconds to come back. After that the room goes to whoever has been there longest, or closes if it's empty.

Done:

- [x] **Rooms** (`voice/rooms.py`): a public list, busiest first, at **Voice rooms** on the home page. A room has a name (or "Asha's room") and holds 8. Each player can open 5 rooms an hour. Its socket, `/ws/rooms/<id>/`, carries who is in it, the chat, and the owner's tools.
- [x] **Voice through Cloudflare's Realtime SFU** (`voice/sfu.py`). Each person sends their voice once and receives the others'. Django makes every SFU call (publish, pull, renegotiate), so the app secret never reaches a page, and a pull only brings in people the player may hear. Without the keys, rooms work with text chat only.
- [x] **Moderation came first.** The owner can mute (it holds through a reload, and every page silences that player too), remove (they can't come back) and lock (the owner still gets in). Anyone can report (kept, 5 an hour per player; read them with `python manage.py list_reports`) or block. People blocked with each other, either way, don't see, hear or read each other in a room. Nobody joins a room whose owner they're blocked with.
- [x] **Chat**: up to 300 characters, one message a second.
- Budget: a full 8-person room uses roughly 1–1.3 GB an hour of Cloudflare's 1,000 GB, so about 800 room-hours a month fit. Render only carries a room's small messages: who is in it, chat lines, and the SFU offers and answers.

Done when: 8 people talk in a room for an hour, and the owner can mute and kick. Checked in the browser with two players: the room listed and joined, chat both ways, mute (still on after a reload), remove (told, sent back, can't return), lock, and the owner's reload keeping the room. The check found three bugs, now fixed: the chat box covered the member menu, a reload undid a mute, and a reload cost the owner the room. Voice through the SFU needs the Cloudflare keys and real people: 8 people for an hour is still to do.

## How each phase is built

- `main` always deploys. A phase lands as small commits, and each one passes CI.
- Game rules, limits and permissions get tests before the code that uses them.
- Each phase adds a section to [ARCHITECTURE.md](ARCHITECTURE.md): what was decided and why, with the numbers.
- Before a phase is merged, its author can explain it without help. For example: what happens when two friend requests cross? When a socket drops in the middle of an invite? Why does voice need TURN?
