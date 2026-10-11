/** @odoo-module ignore **/
// Interactive talent inventory: autosave every answer (state shown in the top bar), digit keys 1-5 only while a
// statement has focus (WCAG 2.1.4), field-name suggestions, collapsible report sections (button + aria-expanded +
// hidden; open without JS) and the person's own raw answers. The forms still work without JS.
(function () {
    'use strict';
    function form() { return document.querySelector('.tt-qform'); }
    function saveState() { return document.querySelector('.tt-save'); }

    document.addEventListener('change', function (ev) {
        var input = ev.target;
        if (!input.matches || !input.matches('.tt-q input[type="radio"]')) { return; }
        var f = form();
        if (!f) { return; }
        var q = input.closest('.tt-q');
        q.classList.add('is-answered');
        q.classList.remove('is-missing');
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
            })
            .catch(function () {
                if (state) { state.classList.add('is-error'); state.textContent = 'ذخیره نشد؛ با دکمهٔ پایین صفحه دوباره ذخیره می‌شود'; }
            });
        var next = q.nextElementSibling;
        while (next && !(next.classList && next.classList.contains('tt-q'))) { next = next.nextElementSibling; }
        if (next && !next.querySelector('input:checked') && next.scrollIntoView) {
            setTimeout(function () { next.scrollIntoView({ behavior: 'smooth', block: 'center' }); }, 180);
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
        var sec = ev.target.closest && ev.target.closest('.tt-sec__btn');
        if (sec) { setOpen(sec, sec.getAttribute('aria-expanded') !== 'true'); return; }
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
        var first = document.querySelector('#tt-label');
        if (first && !first.value) { first.focus(); }
    });

    // Printing always shows every section.
    window.addEventListener('beforeprint', function () {
        document.querySelectorAll('.tt-sec__btn[aria-expanded="false"]').forEach(function (b) { b.setAttribute('data-tt-reclose', '1'); setOpen(b, true); });
    });
    window.addEventListener('afterprint', function () {
        document.querySelectorAll('.tt-sec__btn[data-tt-reclose]').forEach(function (b) { b.removeAttribute('data-tt-reclose'); setOpen(b, false); });
    });
})();
