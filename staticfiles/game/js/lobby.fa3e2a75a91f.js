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

    // --- Audio System ---
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    let audioCtx = null;

    function initAudio() {
        if (!audioCtx) audioCtx = new AudioContext();
        if (audioCtx.state === 'suspended') audioCtx.resume();
    }

    document.addEventListener('click', () => { if (!audioCtx) initAudio(); }, { once: true });

    function playEpicStartSound() {
        initAudio();
        if (!audioCtx) return;
        const now = audioCtx.currentTime;
        try {
            // Epic rising chord
            const freqs = [261.63, 329.63, 392.00, 523.25]; // C major chord
            freqs.forEach((freq, i) => {
                const osc = audioCtx.createOscillator();
                const gain = audioCtx.createGain();
                osc.type = 'square';
                osc.frequency.setValueAtTime(freq, now + i * 0.1);
                // pitch bend up
                osc.frequency.exponentialRampToValueAtTime(freq * 2, now + 2.0);
                
                gain.gain.setValueAtTime(0, now + i * 0.1);
                gain.gain.linearRampToValueAtTime(0.15, now + i * 0.1 + 0.1);
                gain.gain.exponentialRampToValueAtTime(0.001, now + 2.5);
                
                osc.connect(gain);
                gain.connect(audioCtx.destination);
                osc.start(now + i * 0.1);
                osc.stop(now + 2.5);
            });
            
            // Bass drop sweep
            const bass = audioCtx.createOscillator();
            const bassGain = audioCtx.createGain();
            bass.type = 'sawtooth';
            bass.frequency.setValueAtTime(150, now);
            bass.frequency.exponentialRampToValueAtTime(40, now + 2.0);
            bassGain.gain.setValueAtTime(0.3, now);
            bassGain.gain.exponentialRampToValueAtTime(0.001, now + 2.0);
            bass.connect(bassGain);
            bassGain.connect(audioCtx.destination);
            bass.start(now);
            bass.stop(now + 2.0);
        } catch(e) {}
    }

    // --- WebSocket Setup ---
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/lobby/${ROOM_CODE}/?username=${encodeURIComponent(USERNAME)}`;

    let ws = null;
    let reconnectAttempts = 0;
    let intentionalDisconnect = false;
    const MAX_RECONNECT = 10;

    function connect() {
        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            console.log('Lobby WS connected');
            reconnectAttempts = 0;
        };

        ws.onclose = (e) => {
            console.log('Lobby WS closed:', e.code);
            if (!intentionalDisconnect && reconnectAttempts < MAX_RECONNECT) {
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
                // Show visual feedback that it's starting
                const btn = document.getElementById('btn-start');
                if (btn) {
                    btn.innerHTML = '<i class="ph-duotone ph-rocket-launch" style="font-size: 1.4rem; margin-right: 8px;"></i> Starting...';
                    btn.disabled = true;
                }
                const msg = document.querySelector('.waiting-message p');
                if (msg) msg.textContent = 'Game is starting! Get ready...';
                
                playEpicStartSound();
                setTimeout(navigateToGame, 2500);
                break;
            case 'error':
                showError(data.message);
                break;
        }
    }

    // --- UI Updates ---

    const SPECIAL_AVATARS = {
        "Soo": { emoji: "🐼", color: "rgba(52,211,153,0.2)" },
        "Chanie": { emoji: "🐼", color: "rgba(52,211,153,0.2)" },
        "Soochan": { emoji: "🐼", color: "rgba(52,211,153,0.2)" },
        "Mile": { emoji: "🐱", color: "rgba(255,107,157,0.2)" },
        "Kamila": { emoji: "🐱", color: "rgba(255,107,157,0.2)" },
        "Poocha": { emoji: "🐱", color: "rgba(255,107,157,0.2)" },
        "Neko": { emoji: "🐱", color: "rgba(255,107,157,0.2)" }
    };

    function getAvatarForName(name) {
        for (const [key, avatar] of Object.entries(SPECIAL_AVATARS)) {
            if (name.startsWith(key)) {
                return avatar;
            }
        }

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
        const isHostNow = (USERNAME === creator);

        countEl.textContent = `(${players.length}/10)`;

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

        // Update host UI dynamically
        const startWrapper = document.getElementById('start-action-wrapper');
        const waitingMsg = document.getElementById('waiting-message');
        
        if (isHostNow) {
            if (startWrapper) startWrapper.style.display = 'flex';
            if (waitingMsg) waitingMsg.style.display = 'none';
            
            const startBtn = document.getElementById('btn-start');
            const noteEl = document.getElementById('btn-start-note');
            if (startBtn && noteEl) {
                if (players.length >= 2) {
                    startBtn.disabled = false;
                    noteEl.textContent = `${players.length} players ready!`;
                } else {
                    startBtn.disabled = true;
                    noteEl.textContent = 'Need at least 2 players';
                }
            }
        } else {
            if (startWrapper) startWrapper.style.display = 'none';
            if (waitingMsg) waitingMsg.style.display = 'block';
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
    const btnStart = document.getElementById('btn-start');
    if (btnStart) {
        btnStart.addEventListener('click', () => {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: 'start_game' }));
            }
        });
    }

    // Copy room code
    document.getElementById('btn-copy').addEventListener('click', () => {
        function success() {
            const btn = document.getElementById('btn-copy');
            btn.innerHTML = '✅ Copied!';
            setTimeout(() => { btn.innerHTML = '<i class="ph-duotone ph-copy"></i> Copy'; }, 2000);
        }

        function fallback() {
            const textarea = document.createElement('textarea');
            textarea.value = ROOM_CODE;
            textarea.style.position = 'fixed';
            document.body.appendChild(textarea);
            textarea.select();
            try {
                document.execCommand('copy');
                success();
            } catch (err) {
                alert("Failed to copy code: " + ROOM_CODE);
            }
            document.body.removeChild(textarea);
        }

        if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(ROOM_CODE).then(success).catch(fallback);
        } else {
            fallback();
        }
    });

    // Handle explicit leave and mobile backgrounding
    const btnExitLobby = document.querySelector('.btn-exit-lobby');
    if (btnExitLobby) {
        btnExitLobby.addEventListener('click', () => {
            intentionalDisconnect = true;
            if (ws) ws.close();
        });
    }

    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'hidden') {
            intentionalDisconnect = true;
            if (ws) ws.close();
        } else {
            intentionalDisconnect = false;
            if (!ws || ws.readyState === WebSocket.CLOSED) {
                connect();
            }
        }
    });

    window.addEventListener('pagehide', () => {
        intentionalDisconnect = true;
        if (ws) ws.close();
    });

    // --- Initialize ---
    connect();

})();
