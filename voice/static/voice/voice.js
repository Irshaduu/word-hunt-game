/**
 * Voice chat in a game room: peer to peer (WebRTC), up to four players.
 *
 * The server (voice/consumers.py) only introduces players and passes their messages over
 * /ws/voice/<room>/: each pair's offer and answer, and their network candidates. The sound
 * goes straight between browsers, or through Cloudflare's TURN relay when a network won't
 * allow that, never through our server.
 *
 * Being in voice survives moving between the lobby and game pages: the next page rejoins by
 * itself (sessionStorage), and the browser doesn't ask for the microphone again.
 */
(function () {
    'use strict';

    const ROOM = window.VOICE_ROOM;
    const ME = window.VOICE_ME;
    const REMEMBER = `voice:${ROOM}`;   // sessionStorage: 'on' while in this room's voice chat
    const CLOSE_CANNOT_JOIN = 4004;     // the room is gone, voice is full (4), or it's a random match

    let ws = null;
    let mic = null;          // this player's microphone stream
    let iceServers = [];
    let muted = false;
    let state = 'off';
    let note = '';
    let audioContext = null;
    const peers = {};        // name -> {pc, audio, pending candidates, muted}
    const levels = {};       // name -> AnalyserNode, for the speaking rings

    // --- The bar: in the game page's header (#voice-slot), or floating in the lobby ---

    const bar = document.createElement('div');
    bar.className = 'voice-bar';
    const slot = document.getElementById('voice-slot');
    if (!slot) bar.classList.add('voice-bar--floating');
    (slot || document.body).appendChild(bar);

    function chip(name, isMuted) {
        const el = document.createElement('span');
        el.className = 'voice-chip' + (isMuted ? ' is-muted' : '');
        el.dataset.voice = name;
        el.title = name === ME ? 'You' : name;
        el.textContent = name.charAt(0);
        return el;
    }

    function button(act, icon, label, extra) {
        const el = document.createElement('button');
        el.type = 'button';
        el.className = 'voice-btn' + (extra ? ' ' + extra : '');
        el.dataset.act = act;
        el.title = label;
        el.setAttribute('aria-label', label);
        el.innerHTML = `<i class="ph-duotone ${icon}"></i>`;
        return el;
    }

    function render() {
        bar.textContent = '';
        if (state === 'on') {
            const mute = button('mute', muted ? 'ph-microphone-slash' : 'ph-microphone', muted ? 'Unmute' : 'Mute', muted ? 'is-muted' : '');
            mute.setAttribute('aria-pressed', String(muted));
            bar.appendChild(mute);
            const people = document.createElement('span');
            people.className = 'voice-people';
            people.appendChild(chip(ME, muted));
            Object.keys(peers).forEach(name => people.appendChild(chip(name, peers[name].muted)));
            bar.appendChild(people);
            bar.appendChild(button('leave', 'ph-phone-x', 'Leave voice', 'voice-btn--leave'));
        } else if (state === 'connecting') {
            bar.innerHTML = '<span class="voice-note">Connecting voice…</span>';
        } else {
            const join = button('join', 'ph-microphone', 'Join voice chat', 'voice-btn--join');
            join.insertAdjacentHTML('beforeend', '<span>Voice</span>');
            bar.appendChild(join);
        }
        if (note) {
            const words = document.createElement('span');
            words.className = 'voice-note';
            words.textContent = note;
            bar.appendChild(words);
        }
    }

    bar.addEventListener('click', (event) => {
        const act = event.target.closest('[data-act]');
        if (!act) return;
        if (act.dataset.act === 'join') join();
        else if (act.dataset.act === 'mute') toggleMute();
        else if (act.dataset.act === 'leave') leave();
        else if (act.dataset.act === 'hear') hearEveryone();
    });

    // --- Joining and leaving ---

    async function join() {
        state = 'connecting';
        note = '';
        render();
        try {
            const response = await fetch(`/voice/ice/?room=${encodeURIComponent(ROOM)}`);
            iceServers = (await response.json()).iceServers;
            mic = await navigator.mediaDevices.getUserMedia({
                audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
                video: false,
            });
        } catch (error) {
            sessionStorage.removeItem(REMEMBER);
            state = 'off';
            note = error && error.name === 'NotAllowedError' ? 'Allow the microphone to talk.' : "Voice couldn't start.";
            render();
            return;
        }
        mic.getAudioTracks().forEach(track => { track.enabled = !muted; });
        sessionStorage.setItem(REMEMBER, 'on');
        listenTo(ME, mic);
        connect();
    }

    function connect() {
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const socket = new WebSocket(`${protocol}//${location.host}/ws/voice/${encodeURIComponent(ROOM)}/`);
        ws = socket;
        socket.onopen = () => {
            state = 'on';
            render();
            if (muted) send({ type: 'mute', muted: true });
        };
        socket.onmessage = (event) => handle(JSON.parse(event.data));
        socket.onclose = (event) => {
            if (socket !== ws) return;
            Object.keys(peers).forEach(closePeer);
            if (event.code === CLOSE_CANNOT_JOIN) {
                stopMic();
                sessionStorage.removeItem(REMEMBER);
                state = 'off';
                note = 'Voice is full or not available here.';
                render();
            } else if (mic) {
                state = 'connecting';
                render();
                setTimeout(connect, 2000);  // dropped: back in while still in voice
            }
        };
    }

    function leave() {
        sessionStorage.removeItem(REMEMBER);
        const socket = ws;
        ws = null;
        if (socket) socket.close();
        Object.keys(peers).forEach(closePeer);
        stopMic();
        state = 'off';
        note = '';
        render();
    }

    function stopMic() {
        if (mic) mic.getTracks().forEach(track => track.stop());
        mic = null;
        delete levels[ME];
    }

    function toggleMute() {
        muted = !muted;
        if (mic) mic.getAudioTracks().forEach(track => { track.enabled = !muted; });
        send({ type: 'mute', muted });
        render();
    }

    function send(message) {
        if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(message));
    }

    function signal(to, data) {
        send({ type: 'signal', to, data });
    }

    // --- Talking to each player (one RTCPeerConnection each) ---

    function handle(message) {
        switch (message.type) {
            case 'peers':  // everyone already talking: the newcomer calls each
                message.peers.forEach(call);
                render();
                break;
            case 'peer_joined':  // they'll call us; a page of theirs from before is gone
                closePeer(message.name);
                render();
                break;
            case 'peer_left':
                closePeer(message.name);
                render();
                break;
            case 'signal':
                onSignal(message.from, message.data);
                break;
            case 'peer_muted':
                if (peers[message.name]) {
                    peers[message.name].muted = message.muted;
                    render();
                }
                break;
        }
    }

    function newPeer(name) {
        const pc = new RTCPeerConnection({ iceServers });
        const audio = new Audio();
        audio.autoplay = true;
        const peer = { pc, audio, pending: [], muted: false };
        peers[name] = peer;
        mic.getTracks().forEach(track => pc.addTrack(track, mic));
        pc.onicecandidate = (event) => {
            if (event.candidate) signal(name, { candidate: event.candidate });
        };
        pc.ontrack = (event) => {
            audio.srcObject = event.streams[0];
            audio.play().catch(offerToHear);
            listenTo(name, event.streams[0]);
        };
        pc.onconnectionstatechange = () => {
            // A path that failed (a network change): one side, the same one each time, tries again.
            if (pc.connectionState === 'failed' && ME < name) call(name, true);
        };
        return peer;
    }

    async function call(name, restart) {
        const peer = (restart && peers[name]) || newPeer(name);
        await peer.pc.setLocalDescription(await peer.pc.createOffer({ iceRestart: !!restart }));
        signal(name, { sdp: peer.pc.localDescription });
    }

    async function onSignal(name, data) {
        if (!mic) return;
        let peer = peers[name];
        try {
            if (data.sdp) {
                if (data.sdp.type === 'offer') {
                    peer = peer || newPeer(name);
                    await peer.pc.setRemoteDescription(data.sdp);
                    await peer.pc.setLocalDescription(await peer.pc.createAnswer());
                    signal(name, { sdp: peer.pc.localDescription });
                } else if (peer) {
                    await peer.pc.setRemoteDescription(data.sdp);
                }
                if (peer) {
                    for (const candidate of peer.pending.splice(0)) {
                        await peer.pc.addIceCandidate(candidate).catch(() => {});
                    }
                }
                render();
            } else if (data.candidate && peer) {
                if (peer.pc.remoteDescription) await peer.pc.addIceCandidate(data.candidate).catch(() => {});
                else peer.pending.push(data.candidate);
            }
        } catch (error) {
            console.warn('Voice: could not connect to', name, error);
        }
    }

    function closePeer(name) {
        const peer = peers[name];
        if (!peer) return;
        peer.pc.close();
        peer.audio.srcObject = null;
        delete peers[name];
        delete levels[name];
    }

    // A page that rejoined by itself may not play sound until it's tapped (autoplay rules).
    function offerToHear() {
        if (bar.querySelector('[data-act="hear"]')) return;
        bar.appendChild(button('hear', 'ph-speaker-high', 'Tap to hear the others', 'voice-btn--hear'));
    }

    function hearEveryone() {
        Object.values(peers).forEach(peer => peer.audio.play().catch(() => {}));
        if (audioContext) audioContext.resume();
        const hear = bar.querySelector('[data-act="hear"]');
        if (hear) hear.remove();
    }

    // --- Who is speaking: a ring on their chip ---

    function listenTo(name, stream) {
        try {
            audioContext = audioContext || new (window.AudioContext || window.webkitAudioContext)();
            const analyser = audioContext.createAnalyser();
            analyser.fftSize = 512;
            audioContext.createMediaStreamSource(stream).connect(analyser);
            levels[name] = analyser;
        } catch (error) {
            // No rings, but the sound itself still plays.
        }
    }

    const samples = new Float32Array(512);
    setInterval(() => {
        Object.entries(levels).forEach(([name, analyser]) => {
            analyser.getFloatTimeDomainData(samples);
            let sum = 0;
            for (const sample of samples) sum += sample * sample;
            const speaking = Math.sqrt(sum / samples.length) > 0.02 && !(name === ME && muted);
            bar.querySelectorAll(`[data-voice="${CSS.escape(name)}"]`).forEach(el => {
                el.classList.toggle('is-speaking', speaking);
            });
        });
    }, 150);

    render();
    if (sessionStorage.getItem(REMEMBER) === 'on') join();
})();
