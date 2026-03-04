/**
 * Minimal HTML partial include helper.
 *
 * Usage:
 *   <div data-include="partials/header.html"></div>
 *   <script src="assets/js/include.js" defer></script>
 *
 * Note: requires serving over http(s). `file://` fetch is blocked in most browsers.
 */
(async function includePartials() {
  const nodes = Array.from(document.querySelectorAll('[data-include]'));
  if (!nodes.length) {
    // Always emit so pages can reliably initialize off this event.
    window.dispatchEvent(new Event('partials:loaded'));
    return;
  }

  await Promise.all(nodes.map(async (el) => {
    const url = el.getAttribute('data-include');
    if (!url) return;
    try {
      const res = await fetch(url, { cache: 'no-cache' });
      if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
      const html = await res.text();
      el.outerHTML = html;
    } catch (err) {
      console.error('[include] failed:', url, err);
    }
  }));

  window.dispatchEvent(new Event('partials:loaded'));
})();

