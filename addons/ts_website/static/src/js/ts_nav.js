/** @odoo-module ignore **/
// Talent Search site behaviour (website 4 only, ts_website.assets_ts_js):
// - mobile menu: a disclosure button (aria-expanded) controlling #ts-mnav
// - theme toggle: light / dark, stored in localStorage['ts-site-theme'] (the head script applies it before paint)
// - FAQ accordion: .ts-faq__q buttons with aria-expanded controlling the answer (never <details>)
// - horizontal scrollers (.ts-scroller, .tsp-subnav, .tsp-chips, .tsp-steps): data-ts-fade="l|r|lr" on the side that
//   hides more items; the active item (.is-on / aria-current) is scrolled into view
// - file pickers (ts_website.filefield and every bare <input type=file>): Persian button «انتخاب فایل» + live file name
// - Solar Hijri date fields (ts_website.jdate): Jalali <-> Gregorian conversion (below, no library), fills the hidden
//   ISO field, confirms the date in words («۲۰ مهر ۱۴۰۵») or says what is wrong
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

    // ---------- horizontal scrollers ----------
    var SCROLLERS = '.ts-scroller, .tsp-subnav, .tsp-chips, .tsp-steps';
    function fadeOf(el) {
        if (el.scrollWidth <= el.clientWidth + 1) { el.removeAttribute('data-ts-fade'); return; }
        var box = el.getBoundingClientRect(), left = false, right = false;
        Array.prototype.forEach.call(el.children, function (c) {
            var r = c.getBoundingClientRect();
            if (!r.width) { return; }
            if (r.left < box.left - 1) { left = true; }
            if (r.right > box.right + 1) { right = true; }
        });
        var v = (left ? 'l' : '') + (right ? 'r' : '');
        if (v) { el.setAttribute('data-ts-fade', v); } else { el.removeAttribute('data-ts-fade'); }
    }
    function initScrollers() {
        document.querySelectorAll(SCROLLERS).forEach(function (el) {
            var on = el.querySelector('.is-on, [aria-current="page"], [aria-current="step"], [aria-current="true"]');
            if (on && el.scrollWidth > el.clientWidth + 1) {
                var b = el.getBoundingClientRect(), r = on.getBoundingClientRect();
                el.scrollLeft += (r.left + r.width / 2) - (b.left + b.width / 2);
            }
            fadeOf(el);
            el.addEventListener('scroll', function () { fadeOf(el); }, {passive: true});
        });
        var t = null;
        window.addEventListener('resize', function () {
            clearTimeout(t);
            t = setTimeout(function () { document.querySelectorAll(SCROLLERS).forEach(fadeOf); }, 120);
        });
    }

    // ---------- file pickers ----------
    var NO_FILE = 'فایلی انتخاب نشده';
    function fileName(input) {
        var f = input.files;
        if (!f || !f.length) { return NO_FILE; }
        if (f.length > 1) { return f.length.toLocaleString('fa-IR') + ' فایل انتخاب شد'; }
        return f[0].name;
    }
    function initFiles() {
        document.querySelectorAll('#wrapwrap input[type=file]').forEach(function (input) {
            if (input.getAttribute('data-ts-file-done')) { return; }
            input.setAttribute('data-ts-file-done', '1');
            var box = input.closest('.ts-file');
            var btn, out;
            if (box) {
                btn = box.querySelector('.ts-file__btn');
                out = box.querySelector('.ts-file__name');
            }
            if (!box || !btn || !out) {                      // a bare input from another template: build the same parts
                box = document.createElement('span');
                box.className = 'ts-file ts-file--inline';
                input.parentNode.insertBefore(box, input);
                box.appendChild(input);
                input.classList.add('ts-file__input');
                btn = document.createElement('span');
                btn.className = 'ts-btn ts-btn--outline ts-file__btn';
                btn.setAttribute('aria-hidden', 'true');
                btn.textContent = 'انتخاب فایل';
                out = document.createElement('span');
                out.className = 'ts-file__name';
                out.setAttribute('aria-live', 'polite');
                out.id = (input.id || input.name || 'ts-file') + '_tsname';
                box.appendChild(btn);
                box.appendChild(out);
                var d = input.getAttribute('aria-describedby');
                input.setAttribute('aria-describedby', (d ? d + ' ' : '') + out.id);
            }
            out.textContent = fileName(input);
            btn.addEventListener('click', function () { if (!input.disabled) { input.click(); } });
            input.addEventListener('change', function () { out.textContent = fileName(input); });
            box.classList.add('is-ready');
        });
    }

    // ---------- Solar Hijri dates (same algorithm as ts_website/tools.py) ----------
    var MONTHS = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند'];
    function div(a, b) { return Math.floor(a / b); }
    function mod(a, b) { return a - Math.floor(a / b) * b; }
    function g2j(gy, gm, gd) {
        var gdm = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
        var gy2 = gm > 2 ? gy + 1 : gy;
        var days = 355666 + 365 * gy + div(gy2 + 3, 4) - div(gy2 + 99, 100) + div(gy2 + 399, 400) + gd + gdm[gm - 1];
        var jy = -1595 + 33 * div(days, 12053);
        days = mod(days, 12053);
        jy += 4 * div(days, 1461);
        days = mod(days, 1461);
        if (days > 365) { jy += div(days - 1, 365); days = mod(days - 1, 365); }
        if (days < 186) { return [jy, 1 + div(days, 31), 1 + mod(days, 31)]; }
        return [jy, 7 + div(days - 186, 30), 1 + mod(days - 186, 30)];
    }
    function j2g(jy, jm, jd) {
        jy += 1595;
        var days = -355668 + 365 * jy + div(jy, 33) * 8 + div(mod(jy, 33) + 3, 4) + jd + (jm < 7 ? (jm - 1) * 31 : (jm - 7) * 30 + 186);
        var gy = 400 * div(days, 146097);
        days = mod(days, 146097);
        if (days > 36524) {
            days -= 1;
            gy += 100 * div(days, 36524);
            days = mod(days, 36524);
            if (days >= 365) { days += 1; }
        }
        gy += 4 * div(days, 1461);
        days = mod(days, 1461);
        if (days > 365) { gy += div(days - 1, 365); days = mod(days - 1, 365); }
        var gd = days + 1;
        var leap = (gy % 4 === 0 && gy % 100 !== 0) || gy % 400 === 0;
        var md = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
        var gm = 0;
        while (gm < 12 && gd > md[gm]) { gd -= md[gm]; gm += 1; }
        return [gy, gm + 1, gd];
    }
    function latin(s) {
        return String(s).replace(/[۰-۹]/g, function (c) { return String(c.charCodeAt(0) - 0x06F0); })
                        .replace(/[٠-٩]/g, function (c) { return String(c.charCodeAt(0) - 0x0660); });
    }
    function fa(s) { return String(s).replace(/[0-9]/g, function (c) { return '۰۱۲۳۴۵۶۷۸۹'.charAt(+c); }); }
    function pad(n, w) { n = String(n); while (n.length < w) { n = '0' + n; } return n; }
    function parseJalali(text) {          // -> [jy, jm, jd] or null
        var parts = latin(text).trim().split(/[\s\/\-.،,]+/).filter(Boolean);
        if (parts.length !== 3 || !parts.every(function (p) { return /^\d+$/.test(p); })) { return null; }
        var jy = +parts[0], jm = +parts[1], jd = +parts[2];
        if (jy < 100) { jy += jy < 50 ? 1400 : 1300; }
        if (jm < 1 || jm > 12 || jd < 1 || jd > 31 || jy < 1300 || jy > 1500) { return null; }
        var g = j2g(jy, jm, jd), back = g2j(g[0], g[1], g[2]);
        if (back[0] !== jy || back[1] !== jm || back[2] !== jd) { return null; }
        return [jy, jm, jd, g];
    }
    function initDates() {
        document.querySelectorAll('[data-ts-jdate]').forEach(function (box) {
            var input = box.querySelector('.ts-jdate__input');
            var iso = box.querySelector('.ts-jdate__iso');
            var out = box.querySelector('.ts-jdate__out');
            if (!input || !iso || box.getAttribute('data-ts-ready')) { return; }
            box.setAttribute('data-ts-ready', '1');
            function update(final) {
                var v = input.value.trim();
                if (!v) {
                    iso.value = '';
                    input.removeAttribute('aria-invalid');
                    if (out) { out.textContent = ''; out.classList.remove('is-bad'); }
                    return;
                }
                var j = parseJalali(v);
                if (!j) {
                    iso.value = '';
                    if (final) {
                        input.setAttribute('aria-invalid', 'true');
                        if (out) { out.textContent = 'این تاریخ درست نیست؛ به شکل ۱۴۰۵/۰۷/۲۰ بنویسید.'; out.classList.add('is-bad'); }
                    }
                    return;
                }
                var g = j[3];
                iso.value = pad(g[0], 4) + '-' + pad(g[1], 2) + '-' + pad(g[2], 2);
                input.removeAttribute('aria-invalid');
                if (out) { out.textContent = fa(j[2] + ' ' + MONTHS[j[1] - 1] + ' ' + j[0]); out.classList.remove('is-bad'); }
                if (final) { input.value = fa(pad(j[0], 4) + '/' + pad(j[1], 2) + '/' + pad(j[2], 2)); }
            }
            input.addEventListener('input', function () { update(false); });
            input.addEventListener('blur', function () { update(true); });
            var form = input.form;
            if (form) { form.addEventListener('submit', function () { update(true); }); }
            if (input.value) { update(false); }
        });
    }

    function init() {
        openFromHash();
        initScrollers();
        initFiles();
        initDates();
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
