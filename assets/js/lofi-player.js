(function initLofiPlayer(){
  if (window.__dcLofiInit) return;
  window.__dcLofiInit = true;

  var AUDIO_SRC = '/music/music.mp3';
  var DEFAULT_VOLUME = 0.30;
  var KEY_ENABLED = 'dc_lofi_enabled';
  var KEY_TIME = 'dc_lofi_time';
  var KEY_VOL = 'dc_lofi_volume';

  function addStyles(){
    if (document.getElementById('dc-lofi-style')) return;
    var style = document.createElement('style');
    style.id = 'dc-lofi-style';
    style.textContent = [
      '.dc-lofi{position:fixed;right:14px;bottom:14px;z-index:1200;}',
      '.dc-lofi-btn{display:inline-flex;align-items:center;gap:8px;padding:7px 10px;border:1px solid rgba(0,212,255,0.25);background:rgba(8,12,20,0.9);color:#9fb7d6;font:600 11px/1.1 var(--mono,monospace);letter-spacing:0.12em;text-transform:uppercase;cursor:crosshair;backdrop-filter:blur(4px);transition:transform .16s ease,border-color .2s ease,color .2s ease,box-shadow .2s ease;}',
      '.dc-lofi-btn:hover{transform:translateY(-1px);border-color:rgba(0,212,255,0.55);color:#d8ecff;box-shadow:0 6px 16px rgba(0,0,0,.28);}',
      '.dc-lofi-btn:active{transform:translateY(0) scale(.99);}',
      '.dc-lofi-btn:focus-visible{outline:1px solid rgba(0,212,255,.72);outline-offset:2px;}',
      '.dc-lofi-btn[data-state="on"]{border-color:rgba(0,255,136,.45);color:#d9fff0;}',
      '.dc-lofi-bars{display:inline-flex;gap:2px;align-items:flex-end;height:10px;}',
      '.dc-lofi-bars i{display:block;width:2px;height:4px;background:currentColor;opacity:.7;}',
      '.dc-lofi-btn[data-state="on"] .dc-lofi-bars i{animation:dcLofiBars .9s ease-in-out infinite;}',
      '.dc-lofi-btn[data-state="on"] .dc-lofi-bars i:nth-child(2){animation-delay:.12s;}',
      '.dc-lofi-btn[data-state="on"] .dc-lofi-bars i:nth-child(3){animation-delay:.24s;}',
      '@keyframes dcLofiBars{0%,100%{height:3px;opacity:.55}50%{height:10px;opacity:1}}',
      '@media (max-width:640px){.dc-lofi{right:10px;bottom:10px}.dc-lofi-btn{padding:6px 8px;font-size:10px;letter-spacing:.1em}}',
      '@media (prefers-reduced-motion:reduce){.dc-lofi-btn,.dc-lofi-btn:hover,.dc-lofi-btn:active{transition:none;transform:none}.dc-lofi-btn[data-state="on"] .dc-lofi-bars i{animation:none;height:6px;opacity:.85}}'
    ].join('');
    document.head.appendChild(style);
  }

  function buildUI(){
    if (!document.body || document.querySelector('.dc-lofi')) return null;

    var wrap = document.createElement('div');
    wrap.className = 'dc-lofi';

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'dc-lofi-btn';
    btn.setAttribute('data-state', 'off');
    btn.setAttribute('aria-label', 'Toggle background lofi music');
    btn.innerHTML = '<span class="dc-lofi-label">Lofi Off</span><span class="dc-lofi-bars" aria-hidden="true"><i></i><i></i><i></i></span>';

    var audio = document.createElement('audio');
    audio.preload = 'none';
    audio.loop = true;
    audio.src = AUDIO_SRC;
    audio.muted = false;
    var savedVol = Number(localStorage.getItem(KEY_VOL));
    audio.volume = Number.isFinite(savedVol) && savedVol >= 0 && savedVol <= 1 ? savedVol : DEFAULT_VOLUME;

    var label = btn.querySelector('.dc-lofi-label');

    function setState(on, pendingTap){
      btn.setAttribute('data-state', on ? 'on' : 'off');
      if (label) {
        if (on) label.textContent = 'Lofi On';
        else label.textContent = pendingTap ? 'Lofi Tap' : 'Lofi Off';
      }
      btn.title = on ? 'Pause background music' : 'Play background music';
    }

    function saveProgress() {
      try {
        if (Number.isFinite(audio.currentTime) && audio.currentTime > 0) {
          localStorage.setItem(KEY_TIME, String(audio.currentTime));
        }
        localStorage.setItem(KEY_VOL, String(audio.volume));
      } catch (_) {}
    }

    async function playWithResume() {
      var savedTime = Number(localStorage.getItem(KEY_TIME));
      if (Number.isFinite(savedTime) && savedTime > 0) {
        var applyTime = function() {
          try {
            if (savedTime < (audio.duration || Number.MAX_SAFE_INTEGER)) {
              audio.currentTime = savedTime;
            }
          } catch (_) {}
        };
        if (audio.readyState >= 1) applyTime();
        else audio.addEventListener('loadedmetadata', applyTime, { once: true });
      }
      await audio.play();
      setState(true, false);
    }

    audio.addEventListener('error', function(){
      setState(false);
      if (label) label.textContent = 'Lofi N/A';
      btn.disabled = true;
      btn.style.opacity = '0.6';
      btn.style.cursor = 'not-allowed';
      btn.title = 'music/music.mp3 not found';
    });

    btn.addEventListener('click', async function(){
      if (audio.paused) {
        try {
          localStorage.setItem(KEY_ENABLED, '1');
          await playWithResume();
        } catch (_) {
          setState(false, true);
        }
      } else {
        audio.pause();
        saveProgress();
        localStorage.setItem(KEY_ENABLED, '0');
        setState(false, false);
      }
    });

    audio.addEventListener('pause', function(){ setState(false, false); saveProgress(); });
    audio.addEventListener('play', function(){ setState(true, false); localStorage.setItem(KEY_ENABLED, '1'); });
    audio.addEventListener('timeupdate', saveProgress);
    window.addEventListener('pagehide', saveProgress);
    window.addEventListener('beforeunload', saveProgress);

    // Restore ON/OFF across pages.
    var shouldPlay = localStorage.getItem(KEY_ENABLED) === '1';
    if (shouldPlay) {
      playWithResume().catch(function(){
        // If autoplay is blocked on new page, prompt tap and retry once.
        setState(false, true);
        var retry = function(){
          playWithResume().catch(function(){}).finally(function(){
            document.removeEventListener('pointerdown', retry);
            document.removeEventListener('keydown', retry);
          });
        };
        document.addEventListener('pointerdown', retry, { once: true, passive: true });
        document.addEventListener('keydown', retry, { once: true });
      });
    } else {
      setState(false, false);
    }
    wrap.appendChild(btn);
    wrap.appendChild(audio);
    document.body.appendChild(wrap);
    return wrap;
  }

  function mount(){
    addStyles();
    buildUI();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount, { once: true });
  } else {
    mount();
  }
})();
