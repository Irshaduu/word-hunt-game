/**
 * A voice room: members, chat and the owner's tools over /ws/rooms/<id>/
 * (voice/consumers.py, RoomConsumer), and the voices through Cloudflare's SFU.
 *
 * With the SFU each person publishes their microphone once and pulls the others' tracks;
 * the server makes the SFU calls (voice/views.py), so its secret never reaches the page.
 * Chat isn't stored anywhere. The owner can mute, remove and lock; anyone can report or block.
 */
(function () {
    'use strict';

    const ROOM = window.ROOM_ID;
    const ME = window.ROOM_ME;
    const CLOSE_CANNOT_JOIN = 4004;  // full, locked, removed earlier, or blocked with the owner
    const CLOSE_REMOVED = 4003;      // the owner removed this player just now

    const membersBox = document.getElementById('room-members');
    const chatLines = document.getElementById('chat-lines');
    const lockLabel = document.getElementById('room-lock');
    const lockBox = document.getElementById('room-lock-box');
    const startBtn = document.getElementById('voice-start');
    const muteBtn = document.getElementById('voice-mute');
    const stopBtn = document.getElementById('voice-stop');
    const voiceNote = document.getElementById('voice-note');

    let ws = null;
    let attempts = 0;
    let room = null;            // the room as this player sees it, from the server

    // Voice through the SFU
    let pc = null;
    let mic = null;
    let myMuted = false;        // muted by me
    let ownerMuted = false;     // muted by the room's owner
    const pulled = {};          // name -> the track of theirs being played
    const audioOf = {};         // name -> <audio>
    const nameOfMid = {};       // transceiver mid -> name, from the SFU's answer to a pull
    let exchange = Promise.resolve();  // SFU exchanges one at a time: each renegotiation ends before the next
    let audioContext = null;
    const levels = {};          // name -> AnalyserNode, for the speaking rings

    // --- The socket ---

    function connect() {
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const socket = new WebSocket(`${protocol}//${location.host}/ws/rooms/${encodeURIComponent(ROOM)}/`);
        ws = socket;
        socket.onopen = () => { attempts = 0; };
        socket.onmessage = (event) => handle(JSON.parse(event.data));
        socket.onclose = (event) => {
            if (socket !== ws) return;
            if (event.code === CLOSE_REMOVED || event.code === CLOSE_CANNOT_JOIN) {
                stopTalking(false);
                goBack(event.code === CLOSE_REMOVED ? 'The owner removed you from this room.' : "You can't join this room.");
                return;
            }
            setTimeout(connect, Math.min(1000 * Math.pow(2, attempts++), 10000));
        };
    }

    function send(message) {
        if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(message));
    }

    function goBack(message) {
        membersBox.textContent = message;
        setTimeout(() => { window.location.href = '/rooms/'; }, 2500);
    }

    function handle(message) {
        if (message.type === 'room') {
            room = message;
            render();
            syncVoices();
        } else if (message.type === 'chat') {
            addChat(message.from, message.text);
        }
    }

    // --- Members and the owner's tools ---

    function render() {
        const isOwner = room.owner === ME;
        lockLabel.hidden = !isOwner;
        lockBox.checked = room.locked;
        const openMenu = membersBox.querySelector('.row-menu[open]');
        const openFor = openMenu ? openMenu.dataset.name : null;  // stays open while the room changes
        membersBox.textContent = '';
        room.members.forEach(member => {
            const row = document.createElement('div');
            row.className = 'friend-row';
            const chip = document.createElement('span');
            chip.className = 'voice-chip' + (member.muted ? ' is-muted' : '');
            chip.dataset.voice = member.name;
            chip.textContent = member.name.charAt(0);
            const who = document.createElement('span');
            who.className = 'friend-row__name';
            who.textContent = member.name + (member.name === ME ? ' (you)' : '');
            row.append(chip, who);
            const about = [];
            if (member.name === room.owner) about.push('owner');
            if (member.muted) about.push('muted by the owner');
            else if (member.track) about.push('in the voice chat');
            if (about.length) {
                const tag = document.createElement('span');
                tag.className = 'room-tag';
                tag.textContent = about.join(' · ');
                row.appendChild(tag);
            }
            if (member.name !== ME) row.appendChild(menu(member, isOwner, member.name === openFor));
            membersBox.appendChild(row);
        });
        const me = room.members.find(m => m.name === ME);
        ownerMuted = !!(me && me.muted);
        applyMic();
        applyListening();
    }

    function menu(member, isOwner, open) {
        const details = document.createElement('details');
        details.className = 'row-menu';
        details.dataset.name = member.name;
        details.open = open;
        details.innerHTML = '<summary><i class="ph-bold ph-dots-three"></i></summary><div class="row-menu__items"></div>';
        details.querySelector('summary').setAttribute('aria-label', `More for ${member.name}`);
        const items = details.querySelector('.row-menu__items');
        const item = (label, onClick) => {
            const button = document.createElement('button');
            button.type = 'button';
            button.textContent = label;
            button.addEventListener('click', () => { details.open = false; onClick(); });
            items.appendChild(button);
        };
        if (isOwner) {
            item(member.muted ? 'Unmute' : 'Mute', () => send({ type: 'mute', name: member.name, muted: !member.muted }));
            item('Remove from the room', () => {
                if (confirm(`Remove ${member.name}? They can't come back to this room.`)) send({ type: 'remove', name: member.name });
            });
        }
        item('Report', () => report(member.name));
        item('Block', () => block(member.name));
        return details;
    }

    lockBox.addEventListener('change', () => send({ type: 'lock', locked: lockBox.checked }));

    function notice(text) {
        if (window.WordHuntMe) window.WordHuntMe.toast(text);
        else alert(text);
    }

    async function formPost(url, fields) {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'X-CSRFToken': window.CSRF_TOKEN },
            body: new URLSearchParams(fields || {}),
        });
        return (await response.json().catch(() => ({}))).message || "That didn't go through. Try again.";
    }

    async function report(name) {
        const reason = prompt(`What did ${name} do? (optional)`);
        if (reason === null) return;
        notice(await formPost(`/rooms/${ROOM}/report/${encodeURIComponent(name)}/`, { reason }));
    }

    async function block(name) {
        if (!confirm(`Block ${name}? Neither of you will hear, see or read the other anywhere in Word Hunt.`)) return;
        notice(await formPost(`/rooms/${ROOM}/block/${encodeURIComponent(name)}/`));
    }

    // --- Chat: passed along by the server, never stored ---

    function addChat(from, text) {
        const line = document.createElement('div');
        line.className = 'chat-line';
        const who = document.createElement('b');
        who.textContent = from === ME ? 'You' : from;
        line.append(who, document.createTextNode(' ' + text));
        chatLines.appendChild(line);
        while (chatLines.children.length > 200) chatLines.firstChild.remove();
        chatLines.scrollTop = chatLines.scrollHeight;
    }

    document.getElementById('chat-form').addEventListener('submit', (event) => {
        event.preventDefault();
        const input = document.getElementById('chat-input');
        if (input.value.trim()) send({ type: 'chat', text: input.value });
        input.value = '';
    });

    // --- Voice through the SFU ---

    async function postJSON(url, body) {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'X-CSRFToken': window.CSRF_TOKEN, 'Content-Type': 'application/json' },
            body: JSON.stringify(body || {}),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || `The server said ${response.status}`);
        return data;
    }

    function setNote(text) {
        if (voiceNote) voiceNote.textContent = text || '';
    }

    async function startTalking() {
        startBtn.disabled = true;
        setNote('Connecting…');
        try {
            mic = await navigator.mediaDevices.getUserMedia({
                audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
                video: false,
            });
            pc = new RTCPeerConnection({ iceServers: [{ urls: 'stun:stun.cloudflare.com:3478' }], bundlePolicy: 'max-bundle' });
            pc.ontrack = hear;
            const transceiver = pc.addTransceiver(mic.getAudioTracks()[0], { direction: 'sendonly' });
            await pc.setLocalDescription(await pc.createOffer());
            const reply = await postJSON(`/rooms/${ROOM}/sfu/publish/`, { sessionDescription: pc.localDescription, mid: transceiver.mid });
            await pc.setRemoteDescription(reply.sessionDescription);
            listen(ME, mic);
            setNote('');
            startBtn.hidden = true;
            muteBtn.hidden = false;
            stopBtn.hidden = false;
            applyMic();
            syncVoices();
        } catch (error) {
            stopTalking(false);
            setNote(error && error.name === 'NotAllowedError' ? 'Allow the microphone to talk.' : (error.message || "Voice couldn't start."));
        }
        startBtn.disabled = false;
    }

    function stopTalking(tellServer) {
        if (pc) pc.close();
        if (mic) mic.getTracks().forEach(track => track.stop());
        pc = null;
        mic = null;
        Object.keys(audioOf).forEach(name => { audioOf[name].srcObject = null; delete audioOf[name]; });
        Object.keys(pulled).forEach(name => { delete pulled[name]; });
        Object.keys(levels).forEach(name => { delete levels[name]; });
        if (startBtn) {
            startBtn.hidden = false;
            muteBtn.hidden = true;
            stopBtn.hidden = true;
        }
        if (tellServer) postJSON(`/rooms/${ROOM}/sfu/stop/`).catch(() => {});
    }

    function hear(event) {
        const name = nameOfMid[event.transceiver.mid];
        if (!name) return;
        const audio = audioOf[name] || new Audio();
        audio.autoplay = true;
        audio.srcObject = new MediaStream([event.track]);
        audioOf[name] = audio;
        audio.play().catch(() => setNote('Tap anywhere to hear the others.'));
        listen(name, audio.srcObject);
        applyListening();
    }

    /** Play everyone the room says is talking, and stop anyone who left, stopped or was blocked. */
    function syncVoices() {
        if (!pc || !room) return;
        Object.keys(pulled).forEach(name => {
            const member = room.members.find(m => m.name === name);
            if (!member || member.track !== pulled[name]) {
                if (audioOf[name]) audioOf[name].srcObject = null;
                delete audioOf[name];
                delete pulled[name];
                delete levels[name];
            }
        });
        const wanted = room.members.filter(m => m.name !== ME && m.track && pulled[m.name] !== m.track);
        if (!wanted.length) return;
        wanted.forEach(m => { pulled[m.name] = m.track; });
        exchange = exchange.then(async () => {
            if (!pc) return;
            const reply = await postJSON(`/rooms/${ROOM}/sfu/pull/`, { names: wanted.map(m => m.name) });
            reply.tracks.forEach(track => { if (track.mid && track.name) nameOfMid[track.mid] = track.name; });
            if (reply.requiresImmediateRenegotiation && pc) {
                await pc.setRemoteDescription(reply.sessionDescription);
                await pc.setLocalDescription(await pc.createAnswer());
                await postJSON(`/rooms/${ROOM}/sfu/renegotiate/`, { sessionDescription: pc.localDescription });
            }
        }).catch(error => {
            wanted.forEach(m => { delete pulled[m.name]; });
            setNote(error.message || "Couldn't connect to the others' voices.");
        });
    }

    function applyMic() {
        if (mic) mic.getAudioTracks().forEach(track => { track.enabled = !(myMuted || ownerMuted); });
        if (muteBtn) {
            muteBtn.textContent = ownerMuted ? 'Muted by the owner' : (myMuted ? 'Unmute' : 'Mute');
            muteBtn.disabled = ownerMuted;
        }
    }

    // Everyone mutes a player the owner muted, so a page that ignored the mute isn't heard either.
    function applyListening() {
        if (!room) return;
        room.members.forEach(member => {
            if (audioOf[member.name]) audioOf[member.name].muted = member.muted;
        });
    }

    if (startBtn) {
        startBtn.addEventListener('click', startTalking);
        muteBtn.addEventListener('click', () => { myMuted = !myMuted; applyMic(); });
        stopBtn.addEventListener('click', () => stopTalking(true));
    }
    // A page whose sound was blocked by the browser's autoplay rules plays on the first tap.
    document.addEventListener('click', () => {
        Object.values(audioOf).forEach(audio => { if (audio.paused) audio.play().catch(() => {}); });
        if (audioContext) audioContext.resume();
    });
    window.addEventListener('pagehide', () => stopTalking(false));

    // --- Who is speaking: a ring on their chip ---

    function listen(name, stream) {
        try {
            audioContext = audioContext || new (window.AudioContext || window.webkitAudioContext)();
            const analyser = audioContext.createAnalyser();
            analyser.fftSize = 512;
            audioContext.createMediaStreamSource(stream).connect(analyser);
            levels[name] = analyser;
        } catch (error) {
            // No rings, but the sound still plays.
        }
    }

    const samples = new Float32Array(512);
    setInterval(() => {
        Object.entries(levels).forEach(([name, analyser]) => {
            analyser.getFloatTimeDomainData(samples);
            let sum = 0;
            for (const sample of samples) sum += sample * sample;
            const quiet = (name === ME && (myMuted || ownerMuted));
            const speaking = Math.sqrt(sum / samples.length) > 0.02 && !quiet;
            membersBox.querySelectorAll(`[data-voice="${CSS.escape(name)}"]`).forEach(el => {
                el.classList.toggle('is-speaking', speaking);
            });
        });
    }, 150);

    connect();
})();
