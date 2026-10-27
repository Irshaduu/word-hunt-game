/**
 * The app-wide socket (/ws/me/), open on every page for a signed-in player.
 *
 * It keeps friends' online status current on whatever page is open (any element with
 * data-friend="Name" gets data-status="online|in_game|offline"), counts friend requests
 * (elements with data-friend-requests), and shows notices at the top of the page.
 * Pages add their own handlers with WordHuntMe.on(type, handler).
 */
(function () {
    'use strict';

    const CLOSE_CANNOT_JOIN = 4004;  // game/consumers.py: signed out, so don't retry
    const handlers = {};
    let ws = null;
    let attempts = 0;
    let retry = null;

    function on(type, handler) {
        (handlers[type] = handlers[type] || []).push(handler);
    }

    function emit(message) {
        (handlers[message.type] || []).forEach(handler => handler(message));
    }

    function send(message) {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify(message));
            return true;
        }
        return false;
    }

    function connect() {
        clearTimeout(retry);
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const socket = new WebSocket(`${protocol}//${location.host}/ws/me/`);
        ws = socket;
        socket.onopen = () => {
            attempts = 0;
            emit({ type: 'open' });
        };
        socket.onmessage = (event) => emit(JSON.parse(event.data));
        socket.onclose = (event) => {
            if (socket !== ws || event.code === CLOSE_CANNOT_JOIN) return;
            const delay = Math.min(1000 * Math.pow(2, attempts), 30000);
            attempts++;
            retry = setTimeout(connect, delay);
        };
    }

    // Back from another app: reconnect now rather than after the back-off.
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible' && (!ws || ws.readyState === WebSocket.CLOSED)) {
            attempts = 0;
            connect();
        }
    });

    // --- Friends' status and friend requests ---

    function showStatus(name, status) {
        document.querySelectorAll(`[data-friend="${CSS.escape(name)}"]`).forEach(el => {
            el.dataset.status = status;
        });
    }

    function showRequestCount(count) {
        document.querySelectorAll('[data-friend-requests]').forEach(el => {
            el.textContent = count;
            el.hidden = !count;
        });
    }

    let requestCount = 0;
    on('friends', (message) => {
        message.friends.forEach(friend => showStatus(friend.name, friend.status));
        requestCount = message.requests;
        showRequestCount(requestCount);
    });
    on('friend_status', (message) => showStatus(message.name, message.status));
    on('friend_request', (message) => {
        showRequestCount(++requestCount);
        toast(`${message.from} wants to be friends`, [{ label: 'See', href: '/friends/' }]);
    });

    // --- Notices at the top of the page ---

    let stack = null;

    /**
     * Show `text` for `seconds`, with buttons: {label, href} opens a page, {label, onClick}
     * runs code. Returns a function that takes the notice away early.
     */
    function toast(text, actions, seconds) {
        if (!stack) {
            stack = document.createElement('div');
            stack.className = 'me-toasts';
            stack.setAttribute('role', 'status');
            document.body.appendChild(stack);
        }
        const box = document.createElement('div');
        box.className = 'me-toast';
        const words = document.createElement('span');
        words.textContent = text;
        box.appendChild(words);

        let timer = null;
        const close = () => {
            clearTimeout(timer);
            box.remove();
        };
        (actions || []).forEach(action => {
            const button = document.createElement(action.href ? 'a' : 'button');
            button.className = 'me-toast__action' + (action.primary ? ' me-toast__action--primary' : '');
            button.textContent = action.label;
            if (action.href) button.href = action.href;
            button.addEventListener('click', () => {
                if (action.onClick) action.onClick();
                close();
            });
            box.appendChild(button);
        });
        stack.appendChild(box);
        timer = setTimeout(close, (seconds || 6) * 1000);
        return close;
    }

    window.WordHuntMe = { on, send, toast };
    connect();
})();
