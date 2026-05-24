# Word Hunt 🎯

A real-time, multiplayer word-finding game built with **Django** and **WebSockets**. Create a room, invite up to 4 friends, and race against the clock to find hidden words on the board!

## Features ✨
- **Real-time Multiplayer:** Powered by Django Channels and WebSockets for instant interactions.
- **Dynamic Gameplay:** One player secretly picks a word from the board, and the other players scramble to find it before time runs out.
- **Time Bank System:** Every player starts with 100 seconds. Time ticks down while you're hunting. If your timer hits zero, you're eliminated!
- **Candy Pop Aesthetic:** A vibrant, smooth, and modern UI with glassmorphism effects and fun micro-animations.
- **Mobile Friendly:** Fully responsive design built to look great on phones.

## Tech Stack 🛠️
- **Backend:** Python, Django, Django Channels (WebSockets)
- **Frontend:** HTML5, Vanilla JavaScript, CSS3 (No heavy frontend frameworks)

## How to Play 🎮
1. **Join/Create:** Enter your name and either create a new room or join a friend's room using a 3-letter code.
2. **The Picker:** In each turn, one player gets 15 seconds to pick a word from the chaotic board.
3. **The Hunt:** Once the word is picked, it flashes on screen for 1.5 seconds. Then, the hunt begins! The other players must find and click the word on their screen.
4. **Win Condition:** Keep finding words to conserve your time bank. The last player standing with time left wins the game!

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
