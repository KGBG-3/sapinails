/* sapinails.il · shared by every public page.
   1. The accessibility menu: text size, high contrast, link highlight, plain font, no motion.
   2. The first-visit note about cookies and privacy.
   Everything is kept in this browser only (localStorage); nothing is sent anywhere.
   Loaded in <head>, so saved choices apply before the page is drawn. The looks are in site.css. */
(function () {
  'use strict';
  var root = document.documentElement;
  var KEY = 'sapinails.ax', NOTE_KEY = 'sapinails.notice';
  var src = (document.currentScript && document.currentScript.src) || '';
  var BASE = src.replace(/assets\/site\.js.*$/, '');   // the site's root, from any page depth
  var SIZES = ['100%', '115%', '130%'];
  var FLAGS = ['contrast', 'links', 'font', 'still'];

  function load() {
    var s = { size: 0, contrast: false, links: false, font: false, still: false };
    try {
      var v = JSON.parse(localStorage.getItem(KEY) || 'null');
      if (v && typeof v === 'object') {
        if (v.size === 1 || v.size === 2) s.size = v.size;
        FLAGS.forEach(function (f) { s[f] = v[f] === true; });
      }
    } catch (_) {}
    return s;
  }
  function isDefault() { return !S.size && !FLAGS.some(function (f) { return S[f]; }); }
  function save() {
    try { if (isDefault()) localStorage.removeItem(KEY); else localStorage.setItem(KEY, JSON.stringify(S)); } catch (_) {}
  }
  function apply() {
    if (S.size) root.setAttribute('data-ax-size', String(S.size)); else root.removeAttribute('data-ax-size');
    FLAGS.forEach(function (f) { root.classList.toggle('ax-' + f, S[f]); });
  }
  var S = load();
  apply();

  var SVG = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">';
  var ICON = SVG + '<circle cx="12" cy="4.6" r="2" fill="currentColor"/><path d="M5 8.4c2.3.8 4.6 1.1 7 1.1s4.7-.3 7-1.1M12 9.5v5M12 14.5l-3.2 6M12 14.5l3.2 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  var X = SVG + '<path d="M6 6l12 12M18 6 6 18"/></svg>';
  var TICK = SVG + '<path d="m5 12.5 4.5 4.5L19 7"/></svg>';
  function opt(id, label) {
    return '<button type="button" class="ax-opt" data-ax="' + id + '" aria-pressed="false"><span class="ax-box">' + TICK + '</span><span>' + label + '</span></button>';
  }

  function build() {
    if (document.querySelector('.ax-root')) return;
    var box = document.createElement('div');
    box.className = 'ax-root';
    box.setAttribute('dir', 'rtl');
    box.setAttribute('lang', 'he');
    box.innerHTML =
      '<button type="button" class="ax-btn" aria-expanded="false" aria-controls="axPanel" aria-label="תפריט נגישות">' + ICON + '</button>' +
      '<div class="ax-panel" id="axPanel" role="dialog" aria-labelledby="axTitle" tabindex="-1" hidden>' +
        '<div class="ax-head"><h2 id="axTitle">נגישות</h2><button type="button" class="ax-x" data-ax="close" aria-label="סגירת תפריט הנגישות">' + X + '</button></div>' +
        '<div class="ax-size" role="group" aria-label="גודל הטקסט"><span class="ax-lbl">גודל הטקסט</span><span class="ax-ctl">' +
          '<button type="button" data-ax="smaller"><span aria-hidden="true">א−</span><span class="ax-sr">הקטנת הטקסט</span></button><output></output>' +
          '<button type="button" data-ax="bigger"><span aria-hidden="true">א+</span><span class="ax-sr">הגדלת הטקסט</span></button></span></div>' +
        opt('contrast', 'ניגודיות גבוהה') + opt('links', 'הדגשת קישורים') + opt('font', 'גופן קריא') + opt('still', 'עצירת אנימציות') +
        '<div class="ax-foot"><button type="button" class="ax-reset" data-ax="reset">איפוס</button><a href="' + BASE + 'accessibility/">הצהרת נגישות</a></div>' +
      '</div>';
    var skip = document.querySelector('a.skip');
    if (skip && skip.parentNode === document.body) skip.after(box); else document.body.prepend(box);

    var btn = box.querySelector('.ax-btn'), panel = box.querySelector('.ax-panel'), out = box.querySelector('output');
    function paint() {
      out.textContent = SIZES[S.size];
      box.querySelector('[data-ax="smaller"]').disabled = S.size === 0;
      box.querySelector('[data-ax="bigger"]').disabled = S.size === SIZES.length - 1;
      FLAGS.forEach(function (f) { box.querySelector('[data-ax="' + f + '"]').setAttribute('aria-pressed', String(S[f])); });
    }
    function setOpen(open, refocus) {
      panel.hidden = !open;
      btn.setAttribute('aria-expanded', String(open));
      if (open) panel.focus(); else if (refocus) btn.focus();
    }
    function change(fn) { fn(); apply(); save(); paint(); }
    paint();

    btn.addEventListener('click', function () { setOpen(panel.hidden); });
    panel.addEventListener('click', function (e) {
      var el = e.target.closest('[data-ax]');
      if (!el || el.disabled) return;
      var a = el.getAttribute('data-ax');
      if (a === 'close') setOpen(false, true);
      else if (a === 'smaller') change(function () { S.size = Math.max(0, S.size - 1); });
      else if (a === 'bigger') change(function () { S.size = Math.min(SIZES.length - 1, S.size + 1); });
      else if (a === 'reset') change(function () { S.size = 0; FLAGS.forEach(function (f) { S[f] = false; }); });
      else if (FLAGS.indexOf(a) >= 0) change(function () { S[a] = !S[a]; });
      // a size button that just became disabled loses the focus; keep it in the menu
      if (el.disabled) box.querySelector(a === 'smaller' ? '[data-ax="bigger"]' : '[data-ax="smaller"]').focus();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !panel.hidden) { e.stopPropagation(); setOpen(false, box.contains(document.activeElement)); }
    }, true);
    document.addEventListener('click', function (e) { if (!panel.hidden && !box.contains(e.target)) setOpen(false); });
    box.addEventListener('focusout', function (e) {
      if (!panel.hidden && e.relatedTarget && !box.contains(e.relatedTarget)) setOpen(false);
    });
    // another tab changed the choices, or this page came back from the browser's back button
    function refresh() {
      S = load(); apply(); paint();
      var n = document.querySelector('.ax-notice'), seen = false;
      try { seen = !!localStorage.getItem(NOTE_KEY); } catch (_) {}
      if (n && seen) { n.remove(); root.style.removeProperty('--ax-lift'); }
    }
    addEventListener('storage', function (e) { if (e.key === KEY || e.key === NOTE_KEY) refresh(); });
    addEventListener('pageshow', function (e) { if (e.persisted) refresh(); });

    note(box);
  }

  /* first visit: a short, true note. The site sets no cookies; the only things kept in the browser are listed in the privacy policy. */
  function note(after) {
    try { if (localStorage.getItem(NOTE_KEY)) return; } catch (_) {}
    var n = document.createElement('div');
    n.className = 'ax-root ax-notice';
    n.setAttribute('dir', 'rtl');
    n.setAttribute('lang', 'he');
    n.setAttribute('role', 'region');
    n.setAttribute('aria-label', 'עוגיות ופרטיות');
    n.innerHTML = '<p>האתר לא שומר עוגיות (cookies) ולא עוקב אחרי הגלישה. בדפדפן נשמר רק מה שנחוץ לשימוש באתר. <a href="' + BASE + 'privacy/">מדיניות הפרטיות</a></p><button type="button">הבנתי</button>';
    after.after(n);
    // on a narrow screen the note reaches the corner where the menu button sits, so the button moves above it
    var lift = function () {
      if (n.isConnected) root.style.setProperty('--ax-lift', n.getBoundingClientRect().left < 76 ? Math.ceil(n.getBoundingClientRect().height + 10) + 'px' : '0px');
    };
    lift();
    addEventListener('resize', lift);
    if (window.ResizeObserver) new ResizeObserver(lift).observe(n);
    n.querySelector('button').addEventListener('click', function () {
      try { localStorage.setItem(NOTE_KEY, '1'); } catch (_) {}
      var back = n.contains(document.activeElement);
      n.remove();
      root.style.removeProperty('--ax-lift');
      if (back) after.querySelector('.ax-btn').focus();
    });
  }

  if (document.body) build(); else document.addEventListener('DOMContentLoaded', build);
})();
