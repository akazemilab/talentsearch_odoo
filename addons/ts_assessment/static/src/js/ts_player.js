/** @odoo-module ignore **/
// Talent Search player: autosave each answer as it is chosen (the page form
// still saves everything on "next" when JS is unavailable), live progress,
// double-submit protection, and the report's print button.
(function () {
    'use strict';
    var FA = '۰۱۲۳۴۵۶۷۸۹';
    function fa(n) { return String(n).replace(/[0-9]/g, function (d) { return FA[+d]; }); }

    function player() { return document.querySelector('.ts-player'); }

    document.addEventListener('change', function (ev) {
        var input = ev.target;
        if (!input.matches || !input.matches('.ts-q input[type="radio"]')) { return; }
        var root = player();
        if (!root) { return; }
        var li = input.closest('.ts-q');
        var form = input.closest('form');
        var state = root.querySelector('.ts-save-state');
        li.classList.add('is-answered');
        var body = new FormData();
        body.append('csrf_token', form.querySelector('input[name="csrf_token"]').value);
        body.append('item', li.getAttribute('data-item'));
        body.append('value', input.value);
        if (state) { state.classList.remove('is-error'); state.textContent = 'در حال ذخیره…'; }
        fetch('/take/' + root.getAttribute('data-token') + '/answer', { method: 'POST', body: body, credentials: 'same-origin' })
            .then(function (r) { return r.json().then(function (j) { return { ok: r.ok && j.ok, j: j }; }); })
            .then(function (res) {
                if (!res.ok) { throw new Error(res.j && res.j.error); }
                var total = res.j.total || +root.getAttribute('data-total');
                var el = root.querySelector('.ts-js-answered');
                if (el) { el.textContent = fa(res.j.answered); }
                var bar = root.querySelector('.ts-progress__bar');
                if (bar && total) { bar.style.width = Math.round(100 * res.j.answered / total) + '%'; }
                var pb = root.querySelector('.ts-progress');
                if (pb) { pb.setAttribute('aria-valuenow', res.j.answered); }
                if (state) { state.textContent = 'ذخیره شد'; }
            })
            .catch(function () {
                if (state) { state.classList.add('is-error'); state.textContent = 'ذخیره نشد؛ با «صفحهٔ بعد» دوباره ذخیره می‌شود'; }
            });
    });

    document.addEventListener('submit', function (ev) {
        var form = ev.target;
        if (!form.classList || !form.classList.contains('ts-submit-form')) { return; }
        if (form.getAttribute('data-sent')) { ev.preventDefault(); return; }
        form.setAttribute('data-sent', '1');
        var btn = form.querySelector('button[type="submit"]');
        if (btn) { btn.setAttribute('aria-disabled', 'true'); btn.textContent = 'در حال ارسال…'; }
    });

    document.addEventListener('click', function (ev) {
        if (ev.target.closest && ev.target.closest('.ts-js-print')) { window.print(); }
    });

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('.ts-q').forEach(function (li) {
            if (li.querySelector('input:checked')) { li.classList.add('is-answered'); }
        });
    });
})();
