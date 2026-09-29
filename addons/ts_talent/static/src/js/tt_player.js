/** @odoo-module ignore **/
// Interactive talent inventory: autosave every answer, keys 1-5, show/hide of the
// person's own raw answers in the report. The forms still work without JS.
(function () {
    'use strict';
    function form() { return document.querySelector('.tt-qform'); }

    document.addEventListener('change', function (ev) {
        var input = ev.target;
        if (!input.matches || !input.matches('.tt-q input[type="radio"]')) { return; }
        var f = form();
        if (!f) { return; }
        var q = input.closest('.tt-q');
        q.classList.add('is-answered');
        q.classList.remove('is-missing');
        var state = f.querySelector('.tt-save');
        var body = new FormData();
        body.append('csrf_token', f.querySelector('input[name="csrf_token"]').value);
        body.append('item', q.getAttribute('data-item'));
        body.append('value', input.value);
        body.append('field', f.getAttribute('data-field'));
        if (state) { state.classList.remove('is-error'); state.textContent = 'در حال ذخیره…'; }
        fetch('/take/' + f.getAttribute('data-token') + '/answer', { method: 'POST', body: body, credentials: 'same-origin' })
            .then(function (r) { return r.json().then(function (j) { return { ok: r.ok && j.ok, j: j }; }); })
            .then(function (res) {
                if (!res.ok) { throw new Error(res.j && res.j.error); }
                if (state) { state.textContent = 'ذخیره شد'; }
            })
            .catch(function () {
                if (state) { state.classList.add('is-error'); state.textContent = 'ذخیره نشد؛ با دکمهٔ ادامه دوباره ذخیره می‌شود'; }
            });
        var next = q.nextElementSibling;
        while (next && !(next.classList && next.classList.contains('tt-q'))) { next = next.nextElementSibling; }
        if (next && !next.querySelector('input:checked') && next.scrollIntoView) {
            setTimeout(function () { next.scrollIntoView({ behavior: 'smooth', block: 'center' }); }, 180);
        }
    });

    document.addEventListener('keydown', function (ev) {
        if (ev.ctrlKey || ev.metaKey || ev.altKey) { return; }
        var t = ev.target;
        if (t && t.matches && t.matches('input[type="text"], textarea, select')) { return; }
        var key = ev.key;
        var map = { '۱': '1', '۲': '2', '۳': '3', '۴': '4', '۵': '5' };
        key = map[key] || key;
        if (!/^[1-5]$/.test(key)) { return; }
        var f = form();
        if (!f) { return; }
        var qs = f.querySelectorAll('.tt-q');
        var target = null;
        var focused = t && t.closest ? t.closest('.tt-q') : null;
        if (focused) { target = focused; }
        else {
            for (var i = 0; i < qs.length; i++) { if (!qs[i].querySelector('input:checked')) { target = qs[i]; break; } }
        }
        if (!target) { return; }
        var radio = target.querySelector('input[value="' + key + '"]');
        if (radio) {
            radio.checked = true;
            radio.dispatchEvent(new Event('change', { bubbles: true }));
            ev.preventDefault();
        }
    });

    document.addEventListener('click', function (ev) {
        var btn = ev.target.closest && ev.target.closest('.tt-toggle');
        if (!btn) { return; }
        var box = document.getElementById(btn.getAttribute('aria-controls'));
        if (!box) { return; }
        var open = btn.getAttribute('aria-expanded') === 'true';
        btn.setAttribute('aria-expanded', open ? 'false' : 'true');
        btn.textContent = open ? 'نمایش پاسخ‌های من' : 'پنهان کردن پاسخ‌های من';
        if (open) { box.setAttribute('hidden', 'hidden'); } else { box.removeAttribute('hidden'); }
    });

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('.tt-q').forEach(function (q) {
            if (q.querySelector('input:checked')) { q.classList.add('is-answered'); }
        });
        var first = document.querySelector('#tt-label');
        if (first) { first.focus(); }
    });
})();
