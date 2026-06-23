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

- **Ephemeral SQLite vs. Persistent Database:** We utilize an SQLite file (`db.sqlite3`) for user profiles and leaderboards. On Render's Free Tier, the filesystem is ephemeral, meaning database resets occur during deployments or prolonged sleep states. 
- **The UptimeBot Strategy:** To prevent the Render service from entering its 15-minute inactivity sleep cycle (which would wipe the SQLite database and cause cold-start delays), we implemented an external UptimeBot. This is a pragmatic, zero-cost DevOps mitigation strategy that helps minimize sleep cycles and cold starts without requiring a paid persistent volume.

## 3. In-Memory State Management & YAGNI

The system uses Django Channels with the `InMemoryChannelLayer` and a global Python dictionary (`ROOMS = {}`) to manage the entire game state.

- **Why Not Redis?** Introducing a message broker like Redis is standard practice for horizontal scaling. However, our target scale is **under 50 concurrent users** (friends, family, and office mates). Deploying a distributed caching layer for 50 users violates the YAGNI (You Aren't Gonna Need It) principle. 
- **The Trade-Off:** The `InMemoryChannelLayer` locks the application to a **single server instance**. For our specified user base, this single-instance architecture is not a bottleneck; rather, it's a highly efficient design that eliminates network latency between the app server and a cache layer, keeping latency low and avoiding unnecessary infrastructure complexity.

## 4. Web Audio API vs. Audio Files

Instead of serving static `.mp3` or `.wav` files (which consume bandwidth, increase load times, and complicate deployment), all game sound effects—including the start fanfare, countdown ticks, elimination buzzers, and victory chords—are synthesized mathematically in real-time using the browser's **Web Audio API**.

This approach leverages native browser capabilities while reducing the application's footprint.

## 5. Real-Time Reconnection Strategy

Real-world mobile networks are flaky. To handle this:
- We don't instantly remove players from a game upon WebSocket disconnect.
- Instead, the server marks them as `is_connected = False`.
- When the client reconnects (using exponential backoff), the server automatically resyncs the entire current game state payload, allowing them to resume exactly where they left off without losing their time bank.

---
*By constraining the system to $0 and acknowledging the <50 user limit, these constraints led to custom state machines and native audio synthesis, resulting in a lightweight and efficient MVP without introducing unnecessary infrastructure complexity.*
