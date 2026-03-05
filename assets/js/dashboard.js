const API = '';

function esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

function readCachedUser() {
  try {
    const raw = localStorage.getItem('dc_user');
    return raw ? JSON.parse(raw) : null;
  } catch (_) {
    localStorage.removeItem('dc_user');
    return null;
  }
}

async function fetchMeWithRetry() {
  for (let attempt = 1; attempt <= 2; attempt++) {
    try {
      const meRes = await fetch(`${API}/api/auth/me`, { credentials: 'include', cache: 'no-store' });
      if (meRes.ok) return await meRes.json();
    } catch (_) {}
    await new Promise((r) => setTimeout(r, 120));
  }
  return null;
}

async function initDashboard() {
  let user = readCachedUser();
  const liveUser = await fetchMeWithRetry();
  if (liveUser) {
    user = liveUser;
    localStorage.setItem('dc_user', JSON.stringify(user));
  } else if (!user) {
    localStorage.removeItem('dc_token');
    localStorage.removeItem('dc_user');
    window.location.href = 'login.html';
    return;
  }

  const RANK_COLORS = {
    DEADCAT: '#445060', Scholar: '#00d4ff', 'Lead Researcher': '#00d4ff',
    'Founding Circle': '#f0a500',
  };

  async function authFetch(url, opts = {}) {
    let res = await fetch(`${API}${url}`, {
      ...opts,
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
      cache: 'no-store',
    });
    if (res.status === 401) {
      const refreshed = await fetchMeWithRetry();
      if (refreshed) {
        user = refreshed;
        localStorage.setItem('dc_user', JSON.stringify(user));
        res = await fetch(`${API}${url}`, {
          ...opts,
          credentials: 'include',
          headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
          cache: 'no-store',
        });
      }
      if (res.status === 401) {
        localStorage.removeItem('dc_token');
        localStorage.removeItem('dc_user');
        window.location.href = 'login.html';
      }
    }
    return res;
  }

  function timeAgo(dateStr) {
    if (!dateStr) return 'never';
    const diff = (Date.now() - new Date(dateStr)) / 1000;
    if (diff < 60) return 'now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
  }

  function timeUntil(dateStr) {
    if (!dateStr) return '';
    const diff = (new Date(dateStr) - Date.now()) / 1000;
    if (diff <= 0) return 'expired';
    if (diff < 3600)  return `expires in ${Math.floor(diff / 60)}m`;
    if (diff < 86400) return `expires in ${Math.floor(diff / 3600)}h`;
    return `expires in ${Math.floor(diff / 86400)}d`;
  }

  function isOnline(dateStr) {
    if (!dateStr) return 'offline';
    const diff = (Date.now() - new Date(dateStr)) / 1000;
    if (diff < 300) return 'online';
    if (diff < 3600) return 'away';
    return 'offline';
  }

  function populateNav() {
    const ava = document.getElementById('nav-ava');
    const handleEl = document.getElementById('nav-handle');
    const rankEl = document.getElementById('nav-rank');
    const profileLink = document.getElementById('nav-profile-link');
    if (profileLink) {
      const myProfileUrl = `members/profile.html?user=${encodeURIComponent(user.handle)}`;
      profileLink.href = myProfileUrl;
      if (!profileLink.dataset.navBound) {
        profileLink.dataset.navBound = '1';
        profileLink.addEventListener('click', (e) => {
          e.preventDefault();
          window.location.assign(myProfileUrl);
        });
      }
    }
    if (!ava || !handleEl || !rankEl || !profileLink) return;
    ava.textContent = user.emoji || '🐱';
    handleEl.textContent = user.handle;
    rankEl.textContent = String(user.rank || '').toUpperCase();
    rankEl.style.color = RANK_COLORS[user.rank] || '#445060';
    profileLink.href = `members/profile.html?user=${encodeURIComponent(user.handle)}`;
  }

  async function loadMembers() {
    try {
      const res = await authFetch('/api/users/');
      if (!res.ok) return;
      const members = await res.json();
      const list = document.getElementById('members-list');
      if (!list) return;

      const onlineCount = members.filter((m) => isOnline(m.last_seen) === 'online').length;
      const statOnline = document.getElementById('stat-online');
      if (statOnline) statOnline.textContent = String(onlineCount);

      const statMembers = document.getElementById('stat-members');
      if (statMembers) statMembers.textContent = members.length;

      list.innerHTML = members.map((m) => {
        const status = isOnline(m.last_seen);
        const color  = RANK_COLORS[m.rank] || '#445060';
        return `<div class="member-row">
          <div class="m-ava">${esc(m.emoji)}<div class="m-status ${status}"></div></div>
          <div class="m-info">
            <div class="m-handle"><a href="members/profile.html?user=${encodeURIComponent(m.handle)}" style="color:inherit;text-decoration:none;">${esc(m.handle)}</a></div>
            <div class="m-rank" style="color:${esc(color)};">${esc(String(m.rank || '').toUpperCase())}</div>
          </div>
          <span class="m-last">${timeAgo(m.last_seen)}</span>
        </div>`;
      }).join('');

      const sorted   = [...members].sort((a, b) => new Date(b.last_seen || 0) - new Date(a.last_seen || 0));
      const activeEl = document.getElementById('active-members');
      if (activeEl) {
        activeEl.innerHTML = sorted.slice(0, 5).map(m => {
          const color = RANK_COLORS[m.rank] || '#445060';
          return `<div class="member-row">
            <div class="m-ava">${esc(m.emoji)}<div class="m-status ${isOnline(m.last_seen)}"></div></div>
            <div class="m-info">
              <div class="m-handle"><a href="members/profile.html?user=${encodeURIComponent(m.handle)}" style="color:inherit;text-decoration:none;">${esc(m.handle)}</a></div>
              <div class="m-rank" style="color:${esc(color)};">${esc(String(m.rank || '').toUpperCase())}</div>
            </div>
            <span class="m-last">${timeAgo(m.last_seen)}</span>
          </div>`;
        }).join('');
      }
    } catch (e) { console.error('Failed to load members:', e); }
  }

  async function loadStats() {
    try {
      const res  = await authFetch('/api/stats');
      if (!res.ok) return;
      const data = await res.json();
      const notesEl = document.getElementById('stat-notes');
      const iocsEl  = document.getElementById('stat-iocs');
      if (notesEl) notesEl.textContent = data.total_notes ?? '0';
      if (iocsEl)  iocsEl.textContent  = data.total_iocs  ?? '0';
    } catch (e) { console.error('Stats error:', e); }
  }

  async function loadAnnouncements() {
    try {
      const res     = await authFetch('/api/announcements/');
      if (!res.ok) return;
      const all     = await res.json();
      const notices = all.filter(a => a.type === 'notice');
      const creds   = all.filter(a => a.type === 'creds');
      renderAnnouncements('noticeItems', notices, false);
      renderAnnouncements('credsItems',  creds,   true);
    } catch (e) { console.error('Announcements error:', e); }
  }

  function renderAnnouncements(elId, items, isCreds) {
    const el = document.getElementById(elId);
    if (!el) return;
    if (!items.length) {
      el.innerHTML = `<div class="ann-empty">${isCreds ? 'No credentials posted.' : 'No announcements.'}</div>`;
      return;
    }
    el.innerHTML = items.map(a => `
      <div class="ann-item ${isCreds ? 'creds-item' : ''}">
        ${user.is_admin ? `<button class="ann-del-btn" onclick="deleteAnnouncement(${a.id})" style="display:block;">✕</button>` : ''}
        <div class="ann-item-title">${esc(a.title)}</div>
        ${a.content ? `<div class="ann-item-content">${esc(a.content)}</div>` : ''}
        <div class="ann-item-meta">
          <span>${esc(a.author)}</span>
          <span>${timeAgo(a.created_at)}</span>
          <span class="ann-expires">${timeUntil(a.expires_at)}</span>
        </div>
      </div>`).join('');
  }

  async function loadRecentNotes() {
    try {
      const res   = await authFetch('/api/notes/');
      if (!res.ok) return;
      const notes = await res.json();
      const el    = document.getElementById('recent-notes');
      if (!el) return;
      if (!notes.length) {
        el.innerHTML = '<div style="padding:16px 18px;font-family:var(--mono);font-size:10px;color:var(--text-dim);">No notes yet.</div>';
        return;
      }
      el.innerHTML = notes.slice(0, 5).map(n => `
        <div class="note-item" onclick="window.location='library.html'" style="cursor:crosshair;">
          <div class="note-title">${esc(n.title)}</div>
          <div class="note-preview">${esc(n.content || 'No preview')}</div>
          <div class="note-meta">
            <span>${esc(n.author_handle)}</span>
            <span>${timeAgo(n.updated_at || n.created_at)}</span>
            ${(Array.isArray(n.tags) ? n.tags : []).filter(Boolean).map(t => `<span class="note-tag">${esc(String(t).trim())}</span>`).join('')}
          </div>
        </div>`).join('');
    } catch (e) { console.error('Notes error:', e); }
  }

  function logout(e) {
    if (e) e.preventDefault();
    fetch(`${API}/api/auth/logout`, { method: 'POST', credentials: 'include', keepalive: true })
      .finally(() => {
        localStorage.removeItem('dc_token');
        localStorage.removeItem('dc_user');
        window.location.replace('login.html');
      });
  }

  const logoutBtn = document.getElementById('logout-btn');
  if (logoutBtn) logoutBtn.addEventListener('click', logout);

  function updateClock() {
    const now    = new Date();
    const utc    = now.toUTCString().split(' ')[4];
    let nepal = '';
    try {
      nepal = new Intl.DateTimeFormat('en-GB', {
        timeZone: 'Asia/Kathmandu',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      }).format(now);
    } catch (_) {
      // Fallback: Nepal is UTC+05:45
      const np = new Date(now.getTime() + ((5 * 60 + 45) * 60 * 1000));
      nepal = np.toISOString().slice(11, 19);
    }
    const clock  = document.getElementById('clock');
    const dateEl = document.getElementById('dateStr');
    if (clock)  clock.textContent  = `${nepal} NPT · ${utc} UTC`;
    if (dateEl) dateEl.textContent = now.toISOString().split('T')[0];
  }
  updateClock();
  setInterval(updateClock, 1000);

  if (user.is_admin) {
    const noticeBtn = document.getElementById('noticePostBtn');
    const credsBtn  = document.getElementById('credsPostBtn');
    if (noticeBtn) noticeBtn.style.display = 'block';
    if (credsBtn)  credsBtn.style.display  = 'block';
  }

  if (!user.is_admin) {
    setTimeout(() => {
      const label = document.getElementById('admin-sidebar-section');
      const link  = document.getElementById('admin-sidebar-link');
      if (label) label.style.display = 'none';
      if (link)  link.style.display  = 'none';
    }, 500);
  }

  // ── Notifications ──────────────────────────────────────────────
  let _notifAll = [];
  let _notifKnownIds = new Set();
  let _notifSoundArmed = false;
  let _notifAudioCtx = null;

  function armNotificationSound() {
    if (_notifSoundArmed) return;
    _notifSoundArmed = true;
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (Ctx) _notifAudioCtx = new Ctx();
      if (_notifAudioCtx && _notifAudioCtx.state === 'suspended') {
        _notifAudioCtx.resume().catch(() => {});
      }
    } catch (_) {}
  }

  function playNotificationSound() {
    if (!_notifSoundArmed) return;
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return;
      if (!_notifAudioCtx) _notifAudioCtx = new Ctx();
      const ctx = _notifAudioCtx;
      if (ctx.state === 'suspended') {
        ctx.resume().catch(() => {});
      }

      const now = ctx.currentTime;
      const master = ctx.createGain();
      master.gain.setValueAtTime(0.0001, now);
      master.gain.exponentialRampToValueAtTime(0.065, now + 0.01);
      master.gain.exponentialRampToValueAtTime(0.0001, now + 0.28);
      master.connect(ctx.destination);

      const o1 = ctx.createOscillator();
      o1.type = 'triangle';
      o1.frequency.setValueAtTime(880, now);
      o1.frequency.exponentialRampToValueAtTime(1174, now + 0.12);
      o1.connect(master);
      o1.start(now);
      o1.stop(now + 0.14);

      const o2 = ctx.createOscillator();
      o2.type = 'sine';
      o2.frequency.setValueAtTime(1318, now + 0.08);
      o2.connect(master);
      o2.start(now + 0.09);
      o2.stop(now + 0.24);
    } catch (_) {}
  }

  document.addEventListener('pointerdown', armNotificationSound, { once: true, passive: true });
  document.addEventListener('keydown', armNotificationSound, { once: true });

  function renderNotifDot() {
    const seen = JSON.parse(localStorage.getItem('dc_seen_notifs') || '[]');
    const dismissed = JSON.parse(localStorage.getItem('dc_dismissed_notifs') || '[]');
    const dot = document.getElementById('notif-dot');
    const hasUnread = _notifAll.some(a => !seen.includes(a.id) && !dismissed.includes(a.id));
    if (dot) dot.style.display = hasUnread ? 'block' : 'none';
  }

  function renderNotifPanel() {
    const body = document.getElementById('notif-panel-body');
    if (!body) return;
    const seen = JSON.parse(localStorage.getItem('dc_seen_notifs') || '[]');
    const dismissed = JSON.parse(localStorage.getItem('dc_dismissed_notifs') || '[]');
    const visibleNotifs = _notifAll.filter((a) => !dismissed.includes(a.id));
    if (!visibleNotifs.length) {
      body.innerHTML = '<div class="notif-empty">No notifications.</div>';
      return;
    }
    body.innerHTML = visibleNotifs.map(a => {
      const isUnread = !seen.includes(a.id);
      return `<div class="notif-item${isUnread ? ' unread' : ''}">
        <div class="notif-item-top">
          <div class="notif-item-title">${esc(a.title)}</div>
          <button class="notif-close-btn" data-notif-id="${a.id}" title="Dismiss">✕</button>
        </div>
        <div class="notif-item-meta">
          <span class="notif-item-type-${esc(a.type)}">[${esc(a.type)}]</span>
          <span>${esc(a.author)}</span>
          <span>${timeAgo(a.created_at)}</span>
        </div>
      </div>`;
    }).join('');
    body.querySelectorAll('.notif-close-btn').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const id = Number(btn.getAttribute('data-notif-id'));
        if (!Number.isFinite(id)) return;
        const dismissedNow = new Set(JSON.parse(localStorage.getItem('dc_dismissed_notifs') || '[]'));
        dismissedNow.add(id);
        localStorage.setItem('dc_dismissed_notifs', JSON.stringify(Array.from(dismissedNow)));
        renderNotifPanel();
        renderNotifDot();
      });
    });
  }

  async function maybeRequestNotificationPermission() {
    if (!('Notification' in window)) return;
    if (Notification.permission === 'default') {
      try { await Notification.requestPermission(); } catch (_) {}
    }
  }

  function pushDesktopNotification(ann) {
    if (!('Notification' in window)) return;
    if (Notification.permission !== 'granted') return;
    const body = `${ann.type.toUpperCase()} • ${ann.author}`;
    try {
      const n = new Notification(`DEADCATS: ${ann.title}`, { body, tag: `dc-ann-${ann.id}` });
      n.onclick = () => {
        window.focus();
      };
    } catch (_) {}
  }

  // ── CTF reminders (24h / 1h) for "I Will Play" ────────────────
  const CTF_REMINDER_STORE_KEY = 'dc_ctf_reminders_sent_v1';

  function readCtfReminderStore() {
    try {
      const raw = localStorage.getItem(CTF_REMINDER_STORE_KEY);
      const parsed = raw ? JSON.parse(raw) : {};
      return parsed && typeof parsed === 'object' ? parsed : {};
    } catch (_) {
      localStorage.removeItem(CTF_REMINDER_STORE_KEY);
      return {};
    }
  }

  function writeCtfReminderStore(store) {
    try {
      localStorage.setItem(CTF_REMINDER_STORE_KEY, JSON.stringify(store));
    } catch (_) {}
  }

  function cleanupCtfReminderStore(store) {
    const cutoff = Date.now() - (14 * 24 * 60 * 60 * 1000);
    let changed = false;
    Object.keys(store).forEach((k) => {
      const ts = Number(store[k] || 0);
      if (!Number.isFinite(ts) || ts < cutoff) {
        delete store[k];
        changed = true;
      }
    });
    return changed;
  }

  function userWillPlayCtf(ev) {
    const markers = Array.isArray(ev.participation_markers) ? ev.participation_markers : [];
    return markers.some((m) => {
      const handle = String(m.handle || '').toLowerCase();
      return handle === String(user.handle || '').toLowerCase() && m.will_play === true;
    });
  }

  function pushCtfReminderNotification(ev, slotLabel, slotId) {
    if (!('Notification' in window)) return;
    if (Notification.permission !== 'granted') return;
    const start = new Date(ev.start_time);
    const when = Number.isFinite(start.getTime())
      ? start.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
      : 'soon';
    try {
      const n = new Notification(`CTF Reminder: ${ev.title}`, {
        body: `Starts in ~${slotLabel}. You marked "I Will Play". (${when})`,
        tag: `dc-ctf-${ev.id}-${slotId}`,
      });
      n.onclick = () => {
        window.focus();
        window.location.href = 'ctf.html';
      };
    } catch (_) {}
  }

  async function checkCtfReminders() {
    try {
      const res = await authFetch('/api/ctf/events');
      if (!res.ok) return;
      const events = await res.json();
      const now = Date.now();
      const slots = [
        { id: '24h', ms: 24 * 60 * 60 * 1000, label: '24h' },
        { id: '1h',  ms: 1 * 60 * 60 * 1000,  label: '1h'  },
      ];

      const store = readCtfReminderStore();
      let changed = cleanupCtfReminderStore(store);

      (Array.isArray(events) ? events : []).forEach((ev) => {
        if (ev.status !== 'upcoming') return;
        if (!userWillPlayCtf(ev)) return;
        const startMs = new Date(ev.start_time || '').getTime();
        if (!Number.isFinite(startMs) || startMs <= now) return;

        const eventKey = `${ev.id}:${ev.start_time || ''}`;
        slots.forEach((slot) => {
          const key = `${eventKey}:${slot.id}`;
          if (store[key]) return;
          // If user is within the reminder window and has not been notified yet, notify once.
          if (now >= (startMs - slot.ms)) {
            pushCtfReminderNotification(ev, slot.label, slot.id);
            store[key] = Date.now();
            changed = true;
          }
        });
      });

      if (changed) writeCtfReminderStore(store);
    } catch (e) {
      console.error('CTF reminder check failed:', e);
    }
  }

  async function loadNotifications() {
    try {
      const res = await authFetch('/api/announcements/');
      if (!res.ok) return;
      _notifAll = await res.json();
      const dismissed = new Set(JSON.parse(localStorage.getItem('dc_dismissed_notifs') || '[]'));
      const visible = _notifAll.filter((a) => !dismissed.has(a.id));
      let hasNewNotification = false;
      if (_notifKnownIds.size === 0) {
        visible.forEach((a) => _notifKnownIds.add(a.id));
      } else {
        visible.forEach((a) => {
          if (!_notifKnownIds.has(a.id)) {
            hasNewNotification = true;
            pushDesktopNotification(a);
            _notifKnownIds.add(a.id);
          }
        });
      }
      if (hasNewNotification) playNotificationSound();
      renderNotifPanel();
      renderNotifDot();
    } catch (e) { console.error('Notifications error:', e); }
  }

  const notifBtn   = document.getElementById('notif-btn');
  const notifPanel = document.getElementById('notif-panel');

  if (notifBtn && notifPanel) {
    notifBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      const isHidden = notifPanel.classList.contains('hidden');
      if (isHidden) {
        renderNotifPanel();
        notifPanel.classList.remove('hidden');
        const dismissed = new Set(JSON.parse(localStorage.getItem('dc_dismissed_notifs') || '[]'));
        const ids = _notifAll.filter((a) => !dismissed.has(a.id)).map(a => a.id);
        localStorage.setItem('dc_seen_notifs', JSON.stringify(ids));
        renderNotifDot();
      } else {
        notifPanel.classList.add('hidden');
      }
    });

    document.addEventListener('click', () => {
      notifPanel.classList.add('hidden');
    });
  }

  populateNav();
  loadMembers();
  loadStats();
  loadAnnouncements();
  loadRecentNotes();
  loadNotifications();
  checkCtfReminders();
  maybeRequestNotificationPermission();
  setInterval(loadNotifications, 30000);
  setInterval(checkCtfReminders, 60000);
}

