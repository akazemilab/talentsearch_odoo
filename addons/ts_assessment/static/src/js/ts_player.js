/** @odoo-module ignore **/
// Talent Search player: autosave each answer as it is chosen (the page form
// still saves everything on "next" when JS is unavailable), live progress,
// a one-time notice when «صفحهٔ بعد» leaves items unanswered, double-submit
// protection, the consent page's disclosure and error focus, and the report's
// print button.
// Career completion (docs/career/01_completion.md): answers that could not be saved (a dropped mobile connection) wait
// in this browser and are sent again; card mode (data-card on .ts-player) shows one item at a time with auto-advance.
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

    // answers waiting in this browser: {item id: value}, one key per player address (storage may be missing: then the
    // page form still posts every answer of the page)
    function qKey() {
        var r = player();
        return r ? 'tsq:' + (r.getAttribute('data-answer-url') || r.getAttribute('data-token') || '') : null;
    }
    function qRead() {
        try { return JSON.parse(window.localStorage.getItem(qKey()) || '{}') || {}; } catch (e) { return {}; }
    }
    function qWrite(o) {
        try {
            if (Object.keys(o).length) { window.localStorage.setItem(qKey(), JSON.stringify(o)); }
            else { window.localStorage.removeItem(qKey()); }
        } catch (e) { /* no storage: nothing kept */ }
    }
    function qSet(item, value) { var o = qRead(); if (value === null) { delete o[item]; } else { o[item] = value; } qWrite(o); }

    function csrf() {
        var el = document.querySelector('#ts-qform input[name="csrf_token"]');
        return el ? el.value : '';
    }

    function post(item, value) {
        var root = player();
        if (!root) { return; }
        var body = new FormData();
        body.append('csrf_token', csrf());
        body.append('item', item);
        body.append('value', value);
        qSet(item, value);
        showState('در حال ذخیره…', false);
        // onb2: the page names its own autosave address (the guest player has no token in any address)
        var url = root.getAttribute('data-answer-url') || ('/take/' + root.getAttribute('data-token') + '/answer');
        fetch(url, { method: 'POST', body: body, credentials: 'same-origin' })
            .then(function (r) {
                return r.json().then(function (j) { return { ok: r.ok && j.ok, status: r.status, j: j }; },
                    function () { return { ok: false, status: r.status, j: {} }; });
            })
            .then(function (res) {
                if (!res.ok) {
                    // a refused answer (4xx other than «slow down») is dropped; the page form posts it again anyway
                    if (res.status >= 400 && res.status < 500 && res.status !== 429) { qSet(item, null); }
                    throw new Error(res.j && res.j.error);
                }
                qSet(item, null);
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
                var msg = 'اینترنت قطع است؛ پاسخ در همین گوشی نگه داشته شد و دوباره فرستاده می‌شود';
                showState(msg, true);
                say(msg);
            });
    }

    function resend() {
        var o = qRead();
        Object.keys(o).forEach(function (item) {
            var input = document.querySelector('.ts-q[data-item="' + item + '"] input[value="' + o[item] + '"]');
            if (input && !input.checked) {
                input.checked = true;
                var li = input.closest('.ts-q');
                if (li) { li.classList.add('is-answered'); }
            }
            post(item, o[item]);
        });
    }
    window.addEventListener('online', resend);

    document.addEventListener('change', function (ev) {
        var input = ev.target;
        if (!input.matches || !input.matches('.ts-q input[type="radio"]')) { return; }
        var root = player();
        if (!root) { return; }
        var li = input.closest('.ts-q');
        li.classList.add('is-answered');
        li.removeAttribute('data-missing');
        var flag = li.querySelector('.ts-q__flag');
        if (flag) { flag.remove(); }
        post(li.getAttribute('data-item'), input.value);
        cardAnswered(li);
    });

    // ------------------------------------------------------------------ skipped items (B8-4a): the first «صفحهٔ بعد»
    // with unanswered items on this page stops once and names them; the second press continues
    function unanswered(form) {
        return Array.prototype.filter.call(form.querySelectorAll('.ts-q'), function (li) {
            return !li.querySelector('input[type="radio"]:checked');
        });
    }
    function skipNote(form, missing, go) {
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
        btn.value = go || 'next';      // the same way on: «صفحهٔ بعد» or, on the last page, «مرور و ارسال» (verify T7)
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
            // verify T7: the last page's «مرور و ارسال» names this page's gaps once too
            if (!sub || (sub.value !== 'next' && sub.value !== 'review') || form.getAttribute('data-skip-shown')) { return; }
            var missing = unanswered(form);
            if (!missing.length) { return; }
            if (skipNote(form, missing, sub.value)) {
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

    // ------------------------------------------------------------------ card mode (phase C): one item at a time,
    // auto-advance after an answer, a visible «قبلی» (the one complaint about auto-advance in the research is that going
    // back looked impossible). After the page's last item: the end card (#ts-cardend, written by the page when it has one)
    // and the page's own buttons. The page form still holds every item of the page and posts them all.
    var card = null;
    var advanceTimer = null;
    function cardForm() { return document.getElementById('ts-qform'); }
    function cardItems(form) { return Array.prototype.slice.call(form.querySelectorAll('.ts-q')); }
    function cardShow(idx, focus) {
        var form = cardForm();
        if (!card || !form) { return; }
        var lis = cardItems(form);
        idx = Math.max(0, Math.min(idx, lis.length));
        var end = idx >= lis.length;
        card.idx = idx;
        lis.forEach(function (li, i) { li.classList.toggle('is-current', i === idx); });
        form.classList.toggle('is-end', end);
        var endBox = document.getElementById('ts-cardend');
        var nav = form.querySelector('.ts-qnav');
        if (endBox) { endBox.hidden = !end; }
        // an end card with its own buttons (data-own-nav) keeps the page bar hidden
        if (nav) { nav.hidden = !end || !!(endBox && endBox.hasAttribute('data-own-nav')); }
        var root = player();
        var first = +(root.getAttribute('data-first') || 0);
        var total = +(root.getAttribute('data-total') || lis.length);
        var pos = form.querySelector('.ts-cardpos');
        if (pos) { pos.textContent = end ? '' : 'سؤال ' + fa(first + idx + 1) + ' از ' + fa(total); }
        var next = form.querySelector('.ts-card-next');
        if (next) { next.hidden = end; }
        var prev = form.querySelector('.ts-card-prev');
        if (prev) { prev.hidden = (idx === 0 && !form.querySelector('button[name="go"][value="prev"]')); }
        if (end) {
            var missing = unanswered(form);
            var note = document.getElementById('ts-cardend-missing');
            if (note) {
                note.hidden = !missing.length;
                var n = note.querySelector('.ts-cardend-missing__n');
                if (n) { n.textContent = fa(missing.length); }
            }
            // the end card names this page's gaps itself: «صفحهٔ بعد» goes on without the one-time stop
            form.setAttribute('data-skip-shown', '1');
        }
        if (focus) {
            var target = end ? (endBox || nav) : lis[idx].querySelector('legend');
            if (target) {
                if (!target.hasAttribute('tabindex')) { target.setAttribute('tabindex', '-1'); }
                target.focus({ preventScroll: true });
            }
            var head = root.querySelector('.ts-player__head') || root;
            if (head.getBoundingClientRect().top < 0) { head.scrollIntoView({ block: 'start' }); }
        }
    }
    function cardAnswered(li) {
        if (!card) { return; }
        var lis = cardItems(cardForm());
        var i = lis.indexOf(li);
        if (i !== card.idx) { return; }
        window.clearTimeout(advanceTimer);
        // a short pause: the chosen answer is seen before the next item comes (a changed mind restarts it)
        advanceTimer = window.setTimeout(function () { cardShow(i + 1, true); }, 280);
    }
    function cardPrev() {
        var form = cardForm();
        if (!card || !form) { return; }
        window.clearTimeout(advanceTimer);
        if (card.idx > 0) { cardShow(card.idx - 1, true); return; }
        var back = form.querySelector('button[name="go"][value="prev"]');
        if (back) {
            if (form.requestSubmit) { form.requestSubmit(back); } else { back.click(); }
        }
    }
    function cardInit() {
        var root = player();
        var form = cardForm();
        if (!root || !form || root.getAttribute('data-card') !== '1') { return; }
        card = { idx: 0 };
        form.classList.add('is-card');
        var bar = document.createElement('div');
        bar.className = 'ts-cardnav';
        var pos = document.createElement('p');
        pos.className = 'ts-cardpos';
        pos.setAttribute('aria-live', 'polite');
        var prev = document.createElement('button');
        prev.type = 'button';
        prev.className = 'ts-btn ts-btn--outline ts-card-prev';
        prev.textContent = 'قبلی';
        var next = document.createElement('button');
        next.type = 'button';
        next.className = 'ts-btn ts-btn--quiet ts-card-next';
        next.textContent = 'بعدی';
        bar.appendChild(prev);
        bar.appendChild(next);
        var list = form.querySelector('.ts-qlist');
        if (list) { list.parentNode.insertBefore(pos, list); list.parentNode.insertBefore(bar, list.nextSibling); }
        prev.addEventListener('click', cardPrev);
        next.addEventListener('click', function () { window.clearTimeout(advanceTimer); cardShow(card.idx + 1, true); });
        form.addEventListener('click', function (ev) {
            var miss = ev.target.closest && ev.target.closest('.ts-card-missing');
            if (miss) {
                ev.preventDefault();
                var gaps = unanswered(form);
                if (gaps.length) { cardShow(cardItems(form).indexOf(gaps[0]), true); }
            }
            var back = ev.target.closest && ev.target.closest('.ts-card-back');
            if (back) { ev.preventDefault(); cardPrev(); }
        });
        var lis = cardItems(form);
        var start = -1;
        if (location.hash && location.hash.indexOf('#q-') === 0) {
            start = lis.indexOf(document.getElementById(location.hash.slice(1)));
        }
        if (start < 0) { start = lis.indexOf(unanswered(form)[0]); }
        if (start < 0) { start = lis.length; }       // every item of this page answered: the end card
        cardShow(start, false);
    }

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

    // ------------------------------------------------------------------ report on a phone (verify T7, B15-3/B16-2):
    // each factor's long texts fold behind one button; the summary table's links open the factor they point to;
    // printing shows everything. Without JS (and in the PDF) every text stays open and the button hidden.
    function setFactor(btn, open) {
        var body = document.getElementById(btn.getAttribute('aria-controls'));
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
        if (btn.firstChild && btn.firstChild.nodeType === 3) {
            btn.firstChild.textContent = btn.getAttribute(open ? 'data-open' : 'data-closed');
        }
        if (body) { if (open) { body.removeAttribute('hidden'); } else { body.setAttribute('hidden', 'hidden'); } }
    }
    function openFactor(id) {
        var sec = id && document.getElementById(id);
        var btn = sec && sec.querySelector('.ts-factor__tog');
        if (btn && btn.getAttribute('aria-expanded') === 'false') { setFactor(btn, true); }
    }
    document.addEventListener('click', function (ev) {
        var tog = ev.target.closest && ev.target.closest('.ts-factor__tog');
        if (tog) { setFactor(tog, tog.getAttribute('aria-expanded') !== 'true'); return; }
        var jump = ev.target.closest && ev.target.closest('a[href^="#f-"]');
        if (jump) { openFactor(jump.getAttribute('href').slice(1)); }
    });
    window.addEventListener('hashchange', function () { openFactor(location.hash.slice(1)); });
    window.addEventListener('beforeprint', function () {
        document.querySelectorAll('.ts-factor__tog[aria-expanded="false"]').forEach(function (b) { b.setAttribute('data-reclose', '1'); setFactor(b, true); });
    });
    window.addEventListener('afterprint', function () {
        document.querySelectorAll('.ts-factor__tog[data-reclose]').forEach(function (b) { b.removeAttribute('data-reclose'); setFactor(b, false); });
    });

    document.addEventListener('DOMContentLoaded', function () {
        syncGuardian();
        var phone = window.matchMedia && window.matchMedia('(max-width: 575.98px)').matches;
        if (phone) {
            document.querySelectorAll('.ts-factor__tog').forEach(function (b) {
                b.removeAttribute('hidden');
                var sec = b.closest('.ts-factor');
                if (!(sec && location.hash === '#' + sec.id)) { setFactor(b, false); }
            });
        }
        document.querySelectorAll('.ts-q').forEach(function (li) {
            if (li.querySelector('input:checked')) { li.classList.add('is-answered'); }
        });
        // answers that waited in this browser (a dropped connection on the last visit) go out first
        if (player()) { resend(); }
        cardInit();
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
        var err = summary || document.getElementById('tt-err-finish') || document.querySelector('form .ts-form__error[tabindex]');
        if (err) {
            err.scrollIntoView({ block: 'center' });
            err.focus({ preventScroll: true });
        }
    });
})();
