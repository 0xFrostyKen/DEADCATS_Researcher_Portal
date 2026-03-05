// ── CONFIG: change this to your laptop's Tailscale IP ──────────
const API = '';
// ────────────────────────────────────────────────────────────────

// If already logged in, skip login page
(function checkSession() {
  fetch(`${API}/api/auth/me`, { credentials: 'include' })
    .then((res) => { if (res.ok) window.location.replace('dashboard.html'); })
    .catch(() => {});
})();

async function handleLogin() {
  const handle = document.getElementById('handle').value.trim();
  const pass = document.getElementById('pass').value;
  const err = document.getElementById('errMsg');
  const btn = document.getElementById('submitBtn');

  if (!handle || !pass) {
    err.textContent = '⚠ Handle and passphrase are required.';
    err.classList.add('show');
    return;
  }

  err.classList.remove('show');
  btn.textContent = 'Authenticating...';
  btn.disabled = true;

  try {
    const res = await fetch(`${API}/api/auth/login`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ handle, password: pass }),
    });

    const data = await res.json();

    if (!res.ok) {
      err.textContent = `⚠ ${data.detail || 'Authentication failed.'}`;
      err.classList.add('show');
      btn.textContent = 'Authenticate →';
      btn.disabled = false;
      return;
    }

    localStorage.removeItem('dc_token');
    // Keep user profile for UI convenience; auth is cookie-based.
    localStorage.removeItem('dc_token');
    localStorage.setItem('dc_user', JSON.stringify(data.user));

    // Redirect to dashboard
    window.location.href = 'dashboard.html';
  } catch (e) {
    err.textContent = '⚠ Cannot reach server. Check your Tailscale connection.';
    err.classList.add('show');
    btn.textContent = 'Authenticate →';
    btn.disabled = false;
  }
}

async function handleRegister() {
  const handle = document.getElementById('reg-handle').value.trim();
  const pass   = document.getElementById('reg-pass').value;
  const pass2  = document.getElementById('reg-pass2').value;
  const token  = document.getElementById('reg-token').value.trim();
  const err    = document.getElementById('regErrMsg');
  const btn    = document.getElementById('regBtn');

  err.classList.remove('show');

  if (!handle || !pass || !pass2 || !token) {
    err.textContent = '⚠ All fields are required.';
    err.classList.add('show'); return;
  }
  if (pass !== pass2) {
    err.textContent = '⚠ Passwords do not match.';
    err.classList.add('show'); return;
  }
  if (pass.length < 8) {
    err.textContent = '⚠ Password must be at least 8 characters.';
    err.classList.add('show'); return;
  }

  btn.textContent = 'Registering...';
  btn.disabled = true;

  try {
    const res = await fetch(`${API}/api/auth/register`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ handle, password: pass, access_token: token }),
    });
    const data = await res.json();
    if (!res.ok) {
      err.textContent = `⚠ ${data.detail || 'Registration failed.'}`;
      err.classList.add('show');
      btn.textContent = 'Request Access →';
      btn.disabled = false;
      return;
    }
    localStorage.setItem('dc_user', JSON.stringify(data.user));
    window.location.href = 'dashboard.html';
  } catch (e) {
    err.textContent = '⚠ Cannot reach server.';
    err.classList.add('show');
    btn.textContent = 'Request Access →';
    btn.disabled = false;
  }
}

function switchTab(tab) {
  const isLogin = tab === 'login';
  document.getElementById('form-login').classList.toggle('hidden', !isLogin);
  document.getElementById('form-register').classList.toggle('hidden', isLogin);
  document.getElementById('tab-login').classList.toggle('active', isLogin);
  document.getElementById('tab-register').classList.toggle('active', !isLogin);
  document.getElementById('errMsg').classList.remove('show');
  document.getElementById('regErrMsg').classList.remove('show');
}

window.handleLogin    = handleLogin;
window.handleRegister = handleRegister;
window.switchTab      = switchTab;

document.addEventListener('keydown', (e) => {
  if (e.key !== 'Enter') return;
  const regHidden = document.getElementById('form-register').classList.contains('hidden');
  if (regHidden) handleLogin(); else handleRegister();
});