// ── Global modal functions ────────────────────────────────────────
let _postType = 'notice';

function openPostModal(type) {
  _postType = type;
  document.getElementById('modalTitle').textContent     = type === 'creds' ? 'Drop CTF Credentials' : 'Post Announcement';
  document.getElementById('contentLabel').textContent   = type === 'creds' ? 'Credentials (user / pass / URL)' : 'Content';
  document.getElementById('postContent').placeholder    = type === 'creds' ? 'user: admin\npass: hunter2\nurl: https://ctf.example.com' : 'Details...';
  document.getElementById('postConfirmBtn').textContent = type === 'creds' ? 'Drop Creds' : 'Post';
  document.getElementById('postTitle').value   = '';
  document.getElementById('postContent').value = '';
  document.getElementById('postModal').classList.remove('hidden');
  document.getElementById('postTitle').focus();
}

function closePostModal() {
  document.getElementById('postModal').classList.add('hidden');
}

async function submitPost() {
  const title      = document.getElementById('postTitle').value.trim();
  const content    = document.getElementById('postContent').value.trim();
  const expires_in = parseInt(document.getElementById('postExpires').value);
  if (!title) { alert('Title required.'); return; }
  const res = await fetch(`${API}/api/announcements/`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, content, type: _postType, expires_in }),
  });
  if (res.ok) { closePostModal(); location.reload(); }
  else { const err = await res.json(); alert(err.detail || 'Failed to post.'); }
}

async function deleteAnnouncement(id) {
  if (!confirm('Delete this?')) return;
  await fetch(`${API}/api/announcements/${id}`, {
    method: 'DELETE',
    credentials: 'include',
  });
  location.reload();
}

// ── Boot ──────────────────────────────────────────────────────────
let _dashboardInitialized = false;
function tryInit() {
  if (_dashboardInitialized) return;
  if (document.getElementById('members-list') && document.getElementById('notif-btn')) {
    _dashboardInitialized = true;
    initDashboard();
  } else {
    setTimeout(tryInit, 50);
  }
}
window.addEventListener('partials:loaded', tryInit, { once: true });
setTimeout(tryInit, 300);
