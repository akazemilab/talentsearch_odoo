/** @odoo-module ignore **/
// Talent Search site behaviour (website 4 only, ts_website.assets_ts_js):
// - mobile menu: a disclosure button (aria-expanded) controlling #ts-mnav
// - theme toggle: light / dark, stored in localStorage['ts-site-theme'] (the head script applies it before paint)
// - FAQ accordion: .ts-faq__q buttons with aria-expanded controlling the answer (never <details>)
(function () {
    'use strict';
    var KEY = 'ts-site-theme';
    function setOpen(btn, open) {
        var panel = document.getElementById(btn.getAttribute('aria-controls'));
        if (!panel) { return; }
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
        panel.hidden = !open;
    }
    function currentTheme() {
        return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
    }
    function setTheme(t) {
        document.documentElement.setAttribute('data-theme', t);
        try { localStorage.setItem(KEY, t); } catch (e) { /* private mode: the choice lasts for this page only */ }
        document.querySelectorAll('.ts-theme').forEach(function (b) {
            b.setAttribute('aria-pressed', t === 'dark' ? 'true' : 'false');
        });
    }
    document.addEventListener('click', function (ev) {
        var t = ev.target;
        if (!t || !t.closest) { return; }
        var theme = t.closest('.ts-theme');
        if (theme) { setTheme(currentTheme() === 'dark' ? 'light' : 'dark'); return; }
        var q = t.closest('.ts-faq__q');
        if (q) {
            var a = document.getElementById(q.getAttribute('aria-controls'));
            var open = q.getAttribute('aria-expanded') !== 'true';
            q.setAttribute('aria-expanded', open ? 'true' : 'false');
            if (a) { a.hidden = !open; }
            return;
        }
        var btn = t.closest('.ts-nav__toggle');
        if (btn) {
            setOpen(btn, btn.getAttribute('aria-expanded') !== 'true');
            return;
        }
        document.querySelectorAll('.ts-nav__toggle[aria-expanded="true"]').forEach(function (b) {
            var panel = document.getElementById(b.getAttribute('aria-controls'));
            if (panel && !panel.contains(t)) { setOpen(b, false); }
        });
    });
    document.addEventListener('keydown', function (ev) {
        if (ev.key !== 'Escape') { return; }
        document.querySelectorAll('.ts-nav__toggle[aria-expanded="true"]').forEach(function (b) {
            setOpen(b, false);
            b.focus();
        });
    });
    // An answer linked from elsewhere (/pricing#faq-f2) opens on arrival.
    function openFromHash() {
        var id = (location.hash || '').slice(1);
        if (!id) { return; }
        var q = document.querySelector('.ts-faq__q[aria-controls="' + id.replace(/"/g, '') + '-a"]');
        if (q && q.getAttribute('aria-expanded') !== 'true') { q.click(); }
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', openFromHash);
    } else {
        openFromHash();
    }
})();
