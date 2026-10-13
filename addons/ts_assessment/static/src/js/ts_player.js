/** @odoo-module ignore **/
// Talent Search player: autosave each answer as it is chosen (the page form
// still saves everything on "next" when JS is unavailable), live progress,
// a one-time notice when «صفحهٔ بعد» leaves items unanswered, double-submit
// protection, the consent page's disclosure and error focus, and the report's
// print button.
(function () {
    'use strict';
    var FA = '۰۱۲۳۴۵۶۷۸۹';
    function fa(n) { return String(n).replace(/[0-9]/g, function (d) { return FA[+d]; }); }

    function player() { return document.querySelector('.ts-player'); }
    function isTu() { var p = player(); return !!(p && p.getAttribute('data-tu')); }

    // ------------------------------------------------------------------ autosave (B8-7: one spoken «saved» per page,
    // every failure spoken; the visible «ذخیره شد ✓» fades after 2 s)
    var announced = false;
    var fadeTimer = null;
    function say(text) {
        var live = document.querySelector('.ts-save-live');
        if (live) { live.textContent = ''; window.setTimeout(function () { live.textContent = text; }, 50); }
    }
    function showState(text, isError) {
        var state = document.querySelector('.ts-save-state');
        if (!state) { return; }
        window.clearTimeout(fadeTimer);
        state.classList.toggle('is-error', !!isError);
        state.classList.remove('is-faded');
        state.textContent = text;
        if (!isError && text.indexOf('✓') !== -1) {
            fadeTimer = window.setTimeout(function () { state.classList.add('is-faded'); }, 2000);
        }
    }

    document.addEventListener('change', function (ev) {
        var input = ev.target;
        if (!input.matches || !input.matches('.ts-q input[type="radio"]')) { return; }
        var root = player();
        if (!root) { return; }
        var li = input.closest('.ts-q');
        var form = input.closest('form');
        li.classList.add('is-answered');
        li.removeAttribute('data-missing');
        var flag = li.querySelector('.ts-q__flag');
        if (flag) { flag.remove(); }
        var body = new FormData();
        body.append('csrf_token', form.querySelector('input[name="csrf_token"]').value);
        body.append('item', li.getAttribute('data-item'));
        body.append('value', input.value);
        showState('در حال ذخیره…', false);
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
                if (pb) {
                    pb.setAttribute('aria-valuenow', res.j.answered);
                    pb.setAttribute('aria-valuetext', fa(res.j.answered) + ' از ' + fa(total) + ' پرسش');
                }
                showState('ذخیره شد ✓', false);
                if (!announced) { announced = true; say('پاسخ ذخیره شد. پاسخ‌های بعدی هم خودکار ذخیره می‌شوند.'); }
            })
            .catch(function () {
                var msg = 'ذخیره نشد؛ با دکمهٔ پایین صفحه دوباره فرستاده می‌شود';
                showState(msg, true);
                say(msg);
            });
    });

    // ------------------------------------------------------------------ skipped items (B8-4a): the first «صفحهٔ بعد»
    // with unanswered items on this page stops once and names them; the second press continues
    function unanswered(form) {
        return Array.prototype.filter.call(form.querySelectorAll('.ts-q'), function (li) {
            return !li.querySelector('input[type="radio"]:checked');
        });
    }
    function skipNote(form, missing) {
        var box = document.getElementById('ts-skip-note');
        if (!box) { return false; }
        var tu = isTu();
        box.textContent = '';
        var p1 = document.createElement('p');
        var strong = document.createElement('strong');
        strong.textContent = (missing.length === 1 ? 'یک پرسش' : fa(missing.length) + ' پرسش') + ' این صفحه بی‌پاسخ مانده است: ';
        p1.appendChild(strong);
        missing.forEach(function (li, i) {
            var num = li.querySelector('.ts-q__num');
            var a = document.createElement('a');
            a.href = '#' + li.id;
            a.className = 'ts-skip-note__link';
            a.textContent = 'پرسش ' + (num ? num.textContent : fa(i + 1));
            a.addEventListener('click', function (ev) {
                ev.preventDefault();
                li.setAttribute('data-missing', '1');
                var first = li.querySelector('input[type="radio"]');
                li.scrollIntoView({ block: 'center' });
                if (first) { first.focus({ preventScroll: true }); }
            });
            if (i) { p1.appendChild(document.createTextNode('، ')); }
            p1.appendChild(a);
        });
        var p2 = document.createElement('p');
        p2.textContent = tu
            ? 'برای ساخته شدن نتیجه، همهٔ پرسش‌ها پاسخ لازم دارند. می‌توانی حالا پاسخ بدهی یا ادامه بدهی و بعداً برگردی.'
            : 'برای ساخته شدن نتیجه، همهٔ پرسش‌ها پاسخ لازم دارند. می‌توانید حالا پاسخ دهید یا ادامه دهید و بعداً برگردید.';
        var btn = document.createElement('button');
        btn.type = 'submit';
        btn.name = 'go';
        btn.value = 'next';
        btn.className = 'ts-btn ts-btn--outline ts-skip-note__go';
        btn.textContent = 'ادامه بدون پاسخ';
        box.appendChild(p1);
        box.appendChild(p2);
        box.appendChild(btn);
        box.removeAttribute('hidden');
        missing.forEach(function (li) { li.setAttribute('data-missing', '1'); });
        box.focus();
        return true;
    }

    document.addEventListener('submit', function (ev) {
        var form = ev.target;
        if (!form.classList) { return; }
        if (form.id === 'ts-qform') {
            var sub = ev.submitter;
            if (!sub || sub.value !== 'next' || form.getAttribute('data-skip-shown')) { return; }
            var missing = unanswered(form);
            if (!missing.length) { return; }
            if (skipNote(form, missing)) {
                ev.preventDefault();
                form.setAttribute('data-skip-shown', '1');
            }
            return;
        }
        if (!form.classList.contains('ts-submit-form')) { return; }
        if (form.getAttribute('data-sent')) { ev.preventDefault(); return; }
        form.setAttribute('data-sent', '1');
        var btn = form.querySelector('button[type="submit"]');
        if (btn) { btn.setAttribute('aria-disabled', 'true'); btn.textContent = 'در حال ارسال…'; }
    });

    document.addEventListener('click', function (ev) {
        if (ev.target.closest && ev.target.closest('.ts-js-print')) { window.print(); }
        // consent page: «جزئیات بیشتر» (a button with aria-expanded, never <details>)
        var more = ev.target.closest && ev.target.closest('.ts-more__btn');
        if (more) {
            var body = document.getElementById(more.getAttribute('aria-controls'));
            var open = more.getAttribute('aria-expanded') !== 'true';
            more.setAttribute('aria-expanded', open ? 'true' : 'false');
            if (body) { if (open) { body.removeAttribute('hidden'); } else { body.setAttribute('hidden', 'hidden'); } }
        }
        // error summary links: move focus to the control, not just scroll (GOV.UK error summary)
        var link = ev.target.closest && ev.target.closest('.ts-error-summary a[href^="#"]');
        if (link) {
            var target = document.getElementById(link.getAttribute('href').slice(1));
            if (target) {
                ev.preventDefault();
                var box = document.getElementById('ts-guardian-box');
                if (box && box.contains(target)) { box.removeAttribute('hidden'); }
                target.scrollIntoView({ block: 'center' });
                target.focus({ preventScroll: true });
            }
        }
    });

    // Consent pages: the guardian confirmation appears only after «under 18» (no-JS keeps it visible; the server
    // still validates it). UX audit G1-P12-2.
    function syncGuardian() {
        var box = document.getElementById('ts-guardian-box');
        if (!box) { return; }
        var no = document.querySelector('input[name="age18"][value="no"]');
        var show = !!(no && no.checked);
        if (show) { box.removeAttribute('hidden'); } else { box.setAttribute('hidden', 'hidden'); }
        var cb = box.querySelector('input[name="guardian_ok"]');
        if (cb) { if (show) { cb.setAttribute('required', 'required'); } else { cb.removeAttribute('required'); cb.checked = false; } }
    }
    document.addEventListener('change', function (ev) {
        if (ev.target && ev.target.name === 'age18') { syncGuardian(); }
    });

    document.addEventListener('DOMContentLoaded', function () {
        syncGuardian();
        document.querySelectorAll('.ts-q').forEach(function (li) {
            if (li.querySelector('input:checked')) { li.classList.add('is-answered'); }
        });
        // the consent details start closed once JS runs (no-JS: open, the button stays hidden)
        document.querySelectorAll('.ts-more__btn').forEach(function (btn) {
            var body = document.getElementById(btn.getAttribute('aria-controls'));
            btn.removeAttribute('hidden');
            btn.setAttribute('aria-expanded', 'false');
            if (body) { body.setAttribute('hidden', 'hidden'); }
        });
        // after an error redirect: focus the summary under the H1 (B2-1, B4-2); pages without a summary (talent consent)
        // focus their first inline error
        var summary = document.getElementById('ts-error-summary');
        var err = summary || document.querySelector('form .ts-form__error[tabindex]');
        if (err) {
            err.scrollIntoView({ block: 'center' });
            err.focus({ preventScroll: true });
        }
    });
})();
