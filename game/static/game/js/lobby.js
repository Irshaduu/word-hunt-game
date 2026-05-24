/**
 * Lobby WebSocket logic for Word Hunt.
 * Handles player list updates and game start.
 */

(function() {
    'use strict';

    // --- Constants ---
    const ANIMAL_EMOJIS = ['🐱', '🐶', '🦊', '🐰', '🐻', '🐼', '🐨', '🦁', '🐸', '🐵'];
    const AVATAR_COLORS = [
        'rgba(255,107,157,0.2)', 'rgba(192,132,252,0.2)', 'rgba(103,232,249,0.2)',
        'rgba(251,191,36,0.2)', 'rgba(52,211,153,0.2)', 'rgba(251,113,133,0.2)',
        'rgba(129,140,248,0.2)', 'rgba(34,211,238,0.2)', 'rgba(249,115,22,0.2)',
        'rgba(45,212,191,0.2)',
    ];

    // --- WebSocket Setup ---
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/lobby/${ROOM_CODE}/?username=${encodeURIComponent(USERNAME)}`;

    let ws = null;
    let reconnectAttempts = 0;
    const MAX_RECONNECT = 10;

    function connect() {
        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            console.log('Lobby WS connected');
            reconnectAttempts = 0;
        };

        ws.onclose = (e) => {
            console.log('Lobby WS closed:', e.code);
            if (reconnectAttempts < MAX_RECONNECT) {
                const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 10000);
                reconnectAttempts++;
                setTimeout(connect, delay);
            }
        };

        ws.onerror = (e) => {
            console.error('Lobby WS error:', e);
        };

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            handleMessage(data);
        };
    }

    function handleMessage(data) {
        switch (data.type) {
            case 'player_update':
                updatePlayerList(data.players, data.creator);
                break;
            case 'game_starting':
                navigateToGame();
                break;
            case 'error':
                showError(data.message);
                break;
        }
    }

    // --- UI Updates ---

    function getAvatarForName(name) {
        let hash = 0;
        for (let i = 0; i < name.length; i++) {
            hash = ((hash << 5) - hash + name.charCodeAt(i)) | 0;
        }
        const idx = Math.abs(hash) % ANIMAL_EMOJIS.length;
        return {
            emoji: ANIMAL_EMOJIS[idx],
            color: AVATAR_COLORS[idx],
        };
    }

    function updatePlayerList(players, creator) {
        const listEl = document.getElementById('player-list');
        const countEl = document.getElementById('player-count');

        countEl.textContent = `(${players.length}/5)`;

        listEl.innerHTML = '';
        players.forEach((player, index) => {
            const avatar = getAvatarForName(player.username);
            const isHost = player.username === creator;
            const isYou = player.username === USERNAME;

            const item = document.createElement('div');
            item.className = 'player-item';
            item.style.animationDelay = `${index * 0.1}s`;

            let badges = '';
            if (isHost) badges += '<span class="player-badge badge-host">Host</span>';
            if (isYou) badges += '<span class="player-badge badge-you">You</span>';

            item.innerHTML = `
                <div class="player-avatar" style="background: ${avatar.color}">${avatar.emoji}</div>
                <span class="player-name">${escapeHtml(player.username)}</span>
                ${badges}
            `;

            listEl.appendChild(item);
        });

        // Update start button state
        if (IS_CREATOR) {
            const startBtn = document.getElementById('btn-start');
            const noteEl = document.getElementById('btn-start-note');
            if (players.length >= 2) {
                startBtn.disabled = false;
                noteEl.textContent = `${players.length} players ready!`;
            } else {
                startBtn.disabled = true;
                noteEl.textContent = 'Need at least 2 players';
            }
        }
    }

    function navigateToGame() {
        window.location.href = `/game/${ROOM_CODE}/`;
    }

    function showError(message) {
        alert(message); // Simple for now
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // --- Event Listeners ---

    // Start Game button
    if (IS_CREATOR) {
        document.getElementById('btn-start').addEventListener('click', () => {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: 'start_game' }));
            }
        });
    }

    // Copy room code
    document.getElementById('btn-copy').addEventListener('click', () => {
        navigator.clipboard.writeText(ROOM_CODE).then(() => {
            const btn = document.getElementById('btn-copy');
            btn.textContent = '✅ Copied!';
            setTimeout(() => { btn.textContent = '📋 Copy'; }, 2000);
        }).catch(() => {
            // Fallback
            const textarea = document.createElement('textarea');
            textarea.value = ROOM_CODE;
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
            const btn = document.getElementById('btn-copy');
            btn.textContent = '✅ Copied!';
            setTimeout(() => { btn.textContent = '📋 Copy'; }, 2000);
        });
    });

    // --- Initialize ---
    connect();

})();
