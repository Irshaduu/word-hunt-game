/**
 * Game WebSocket logic for Word Hunt.
 * Handles board rendering, turn management, timer display,
 * word picking/finding, and game over.
 */

(function() {
    'use strict';

    // --- State ---
    let gameState = null;
    let ws = null;
    let reconnectAttempts = 0;
    const MAX_RECONNECT = 15;
    let timerInterval = null;
    let myTimerStart = null;  // local timestamp for smooth countdown
    let myTimeBank = 100;
    let isEliminated = false;
    let isHunting = false;
    let pickTimerInterval = null;

    // --- WebSocket Setup ---
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/game/${ROOM_CODE}/?username=${encodeURIComponent(USERNAME)}`;

    function connect() {
        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            console.log('Game WS connected');
            reconnectAttempts = 0;
        };

        ws.onclose = (e) => {
            console.log('Game WS closed:', e.code);
            stopTimer();
            if (reconnectAttempts < MAX_RECONNECT) {
                const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 10000);
                reconnectAttempts++;
                setTimeout(connect, delay);
            }
        };

        ws.onerror = (e) => console.error('Game WS error:', e);

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            handleMessage(data);
        };
    }

    function send(data) {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify(data));
        }
    }

    // --- Message Handler ---
    function handleMessage(data) {
        console.log('MSG:', data.type, data);
        switch (data.type) {
            case 'game_state':
                handleGameState(data);
                break;
            case 'word_picked':
                handleWordPicked(data);
                break;
            case 'hunt_start':
                handleHuntStart(data);
                break;
            case 'player_found':
                handlePlayerFound(data);
                break;
            case 'player_eliminated':
                handlePlayerEliminated(data);
                break;
            case 'round_end':
                handleRoundEnd(data);
                break;
            case 'new_turn':
                handleNewTurn(data);
                break;
            case 'game_over':
                handleGameOver(data);
                break;
            case 'error':
                console.warn('Server error:', data.message);
                break;
        }
    }

    // --- Game State ---
    function handleGameState(data) {
        gameState = data;
        syncMyState(data.players);
        renderScoreboard(data.players, data.current_picker);
        renderBoard(data.board);
        updateTurnBanner(data.current_picker, data.state);
        setWordClickMode(data.state, data.current_picker);

        // Restore hunting state on reconnect
        if (data.state === 'hunting') {
            const me = data.players.find(p => p.username === USERNAME);
            if (me && !me.found_current_word && data.current_picker !== USERNAME && !isEliminated) {
                isHunting = true;
                myTimeBank = me.time_bank;
                myTimerStart = Date.now();
            }
            startTimer();
        }
    }

    function syncMyState(players) {
        const me = players.find(p => p.username === USERNAME);
        if (me) {
            myTimeBank = me.time_bank;
            isEliminated = me.is_eliminated;
            if (isEliminated) {
                const el = document.getElementById('eliminated-overlay');
                el.classList.add('visible');
                setTimeout(() => el.classList.remove('visible'), 4000);
            }
        }
    }

    // --- Scoreboard ---
    function renderScoreboard(players, currentPicker) {
        const sb = document.getElementById('scoreboard');
        sb.innerHTML = '';

        players.forEach(p => {
            const card = document.createElement('div');
            card.className = 'score-card';
            if (p.username === currentPicker) card.classList.add('active-picker');
            if (p.username === USERNAME) card.classList.add('is-you');
            if (p.is_eliminated) card.classList.add('eliminated');
            if (p.found_current_word) card.classList.add('found-word');

            const timeClass = p.time_bank <= 10 ? 'time-critical' : p.time_bank <= 30 ? 'time-low' : '';

            card.innerHTML = `
                <div class="score-name">${escapeHtml(p.username)}${p.username === USERNAME ? ' (you)' : ''}</div>
                <div class="score-time ${timeClass}" data-player="${escapeHtml(p.username)}">${p.time_bank.toFixed(1)}s</div>
                ${p.is_eliminated
                    ? '<div class="score-eliminated">OUT</div>'
                    : `<div class="score-words">${p.words_found} found</div>`
                }
            `;
            sb.appendChild(card);
        });
    }

    // --- Board Rendering ---
    function renderBoard(board) {
        const arena = document.getElementById('arena');
        arena.innerHTML = '';

        board.forEach(item => {
            const el = document.createElement('div');
            el.className = 'arena-word';
            el.textContent = item.word;
            el.dataset.word = item.word;
            el.style.cssText = `
                left: ${item.x}%;
                top: ${item.y}%;
                font-size: ${item.fontSize}px;
                color: ${item.color};
                font-family: ${item.font || "'Fredoka', cursive"};
                transform: rotate(${item.rotation}deg);
            `;

            el.addEventListener('click', () => onWordClick(item.word));
            arena.appendChild(el);
        });
    }

    // --- Turn Banner ---
    function updateTurnBanner(currentPicker, state) {
        const banner = document.getElementById('turn-banner');
        const text = document.getElementById('turn-text');
        banner.className = 'turn-banner';

        if (state === 'picking') {
            startPickTimer(currentPicker);
        } else {
            stopPickTimer();
            if (state === 'hunting') {
                if (currentPicker === USERNAME) {
                    text.textContent = '😎 You picked the word. Sit back and watch!';
                } else if (isEliminated) {
                    text.textContent = '👀 Watching...';
                } else {
                    banner.classList.add('hunting');
                    text.textContent = '🔍 FIND THE WORD! Quick!';
                }
            } else if (state === 'showing') {
                text.textContent = '👀 Remember this word...';
            } else if (state === 'round_end') {
                text.textContent = '✨ Round over! Next turn coming...';
            } else {
                text.textContent = '';
            }
        }
    }

    function startPickTimer(currentPicker) {
        stopPickTimer();
        let timeLeft = 15;
        const banner = document.getElementById('turn-banner');
        const text = document.getElementById('turn-text');

        const updateText = () => {
            if (currentPicker === USERNAME) {
                banner.classList.add('your-turn');
                text.textContent = `🎯 Your turn! Tap any word to pick it! (${timeLeft}s)`;
            } else {
                text.textContent = `⏳ ${currentPicker} is picking a word... (${timeLeft}s)`;
            }
        };

        updateText();

        pickTimerInterval = setInterval(() => {
            timeLeft--;
            if (timeLeft <= 0) {
                stopPickTimer();
                if (currentPicker === USERNAME && !isEliminated) {
                    // Auto-pick a random word if time runs out
                    const words = Array.from(document.querySelectorAll('.arena-word'));
                    if (words.length > 0) {
                        const randomWord = words[Math.floor(Math.random() * words.length)].dataset.word;
                        onWordClick(randomWord);
                    }
                }
            } else {
                updateText();
            }
        }, 1000);
    }

    function stopPickTimer() {
        if (pickTimerInterval) {
            clearInterval(pickTimerInterval);
            pickTimerInterval = null;
        }
    }

    // --- Word Click Mode ---
    function setWordClickMode(state, currentPicker) {
        const words = document.querySelectorAll('.arena-word');

        if (state === 'picking' && currentPicker === USERNAME && !isEliminated) {
            // Picker mode: can click any word
            words.forEach(w => w.classList.remove('disabled'));
        } else if (state === 'hunting' && currentPicker !== USERNAME && !isEliminated) {
            // Hunter mode: can click words to find
            words.forEach(w => w.classList.remove('disabled'));
        } else {
            // Spectator / waiting: disable clicks
            words.forEach(w => w.classList.add('disabled'));
        }
    }

    function onWordClick(word) {
        if (!gameState) return;

        if (gameState.state === 'picking' && gameState.current_picker === USERNAME) {
            send({ type: 'pick_word', word: word });
        } else if (isHunting && gameState.current_picker !== USERNAME && !isEliminated) {
            send({ type: 'found_word', word: word });
        }
    }

    // --- Word Picked (3-second popup) ---
    function handleWordPicked(data) {
        if (gameState) {
            gameState.state = 'showing';
            gameState.chosen_word = data.word;
        }

        // Picker doesn't see the popup (they already know the word)
        if (data.picker === USERNAME) {
            updateTurnBanner(data.picker, 'showing');
            document.querySelectorAll('.arena-word').forEach(w => w.classList.add('disabled'));
            // Highlight the picked word on the picker's board
            document.querySelectorAll('.arena-word').forEach(el => {
                if (el.dataset.word === data.word) {
                    el.style.outline = '2px solid rgba(251,191,36,0.6)';
                    el.style.borderRadius = '8px';
                }
            });
            return;
        }

        // Other players see the popup
        const overlay = document.getElementById('popup-overlay');
        document.getElementById('popup-picker').textContent = data.picker;
        document.getElementById('popup-word').textContent = data.word;

        // Reset and restart the timer bar animation
        const fill = document.getElementById('popup-timer-fill');
        fill.style.animation = 'none';
        fill.offsetHeight; // force reflow
        fill.style.animation = 'shrink 1.5s linear forwards';

        overlay.classList.add('visible');

        updateTurnBanner(data.picker, 'showing');

        // Disable word clicks during popup
        document.querySelectorAll('.arena-word').forEach(w => w.classList.add('disabled'));
    }

    // --- Hunt Start ---
    function handleHuntStart(data) {
        // Hide popup
        document.getElementById('popup-overlay').classList.remove('visible');

        if (gameState) {
            gameState.state = 'hunting';
            gameState.players = data.players || gameState.players;
        }

        // Show GO! animation
        const goOverlay = document.getElementById('go-overlay');
        goOverlay.classList.add('visible');
        setTimeout(() => goOverlay.classList.remove('visible'), 800);

        // Update state
        syncMyState(data.players || []);
        renderScoreboard(data.players || [], gameState ? gameState.current_picker : '');
        updateTurnBanner(gameState ? gameState.current_picker : '', 'hunting');

        // Start hunting if we are a hunter
        if (gameState && gameState.current_picker !== USERNAME && !isEliminated) {
            isHunting = true;
            myTimerStart = Date.now();

            // Enable clicking
            document.querySelectorAll('.arena-word').forEach(w => w.classList.remove('disabled'));
        } else {
            // Picker or eliminated — disable
            document.querySelectorAll('.arena-word').forEach(w => w.classList.add('disabled'));
        }
        
        startTimer();
    }

    // --- Player Found ---
    function handlePlayerFound(data) {
        // Update scoreboard
        if (data.players) {
            if (gameState) gameState.players = data.players;
            renderScoreboard(data.players, gameState ? gameState.current_picker : '');
        }

        // If it's us
        if (data.username === USERNAME) {
            isHunting = false;
            myTimeBank = data.time_bank;

            // Highlight the found word on the board
            if (gameState && gameState.chosen_word) {
                highlightWord(gameState.chosen_word);
            }

            // Disable further clicking
            document.querySelectorAll('.arena-word').forEach(w => w.classList.add('disabled'));
            updateTurnBanner(gameState ? gameState.current_picker : '', 'hunting');
        }

        // Flash notification
        showToast(`${data.username} found it! (${data.time_taken}s)`);
    }

    function highlightWord(word) {
        document.querySelectorAll('.arena-word').forEach(el => {
            if (el.dataset.word === word) {
                el.classList.add('found');
            }
        });
    }

    // --- Player Eliminated ---
    function handlePlayerEliminated(data) {
        if (data.players) {
            renderScoreboard(data.players, gameState ? gameState.current_picker : '');
        }

        if (data.username === USERNAME) {
            isEliminated = true;
            isHunting = false;
            const el = document.getElementById('eliminated-overlay');
            el.classList.add('visible');
            setTimeout(() => el.classList.remove('visible'), 4000);
            document.querySelectorAll('.arena-word').forEach(w => w.classList.add('disabled'));
        }

        showToast(`💀 ${data.username} is out of time!`);
    }

    // --- Round End ---
    function handleRoundEnd(data) {
        isHunting = false;
        stopTimer();

        if (gameState) gameState.state = 'round_end';
        if (data.players) {
            renderScoreboard(data.players, gameState ? gameState.current_picker : '');
        }

        updateTurnBanner('', 'round_end');
        document.querySelectorAll('.arena-word').forEach(w => w.classList.add('disabled'));
    }

    // --- New Turn ---
    function handleNewTurn(data) {
        gameState = data;
        isHunting = false;
        stopTimer();
        stopPickTimer();

        syncMyState(data.players);
        renderScoreboard(data.players, data.current_picker);
        renderBoard(data.board);
        updateTurnBanner(data.current_picker, data.state);
        setWordClickMode(data.state, data.current_picker);
    }

    // --- Game Over ---
    function handleGameOver(data) {
        isHunting = false;
        stopTimer();
        stopPickTimer();

        // Hide eliminated overlay if showing
        document.getElementById('eliminated-overlay').classList.remove('visible');

        // Build leaderboard
        const lbEl = document.getElementById('leaderboard');
        lbEl.innerHTML = '';

        const rankEmojis = ['🥇', '🥈', '🥉', '4️⃣', '5️⃣'];

        data.leaderboard.forEach((entry, idx) => {
            const row = document.createElement('div');
            row.className = 'lb-row';
            if (idx === 0) row.classList.add('lb-winner');

            row.innerHTML = `
                <span class="lb-rank">${rankEmojis[idx] || (idx + 1)}</span>
                <span class="lb-name">${escapeHtml(entry.username)}${entry.username === USERNAME ? ' (you)' : ''}</span>
                <div class="lb-stats">
                    ${entry.is_eliminated
                        ? '<span class="lb-out">OUT</span>'
                        : `<span class="lb-time">${entry.time_bank.toFixed(1)}s left</span>`
                    }
                    <br><span class="lb-words">${entry.words_found} words found</span>
                </div>
            `;
            lbEl.appendChild(row);
        });

        // Winner info
        document.getElementById('winner-title').textContent = data.winner
            ? `${data.winner} Wins!`
            : 'Game Over!';
        document.getElementById('winner-time').textContent = data.winner
            ? `${data.time_remaining}s remaining`
            : '';

        // Show overlay
        document.getElementById('gameover-overlay').classList.add('visible');

        // Launch confetti
        launchConfetti();
    }

    // --- Timer ---
    function startTimer() {
        stopTimer();
        timerInterval = setInterval(() => {
            if (gameState && gameState.state !== 'hunting') {
                stopTimer();
                return;
            }

            // Sync all players' timers locally
            if (gameState && gameState.players) {
                gameState.players.forEach(p => {
                    // Skip the current picker, eliminated players, and those who already found it
                    if (p.username === gameState.current_picker) return;
                    if (p.is_eliminated || p.found_current_word) return;
                    
                    // Decrement locally
                    p.time_bank = Math.max(0, p.time_bank - 0.1);
                    
                    const timeEl = document.querySelector(`.score-time[data-player="${escapeHtml(p.username)}"]`);
                    if (timeEl) {
                        timeEl.textContent = p.time_bank.toFixed(1) + 's';
                        timeEl.className = 'score-time';
                        if (p.time_bank <= 10) timeEl.classList.add('time-critical');
                        else if (p.time_bank <= 30) timeEl.classList.add('time-low');
                    }
                });
            }
        }, 100);
    }

    function stopTimer() {
        if (timerInterval) {
            clearInterval(timerInterval);
            timerInterval = null;
        }
    }

    // --- Toast Notifications ---
    function showToast(message) {
        const toast = document.createElement('div');
        toast.style.cssText = `
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(0,0,0,0.8);
            backdrop-filter: blur(10px);
            color: white;
            padding: 10px 20px;
            border-radius: 20px;
            font-family: var(--font-body);
            font-size: 0.85rem;
            font-weight: 600;
            z-index: 200;
            animation: slideUp 0.3s ease;
            pointer-events: none;
            border: 1px solid rgba(255,255,255,0.1);
        `;
        toast.textContent = message;
        document.body.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transition = 'opacity 0.5s';
            setTimeout(() => toast.remove(), 500);
        }, 2500);
    }

    // --- Confetti ---
    function launchConfetti() {
        const container = document.getElementById('confetti');
        const colors = ['#FF6B9D', '#C084FC', '#67E8F9', '#FBBF24', '#34D399', '#FB7185', '#818CF8'];

        for (let i = 0; i < 60; i++) {
            const piece = document.createElement('div');
            piece.className = 'confetti-piece';
            piece.style.left = Math.random() * 100 + '%';
            piece.style.background = colors[Math.floor(Math.random() * colors.length)];
            piece.style.width = (Math.random() * 8 + 5) + 'px';
            piece.style.height = (Math.random() * 8 + 5) + 'px';
            piece.style.borderRadius = Math.random() > 0.5 ? '50%' : '2px';
            piece.style.animationDuration = (Math.random() * 2 + 2) + 's';
            piece.style.animationDelay = (Math.random() * 1.5) + 's';
            container.appendChild(piece);
        }
    }

    // --- Helpers ---
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // --- Play Again ---
    document.getElementById('btn-play-again').addEventListener('click', () => {
        window.location.href = '/';
    });

    // --- Initialize ---
    connect();

})();
