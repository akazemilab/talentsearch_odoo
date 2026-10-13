/** @odoo-module ignore **/
// Interactive talent inventory: autosave every answer (state shown in the top bar, and next to the statement and the
// page button when it fails), digit keys 1-5 only while a statement has focus (WCAG 2.1.4), field-name suggestions,
// collapsible report sections and consent details (button + aria-expanded + hidden; open without JS) and the person's
// own raw answers. The forms still work without JS.
(function () {
    'use strict';
    var FAIL = 'ذخیره نشد؛ با دکمهٔ پایین صفحه دوباره ذخیره می‌شود';
    function form() { return document.querySelector('.tt-qform'); }
    function saveState() { return document.querySelector('.tt-save'); }
    function reduced() { return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches); }
    function failNote(q, on) {
        var n = q.querySelector('.tt-unsaved');
        if (on && !n) {
            n = document.createElement('p');
            n.className = 'tt-unsaved';
            n.textContent = 'ذخیره نشد';
            var opts = q.querySelector('.tt-opts');
            q.insertBefore(n, opts);
        }
        if (!on && n) { n.remove(); }
        q.classList.toggle('is-unsaved', !!on);
        var all = document.querySelector('.tt-savefail');
        if (all) {
            var any = !!document.querySelector('.tt-q.is-unsaved');
            all.textContent = any ? FAIL : '';
            if (any) { all.removeAttribute('hidden'); } else { all.setAttribute('hidden', 'hidden'); }
        }
    }

    document.addEventListener('change', function (ev) {
        var input = ev.target;
        if (!input.matches || !input.matches('.tt-q input[type="radio"]')) { return; }
        var f = form();
        if (!f) { return; }
        var q = input.closest('.tt-q');
        q.classList.add('is-answered');
        if (q.classList.contains('is-missing')) {
            q.classList.remove('is-missing');
            var miss = q.querySelector('.tt-miss');
            if (miss) { miss.remove(); }
            var grp = q.querySelector('.tt-opts');
            if (grp) { grp.removeAttribute('aria-invalid'); grp.removeAttribute('aria-describedby'); }
        }
        var state = saveState();
        var body = new FormData();
        body.append('csrf_token', f.querySelector('input[name="csrf_token"]').value);
        body.append('item', q.getAttribute('data-item'));
        body.append('value', input.value);
        body.append('field', f.getAttribute('data-field'));
        if (state) { state.classList.remove('is-error', 'is-ok'); state.textContent = 'در حال ذخیره…'; }
        fetch('/take/' + f.getAttribute('data-token') + '/answer', { method: 'POST', body: body, credentials: 'same-origin' })
            .then(function (r) { return r.json().then(function (j) { return { ok: r.ok && j.ok, j: j }; }); })
            .then(function (res) {
                if (!res.ok) { throw new Error(res.j && res.j.error); }
                if (state) { state.classList.add('is-ok'); state.textContent = 'ذخیره شد'; }
                failNote(q, false);
            })
            .catch(function () {
                if (state) { state.classList.add('is-error'); state.textContent = FAIL; }
                failNote(q, true);      // the top bar is scrolled away on a phone: mark the statement too (UX audit T7 P4-1)
            });
        // bring the next unanswered statement up only when it is below the screen; no animation for reduced motion
        var next = q.nextElementSibling;
        while (next && !(next.classList && next.classList.contains('tt-q'))) { next = next.nextElementSibling; }
        if (next && !next.querySelector('input:checked') && next.scrollIntoView) {
            setTimeout(function () {
                var r = next.getBoundingClientRect();
                if (r.bottom > window.innerHeight) { next.scrollIntoView({ behavior: reduced() ? 'auto' : 'smooth', block: 'center' }); }
            }, 180);
        }
    });

    // Digits answer only the statement that has keyboard focus; there is no page-wide shortcut.
    document.addEventListener('keydown', function (ev) {
        if (ev.ctrlKey || ev.metaKey || ev.altKey) { return; }
        var t = ev.target;
        var q = t && t.closest ? t.closest('.tt-q') : null;
        if (!q || !form()) { return; }
        var map = { '۱': '1', '۲': '2', '۳': '3', '۴': '4', '۵': '5' };
        var key = map[ev.key] || ev.key;
        if (!/^[1-5]$/.test(key)) { return; }
        var radio = q.querySelector('input[value="' + key + '"]');
        if (radio) {
            radio.checked = true;
            radio.focus();
            radio.dispatchEvent(new Event('change', { bubbles: true }));
            ev.preventDefault();
        }
    });

    function setOpen(btn, open) {
        var box = document.getElementById(btn.getAttribute('aria-controls'));
        if (!box) { return; }
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
        if (open) { box.removeAttribute('hidden'); } else { box.setAttribute('hidden', 'hidden'); }
    }

    document.addEventListener('click', function (ev) {
        var raw = ev.target.closest && ev.target.closest('.tt-toggle');
        if (raw) {
            var open = raw.getAttribute('aria-expanded') === 'true';
            setOpen(raw, !open);
            raw.textContent = open ? 'نمایش پاسخ‌های من' : 'پنهان کردن پاسخ‌های من';
            return;
        }
        var sec = ev.target.closest && ev.target.closest('.tt-sec__btn, .tt-fold');
        if (sec) { setOpen(sec, sec.getAttribute('aria-expanded') !== 'true'); return; }
        var more = ev.target.closest && ev.target.closest('.tt-cmp-more');
        if (more) {
            document.querySelectorAll('.tt-cmp__row[data-tt-more]').forEach(function (r) { r.removeAttribute('hidden'); });
            more.remove();
            return;
        }
        var chip = ev.target.closest && ev.target.closest('.tt-chip');
        if (chip) {
            var input = document.getElementById('tt-label');
            if (input) { input.value = chip.getAttribute('data-fill'); input.focus(); }
            return;
        }
        var jump = ev.target.closest && ev.target.closest('.tt-jump a[href^="#"]');
        if (jump) {
            var target = document.querySelector(jump.getAttribute('href'));
            var btn = target && target.querySelector('.tt-sec__btn');
            if (btn) { setOpen(btn, true); }
        }
    });

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('.tt-q').forEach(function (q) {
            if (q.querySelector('input:checked')) { q.classList.add('is-answered'); }
        });
        document.querySelectorAll('[data-tt-chips]').forEach(function (el) { el.removeAttribute('hidden'); });
        var phone = window.matchMedia && window.matchMedia('(max-width: 640px)').matches;
        document.querySelectorAll('.tt-sec[data-collapse]').forEach(function (sec) {
            var mode = sec.getAttribute('data-collapse');
            var btn = sec.querySelector('.tt-sec__btn');
            if (btn && (mode === 'always' || (mode === 'phone' && phone)) && location.hash !== '#' + sec.id) { setOpen(btn, false); }
        });
        // consent details fold once the page can open them again
        document.querySelectorAll('[data-tt-fold]').forEach(function (b) { setOpen(b, false); });
        // fields side by side: on a phone the first two rows, the rest behind one button (UX audit T7 P9-1)
        var rows = document.querySelectorAll('.tt-compare .tt-cmp__row');
        if (phone && rows.length > 3) {
            rows.forEach(function (r, i) { if (i >= 2) { r.setAttribute('hidden', 'hidden'); r.setAttribute('data-tt-more', '1'); } });
            var b = document.createElement('button');
            b.type = 'button';
            b.className = 'tt-toggle tt-cmp-more';
            b.textContent = 'نمایش همهٔ توانایی‌ها';
            rows[1].parentNode.insertBefore(b, rows[2]);
        }
        // an empty name field gets focus only with a mouse or with an error: on a phone the keyboard would cover the
        // guidance and the suggestions the person needs first (UX audit T7 P2-2)
        var first = document.querySelector('#tt-label');
        var fine = window.matchMedia && window.matchMedia('(pointer: fine)').matches;
        if (first && !first.value && (fine || document.querySelector('.tt-error'))) { first.focus(); }
        // after «صفحهٔ بعد» with a gap: the summary is read out, the first unanswered statement is brought into view
        var miss = document.querySelector('.tt-q.is-missing');
        var summary = document.getElementById('tt-error-summary');
        if (miss) {
            if (summary && summary.focus) { summary.focus({ preventScroll: true }); }
            miss.scrollIntoView({ behavior: 'auto', block: 'center' });
        }
    });

    // Printing always shows every section.
    window.addEventListener('beforeprint', function () {
        document.querySelectorAll('.tt-sec__btn[aria-expanded="false"]').forEach(function (b) { b.setAttribute('data-tt-reclose', '1'); setOpen(b, true); });
        document.querySelectorAll('.tt-cmp__row[data-tt-more]').forEach(function (r) { r.removeAttribute('hidden'); });
    });
    window.addEventListener('afterprint', function () {
        document.querySelectorAll('.tt-sec__btn[data-tt-reclose]').forEach(function (b) { b.removeAttribute('data-tt-reclose'); setOpen(b, false); });
    });
})();
