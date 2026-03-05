(function initLofiPlayer(){
  if (window.__dcLofiV2Loaded) return;
  window.__dcLofiV2Loaded = true;

  var SRC = '/music/music.mp3';
  var DEFAULT_VOLUME = 0.1;
  var KEY_ENABLED = 'dc_lofi_enabled';
  var KEY_TIME = 'dc_lofi_time';

  function injectStyle(){
    if (document.getElementById('dc-lofi-v2-style')) return;
    var s = document.createElement('style');
    s.id = 'dc-lofi-v2-style';
    s.textContent = [
      '.dc-lofi{position:fixed;right:12px;bottom:12px;z-index:1300;}',
      '.dc-lofi-btn{display:inline-flex;align-items:center;gap:8px;font:600 11px/1 var(--mono,monospace);letter-spacing:.12em;text-transform:uppercase;color:#d8ecff;background:rgba(8,12,20,.9);border:1px solid rgba(0,212,255,.35);padding:7px 10px;cursor:crosshair;backdrop-filter:blur(4px);transition:border-color .2s ease,color .2s ease,box-shadow .2s ease,transform .16s ease}',
      '.dc-lofi-btn:hover{transform:translateY(-1px);border-color:rgba(0,212,255,.55);box-shadow:0 6px 16px rgba(0,0,0,.28)}',
      '.dc-lofi-btn:active{transform:translateY(0) scale(.99)}',
      '.dc-lofi-btn[data-state="on"]{border-color:rgba(0,255,136,.5);color:#d9fff0}',
      '.dc-lofi-bars{display:inline-flex;gap:2px;align-items:flex-end;height:10px}',
      '.dc-lofi-bars i{display:block;width:2px;height:4px;background:currentColor;opacity:.7}',
      '.dc-lofi-btn[data-state="on"] .dc-lofi-bars i{animation:dcLofiBars .9s ease-in-out infinite}',
      '.dc-lofi-btn[data-state="on"] .dc-lofi-bars i:nth-child(2){animation-delay:.12s}',
      '.dc-lofi-btn[data-state="on"] .dc-lofi-bars i:nth-child(3){animation-delay:.24s}',
      '@keyframes dcLofiBars{0%,100%{height:3px;opacity:.55}50%{height:10px;opacity:1}}',
      '@media (max-width:640px){.dc-lofi{right:8px;bottom:8px}.dc-lofi-btn{padding:6px 8px;font-size:10px;letter-spacing:.1em}}'
    ].join('');
    document.head.appendChild(s);
  }

  function mount(){
    if (!document.body || document.querySelector('.dc-lofi')) return;

    var wrap = document.createElement('div');
    wrap.className = 'dc-lofi';

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'dc-lofi-btn';
    btn.setAttribute('data-state', 'off');
    btn.innerHTML = '<span class="dc-lofi-txt">Lofi Off</span><span class="dc-lofi-bars" aria-hidden="true"><i></i><i></i><i></i></span>';

    var audio = document.createElement('audio');
    audio.src = SRC;
    audio.loop = true;
    audio.preload = 'none';
    audio.volume = DEFAULT_VOLUME;
    audio.muted = false;

    function setState(mode){
      btn.setAttribute('data-state', mode === 'on' ? 'on' : 'off');
      var txt = btn.querySelector('.dc-lofi-txt');
      if (!txt) return;
      if (mode === 'on') txt.textContent = 'Lofi On';
      else if (mode === 'tap') txt.textContent = 'Lofi Tap';
      else txt.textContent = 'Lofi Off';
    }

    function saveTime() {
      try {
        if (Number.isFinite(audio.currentTime) && audio.currentTime > 0) {
          localStorage.setItem(KEY_TIME, String(audio.currentTime));
        }
      } catch (_) {}
    }

    async function playWithResume() {
      var t = Number(localStorage.getItem(KEY_TIME));
      if (Number.isFinite(t) && t > 0) {
        var apply = function() {
          try {
            if (t < (audio.duration || Number.MAX_SAFE_INTEGER)) audio.currentTime = t;
          } catch (_) {}
        };
        if (audio.readyState >= 1) apply();
        else audio.addEventListener('loadedmetadata', apply, { once: true });
      }
      await audio.play();
      setState('on');
    }

    btn.addEventListener('click', async function(){
      if (audio.paused) {
        try {
          localStorage.setItem(KEY_ENABLED, '1');
          await playWithResume();
        } catch (_) {
          setState('tap');
        }
      } else {
        audio.pause();
        saveTime();
        localStorage.setItem(KEY_ENABLED, '0');
        setState('off');
      }
    });

    audio.addEventListener('pause', function(){ setState('off'); saveTime(); });
    audio.addEventListener('play', function(){ setState('on'); localStorage.setItem(KEY_ENABLED, '1'); });
    audio.addEventListener('timeupdate', saveTime);
    window.addEventListener('pagehide', saveTime);
    window.addEventListener('beforeunload', saveTime);
    audio.addEventListener('error', function(){
      btn.disabled = true;
      var txt = btn.querySelector('.dc-lofi-txt');
      if (txt) txt.textContent = 'Lofi N/A';
      btn.style.opacity = '0.65';
    });

    var shouldPlay = localStorage.getItem(KEY_ENABLED) === '1';
    if (shouldPlay) {
      playWithResume().catch(function(){
        setState('tap');
        var retry = function(ev) {
          var target = ev && ev.target;
          if (target && btn.contains(target)) return;
          playWithResume().then(function(){
            document.removeEventListener('pointerdown', retry);
            document.removeEventListener('keydown', retry);
          }).catch(function(){});
        };
        document.addEventListener('pointerdown', retry, { passive: true });
        document.addEventListener('keydown', retry);
      });
    } else {
      setState('off');
    }
    wrap.appendChild(btn);
    wrap.appendChild(audio);
    document.body.appendChild(wrap);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function(){ injectStyle(); mount(); }, { once: true });
  } else {
    injectStyle();
    mount();
  }
})();
