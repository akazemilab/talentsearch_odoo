/** @odoo-module ignore **/
// Timed task player (docs/hr/01_architecture.md section 4). Overview before the first block -> per block: intro ->
// optional practice with feedback -> timed run. Answers of power blocks are saved one by one (queued and retried until
// the server has them; the queue is flushed before a block is closed); speed blocks post all trials at the end.
// The server keeps the keys and the deadline; this script only shows items and measures response times.
// UX audit T7 (2026-10-13): rules before the clock, honest save state, one focus-loss event per time away, a header
// exit that never suggests a pause, live time left on the resume screen.
(function () {
    'use strict';
    if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', main); } else { main(); }
    function main() {
    var FA = '۰۱۲۳۴۵۶۷۸۹';
    function fa(n) { return String(n).replace(/[0-9]/g, function (d) { return FA[+d]; }); }
    function el(tag, cls, text) {
        var e = document.createElement(tag);
        if (cls) { e.className = cls; }
        if (text !== undefined && text !== null) { e.textContent = text; }
        return e;
    }
    function svg(html) { var d = el('span', 'tst-svg'); d.innerHTML = html; return d; }   // our own server-built SVG
    function mmss(s) { s = Math.max(0, Math.ceil(s)); return fa(Math.floor(s / 60)) + ':' + fa(('0' + (s % 60)).slice(-2)); }
    // a duration in words for instructions («۴ دقیقه»، «۳ دقیقه و ۳۰ ثانیه»); m:ss only for the live countdown
    function dur(s) {
        s = Math.max(0, Math.round(s));
        var m = Math.floor(s / 60), r = s % 60;
        if (!m) { return fa(r) + ' ثانیه'; }
        return fa(m) + ' دقیقه' + (r ? ' و ' + fa(r) + ' ثانیه' : '');
    }
    function now() { return (window.performance && performance.now) ? performance.now() : Date.now(); }

    var root = document.querySelector('.tst-player');
    if (!root) { return; }
    var token = root.getAttribute('data-token');
    var csrf = root.getAttribute('data-csrf');
    var cfg = JSON.parse(root.getAttribute('data-config'));
    var org = root.getAttribute('data-org') || '';
    var stage = root.querySelector('.tst-stage');
    var live = root.querySelector('.tst-live');
    var focusLost = 0, running = false, timerId = null, keyHandler = null, hideClock = false;
    var practised = {};

    // ------------------------------------------------------------------ leaving the page during a block
    // One event per time away: switching apps fires both 'blur' and 'visibilitychange', which used to count twice.
    var away = false, backAt = 0, confirming = false;
    function leave() {
        if (!running || away || confirming) { return; }      // our own confirm dialog is not leaving the page
        away = true;
        if (Date.now() - backAt > 1000) { focusLost += 1; }     // a flicker right after coming back is the same absence
    }
    function back() { if (away) { away = false; backAt = Date.now(); } }
    document.addEventListener('visibilitychange', function () { if (document.hidden) { leave(); } else { back(); } });
    window.addEventListener('blur', leave);
    window.addEventListener('focus', function () { if (!document.hidden) { back(); } });

    // The focus-mode header link «ذخیره و خروج» must not suggest a pause while a block's clock runs.
    var exitLink = document.querySelector('.ts-header a.ts-btn[href="/my/assessments"]');
    var exitLabel = exitLink ? exitLink.textContent : '';
    function setRunning(v) {
        running = v;
        if (v) { away = !!document.hidden; }
        if (exitLink) { exitLink.textContent = v ? 'بازگشت به فهرست (زمان بخش ادامه دارد)' : exitLabel; }
    }
    if (exitLink) {
        exitLink.addEventListener('click', function (ev) {
            if (!running) { return; }
            confirming = true;
            var ok = window.confirm('زمان این بخش متوقف نمی‌شود و تا پایانش می‌گذرد. با این حال خارج می‌شوید؟');
            confirming = false;
            if (!ok) { ev.preventDefault(); return; }
            if (pendingCount()) { ev.preventDefault(); flush(4000).then(function () { window.location.href = exitLink.href; }); }
        });
    }

    function post(path, data) {
        var body = new FormData();
        body.append('csrf_token', csrf);
        Object.keys(data || {}).forEach(function (k) { body.append(k, typeof data[k] === 'object' ? JSON.stringify(data[k]) : data[k]); });
        return fetch('/take/' + token + '/task/' + path, { method: 'POST', body: body, credentials: 'same-origin' })
            .then(function (r) { return r.json().then(function (j) { if (!r.ok || j.ok === false) { throw j; } return j; }); });
    }
    function say(t) { if (live) { live.textContent = t; } }

    // ------------------------------------------------------------------ answer queue (power blocks)
    // An answer that did not reach the server (network) is kept and sent again with a growing pause; the server's own
    // refusals (time over, block closed, invalid item) are final. The newest answer to a question always wins.
    var queue = {}, inflight = {}, retryT = null, delay = 1000, hadError = false, waiters = [], saveLine = null, onTimeUp = null;
    function pendingCount() { return Object.keys(queue).length + Object.keys(inflight).length; }
    function setSave(state) {
        if (!saveLine) { return; }
        saveLine.className = 'tst-save' + (state ? ' is-' + state : '');
        saveLine.textContent = state === 'err' ? 'یک پاسخ هنوز ذخیره نشده است؛ دوباره تلاش می‌کنیم…' : (state === 'ok' ? 'همهٔ پاسخ‌ها ذخیره شد.' : '');
    }
    function queueAnswer(a) { queue[a.i + ':' + a.idx] = a; pump(); }
    function pump() { Object.keys(queue).forEach(function (k) { if (!inflight[k]) { send(k); } }); }
    function send(k) {
        var a = queue[k];
        delete queue[k];
        inflight[k] = a;
        post('answer', a).then(function () { settle(k, true); }, function (e) {
            if (e && e.reason === 'time') { settle(k, true); if (onTimeUp) { onTimeUp(); } return; }
            if (e && (e.reason || e.error)) { settle(k, true); return; }
            if (!(k in queue)) { queue[k] = a; }
            settle(k, false);
        });
    }
    function settle(k, ok) {
        delete inflight[k];
        if (ok) {
            delay = 1000;
            if (k in queue) { send(k); }
        } else {
            hadError = true;
            setSave('err');
            if (!retryT) { retryT = setTimeout(function () { retryT = null; pump(); }, delay); delay = Math.min(delay * 2, 8000); }
        }
        if (!pendingCount()) {
            if (hadError) { hadError = false; setSave('ok'); }
            var w = waiters;
            waiters = [];
            w.forEach(function (f) { f(); });
        }
    }
    function flush(maxMs) {
        return new Promise(function (resolve) {
            if (!pendingCount()) { resolve(); return; }
            waiters.push(resolve);
            if (retryT) { clearTimeout(retryT); retryT = null; }
            delay = 1000;
            pump();
            setTimeout(resolve, maxMs);
        });
    }

    function clear() {
        stage.innerHTML = '';
        saveLine = null;
        if (timerId) { clearInterval(timerId); timerId = null; }
        if (keyHandler) { document.removeEventListener('keydown', keyHandler); keyHandler = null; }
    }
    function btn(label, cls, fn) {
        var b = el('button', 'ts-btn ' + (cls || 'ts-btn--primary'), label);
        b.type = 'button';
        b.addEventListener('click', fn);
        return b;
    }
    function progressDots() {
        var ol = el('ol', 'tst-dots');
        ol.setAttribute('aria-label', 'بخش‌های این آزمون');
        cfg.blocks.forEach(function (b) {
            var li = el('li', 'tst-dots__i' + (b.done ? ' is-done' : '') + (b.i === cfg.current ? ' is-current' : ''));
            if (b.done) { var m = el('span', 'tst-dots__mark', '✓ '); m.setAttribute('aria-hidden', 'true'); li.appendChild(m); }
            li.appendChild(document.createTextNode(b.title));
            if (b.done) { li.appendChild(el('span', 'visually-hidden', ' (انجام شد)')); }
            if (b.i === cfg.current) { li.setAttribute('aria-current', 'step'); }
            ol.appendChild(li);
        });
        return ol;
    }
    function accomText() {
        var who = org ? '«' + org + '»' : 'سازمانی که شما را دعوت کرده است';
        return 'اگر به‌خاطر ناتوانی یا شرایط خاص به زمان بیشتر نیاز دارید، پیش از شروع بخش اول به ' + who
            + ' بگویید تا زمان بیشتری (۲۵ یا ۵۰ درصد) برایتان در نظر بگیرد.';
    }

    // ------------------------------------------------------------------ start screens
    function showDeviceCheck() {
        var touch = window.matchMedia && window.matchMedia('(pointer: coarse)').matches;
        if (!cfg.desktop || !touch || window.innerWidth >= 900) { return showOverview(); }
        clear();
        var box = el('div', 'ts-card tst-card');
        box.appendChild(el('h2', 'tst-h', 'این آزمون را بهتر است با رایانه انجام دهید'));
        box.appendChild(el('p', '', 'بخش‌های سرعت با صفحه‌کلید دقیق‌تر سنجیده می‌شوند. اگر رایانه در دسترس ندارید، با دکمه‌های روی صفحه هم می‌توانید پاسخ دهید.'));
        var row = el('div', 'tst-actions');
        row.appendChild(btn('ادامه با همین دستگاه', 'ts-btn--outline', showOverview));
        var later = el('a', 'ts-btn ts-btn--quiet', 'بعداً با رایانه ادامه می‌دهم');
        later.href = '/my/assessments';
        row.appendChild(later);
        box.appendChild(row);
        stage.appendChild(box);
    }

    // Before block 1 (nothing started yet): the whole effort and the rules, before any clock runs (ITC 2022 pre-test info).
    function showOverview() {
        var fresh = cfg.blocks.every(function (b) { return !b.started && !b.done; });
        if (!fresh) { return showIntro(); }
        clear();
        var blocks = cfg.blocks;
        var power = blocks.filter(function (b) { return !b.speed; });
        var nItems = power.reduce(function (s, b) { return s + (b.n || 0); }, 0);
        var box = el('div', 'ts-card tst-card');
        box.appendChild(el('h2', 'tst-h', 'پیش از شروع'));
        var facts = [fa(blocks.length) + ' بخش'];
        if (power.length === blocks.length && nItems) { facts.push(fa(nItems) + ' پرسش'); }
        if (cfg.minutes) { facts.push('روی هم حدود ' + fa(cfg.minutes) + ' دقیقه'); }
        box.appendChild(el('p', 'tst-facts', facts.join(' · ')));
        var ul = el('ul', 'tst-rules');
        function li(t) { ul.appendChild(el('li', '', t)); }
        li('زمان هر بخش با «شروع بخش» آغاز می‌شود و با بستن صفحه متوقف نمی‌شود؛ پس هر بخش را یک‌جا تمام کنید.');
        li('پیش از هر بخش می‌توانید با چند پرسش نمونه، بدون نمره، تمرین کنید.');
        if (power.length) {
            li('با انتخاب یک گزینه، پاسخ ثبت می‌شود و پرسش بعدی می‌آید. با «پرسش قبلی» برمی‌گردید و می‌توانید پاسخ را عوض کنید؛ با «رد شدن» از پرسشی می‌گذرید و بعد برمی‌گردید.');
            li('پرسش بی‌پاسخ نادرست حساب می‌شود؛ اگر مطمئن نیستید، بهترین حدس خود را بزنید.');
        }
        if (blocks.some(function (b) { return b.key === 'arith' || b.key === 'compare'; })) {
            li('در بخش‌های سرعتی، پاسخ نادرست از نمره کم می‌کند.');
        }
        li('جای آرامی انتخاب کنید و اعلان‌های گوشی را خاموش کنید.');
        li('اگر در میانهٔ یک بخش از صفحه یا برنامه بیرون بروید یا صفحه را دوباره باز کنید، این کار ثبت می‌شود و ممکن است سازمان دعوت‌کننده آن را ببیند.');
        if (!(cfg.accom > 1)) { li(accomText()); }
        box.appendChild(ul);
        var row = el('div', 'tst-actions');
        row.appendChild(btn('ادامه به بخش ' + fa(1), 'ts-btn--primary', showIntro));
        box.appendChild(row);
        stage.appendChild(box);
        var h = box.querySelector('.tst-h');
        if (h) { h.setAttribute('tabindex', '-1'); h.focus(); }
    }

    function showIntro() {
        clear();
        if (cfg.current === null || cfg.current === undefined) { location.reload(); return; }
        var b = cfg.blocks[cfg.current];
        var box = el('div', 'ts-card tst-card');
        box.appendChild(progressDots());
        box.appendChild(el('p', 'tst-kicker', 'بخش ' + fa(b.i + 1) + ' از ' + fa(cfg.blocks.length)));
        box.appendChild(el('h2', 'tst-h', b.title));
        box.appendChild(el('p', 'tst-help', b.help));
        var row = el('div', 'tst-actions');
        if (b.started && !b.done) {
            // resume: the block's clock has been running since it started; show what is left, live
            box.appendChild(el('p', 'ts-notice ts-notice--warn', 'این بخش پیش‌تر شروع شده است و زمانش در حال گذر است.'));
            var facts = el('p', 'tst-facts');
            facts.setAttribute('aria-live', 'off');
            var end = (b.remaining !== null && b.remaining !== undefined) ? Date.now() + b.remaining * 1000 : null;
            var done = (!b.speed && b.n) ? fa(b.answered || 0) + ' پرسش از ' + fa(b.n) + ' پاسخ داده شده' : '';
            var paint = function () {
                var parts = [];
                if (end !== null) {
                    var left = (end - Date.now()) / 1000;
                    parts.push(left > 0 ? 'زمان باقی‌مانده: ' + mmss(left) + ' (در حال گذر)' : 'زمان این بخش تمام شده است؛ با «ادامهٔ بخش» پاسخ‌ها ثبت می‌شود.');
                }
                if (done) { parts.push(done); }
                facts.textContent = parts.join(' · ');
                facts.hidden = !parts.length;
            };
            paint();
            if (end !== null) { timerId = setInterval(paint, 1000); }
            box.appendChild(facts);
            row.appendChild(btn('ادامهٔ بخش', 'ts-btn--primary', function () { startBlock(b); }));
        } else {
            var f = [];
            if (b.n && b.key !== 'span') { f.push(fa(b.n) + (b.speed ? ' مورد' : ' پرسش')); }
            if (b.limit) { f.push(dur(b.limit)); } else { f.push('بدون محدودیت زمانی کلی؛ سرعت هر پاسخ ثبت می‌شود'); }
            box.appendChild(el('p', 'tst-facts', f.join(' · ')));
            if (!b.speed) { box.appendChild(el('p', 'tst-note', 'می‌توانید از یک پرسش رد شوید و بعد برگردید؛ پرسش بی‌پاسخ نادرست حساب می‌شود.')); }
            box.appendChild(el('p', 'tst-note', 'اگر در میانهٔ این بخش از صفحه یا برنامه بیرون بروید، ثبت می‌شود.'));
            var tried = !!practised[b.i];
            row.appendChild(btn(tried ? 'تمرین دوباره' : 'تمرین (بدون نمره)', tried ? 'ts-btn--quiet' : 'ts-btn--primary', function () { runPractice(b); }));
            row.appendChild(btn('شروع بخش', tried ? 'ts-btn--primary' : 'ts-btn--outline', function () { startBlock(b); }));
        }
        box.appendChild(row);
        if (b.limit && !b.started) { box.appendChild(el('p', 'ts-hint', 'با زدن «شروع بخش» زمان این بخش آغاز می‌شود و با بستن صفحه متوقف نمی‌شود.')); }
        stage.appendChild(box);
        var h = box.querySelector('.tst-h');
        if (h) { h.setAttribute('tabindex', '-1'); h.focus(); }
    }

    // ------------------------------------------------------------------ practice (keys are known: immediate feedback)
    // Feedback stays on screen until the person moves on (no timeout), so the right answer can be studied.
    function runPractice(b) {
        var items = b.practice.items, keys = b.practice.keys, k = 0;
        function next() {
            if (k >= items.length) {
                practised[b.i] = true;
                clear();
                var box = el('div', 'ts-card tst-card');
                box.appendChild(el('h2', 'tst-h', 'تمرین تمام شد'));
                box.appendChild(el('p', '', b.limit
                    ? 'حالا نوبت بخش اصلی است. با «شروع بخش» زمان ' + dur(b.limit) + ' این بخش شروع می‌شود و دیگر درست یا نادرست بودن پاسخ‌ها نشان داده نمی‌شود.'
                    : 'حالا نوبت بخش اصلی است. در بخش اصلی، درست یا نادرست بودن پاسخ‌ها نشان داده نمی‌شود.'));
                var row = el('div', 'tst-actions');
                row.appendChild(btn('شروع بخش', 'ts-btn--primary', function () { startBlock(b); }));
                row.appendChild(btn('تمرین دوباره', 'ts-btn--quiet', function () { runPractice(b); }));
                box.appendChild(row);
                stage.appendChild(box);
                var h = box.querySelector('.tst-h');
                if (h) { h.setAttribute('tabindex', '-1'); h.focus(); }
                return;
            }
            var it = items[k];
            var key = keys[k];
            clear();
            var wrap = el('div', 'tst-run');
            var kick = el('p', 'tst-kicker', 'تمرین ' + fa(k + 1) + ' از ' + fa(items.length));
            kick.setAttribute('tabindex', '-1');
            wrap.appendChild(kick);
            var fb = el('p', 'tst-feedback');
            fb.setAttribute('aria-live', 'polite');
            renderTrial(wrap, it, function (resp) {
                var ok = it.kind === 'span' ? (resp.v === key) : (resp.c === key);
                var opts = wrap.querySelectorAll('.tst-opt');
                if (ok) {
                    fb.textContent = 'درست است.';
                } else if (it.kind === 'span') {
                    fb.textContent = 'نادرست بود؛ عددها به این ترتیب بودند: ' + fa(key);
                } else {
                    fb.textContent = 'نادرست بود؛ پاسخ درست با علامت ✓ نشان داده شد.';
                }
                fb.className = 'tst-feedback ' + (ok ? 'is-ok' : 'is-bad');
                if (opts.length && it.kind !== 'span' && opts[key]) {
                    opts[key].classList.add('is-key');
                    var mk = el('span', 'tst-keymark', '✓');
                    mk.setAttribute('aria-hidden', 'true');
                    opts[key].appendChild(mk);
                }
                Array.prototype.forEach.call(opts, function (o) { o.disabled = true; });
                var nx = btn(k + 1 < items.length ? 'پرسش بعدی' : 'پایان تمرین', 'ts-btn--primary', function () { k += 1; next(); });
                wrap.appendChild(nx);
                nx.focus();
            }, true);
            wrap.appendChild(fb);
            stage.appendChild(wrap);
            kick.focus();
        }
        next();
    }

    // ------------------------------------------------------------------ live block
    function startBlock(b) {
        clear();
        stage.appendChild(el('p', 'tst-wait', 'در حال آماده‌سازی…'));
        post('start', { i: b.i }).then(function (r) {
            b.started = true;
            focusLost = 0;
            backAt = 0;
            setRunning(true);
            if (b.speed) { runSpeed(b, r); } else { runPower(b, r); }
        }).catch(function (e) { fail(e, function () { startBlock(b); }); });
    }

    function timerBar(wrap, seconds, onEnd) {
        if (!seconds && seconds !== 0) { return; }
        var bar = el('div', 'tst-timerbar');
        var t = el('p', 'tst-timer', '');
        t.setAttribute('role', 'timer');
        var tog = el('button', 'tst-clock', '');
        tog.type = 'button';
        saveLine = el('p', 'tst-save', '');
        saveLine.setAttribute('role', 'status');
        bar.appendChild(t);
        bar.appendChild(tog);
        bar.appendChild(saveLine);
        wrap.insertBefore(bar, wrap.firstChild);
        var end = Date.now() + seconds * 1000, warned = false;
        // the digits can be hidden by anxious takers; the 30-second warning always shows and is announced
        function paint(left) {
            var low = left <= 30;
            t.textContent = (hideClock && !low) ? 'زمان پنهان است' : 'زمان باقی‌مانده ' + mmss(left);
            tog.textContent = hideClock ? 'نمایش زمان' : 'پنهان کردن زمان';
            tog.hidden = low;
        }
        tog.addEventListener('click', function () { hideClock = !hideClock; paint((end - Date.now()) / 1000); });
        function tick() {
            var left = (end - Date.now()) / 1000;
            paint(left);
            if (left <= 30 && !warned) { warned = true; t.classList.add('is-low'); say('۳۰ ثانیه مانده است'); }
            if (left <= 0) { clearInterval(timerId); timerId = null; onEnd(); }
        }
        tick();
        timerId = setInterval(tick, 500);
    }

    function runPower(b, r) {
        var items = r.items, answers = r.answers.slice(), idx = answers.findIndex(function (a) { return a === null || a === undefined; });
        if (idx < 0) { idx = 0; }
        var finished = false, shownAt = now(), moveT = null;
        var wrap = el('div', 'tst-run');
        var body = el('div', 'tst-body');
        var nav = el('div', 'tst-nav');
        stage.appendChild(wrap);
        timerBar(wrap, r.remaining, function () { finish(true); });
        onTimeUp = function () { finish(true); };
        var count = el('p', 'tst-kicker');
        count.setAttribute('tabindex', '-1');
        wrap.appendChild(count);
        wrap.appendChild(body);
        wrap.appendChild(nav);
        function go(to) {
            if (moveT) { clearTimeout(moveT); moveT = null; }
            idx = to;
            draw();
            count.focus();
        }
        function draw() {
            if (moveT) { clearTimeout(moveT); moveT = null; }
            body.innerHTML = '';
            count.textContent = b.title + ' · پرسش ' + fa(idx + 1) + ' از ' + fa(items.length);
            shownAt = now();
            renderTrial(body, items[idx], function (resp) {
                var at = idx;
                answers[at] = resp.c;
                queueAnswer({ i: b.i, idx: at, c: resp.c, rt: Math.round(now() - shownAt) });
                // the choice stays visible for a moment and is announced before the next question appears
                if (at < items.length - 1) {
                    say('انتخاب شد. پرسش ' + fa(at + 2) + ' از ' + fa(items.length));
                    moveT = setTimeout(function () { moveT = null; if (!finished) { go(at + 1); } }, 250);
                } else {
                    say('انتخاب شد. این آخرین پرسش بود؛ برای پایان، «پایان بخش» را بزنید.');
                    moveT = setTimeout(function () { moveT = null; if (!finished) { go(at); } }, 250);
                }
            }, false, answers[idx]);
            nav.innerHTML = '';
            if (idx > 0) { nav.appendChild(btn('پرسش قبلی', 'ts-btn--quiet', function () { go(idx - 1); })); }
            if (idx < items.length - 1) { nav.appendChild(btn('رد شدن', 'ts-btn--quiet', function () { go(idx + 1); })); }
            var left = answers.filter(function (a) { return a === null || a === undefined; }).length;
            nav.appendChild(btn(left ? 'پایان بخش (' + fa(left) + ' بی‌پاسخ)' : 'پایان بخش', 'ts-btn--outline', function () { confirmEnd(left); }));
        }
        function confirmEnd(left) {
            if (!left) { return finish(false); }
            if (nav.querySelector('.tst-confirm')) { return; }
            var box = el('div', 'ts-notice ts-notice--warn tst-confirm');
            box.setAttribute('role', 'alert');
            box.appendChild(el('p', '', fa(left) + ' پرسش بی‌پاسخ مانده است. پرسش بی‌پاسخ نادرست حساب می‌شود.'));
            box.appendChild(btn('برگشت به پرسش‌ها', 'ts-btn--quiet', function () { box.remove(); count.focus(); }));
            box.appendChild(btn('پایان بخش', 'ts-btn--primary', function () { finish(false); }));
            nav.appendChild(box);
        }
        function finish(timeUp) {
            if (finished) { return; }
            finished = true;
            if (moveT) { clearTimeout(moveT); moveT = null; }
            setRunning(false);
            endBlock(b, {}, timeUp);
        }
        draw();
    }

    function runSpeed(b, r) {
        var items = r.items, resp = [], k = 0, t0 = now(), done = false;
        var wrap = el('div', 'tst-run tst-run--speed');
        stage.appendChild(wrap);
        if (r.remaining || r.remaining === 0) { timerBar(wrap, r.remaining, function () { end(); }); }
        var body = el('div', 'tst-body');
        wrap.appendChild(body);
        function end() { if (done) { return; } done = true; setRunning(false); endBlock(b, { responses: resp }, false); }
        if (b.key === 'span') { return runSpan(items, body, resp, end); }
        function nextTrial() {
            if (done) { return; }
            if (k >= items.length) { return end(); }
            body.innerHTML = '';
            var it = items[k];
            var shown = function () {
                var at = now();
                renderTrial(body, it, function (x) {
                    resp.push({ c: x.c, rt: Math.round(now() - at), t: Math.round(now() - t0) });
                    k += 1;
                    nextTrial();
                }, false);
            };
            if (it.wait) {
                body.appendChild(el('p', 'tst-fix', '+'));
                setTimeout(shown, it.wait);
            } else { shown(); }
        }
        nextTrial();
    }

    function runSpan(items, body, resp, end) {
        var k = 0, failsAt = {};
        function trial() {
            if (k >= items.length) { return end(); }
            var it = items[k];
            if (failsAt[it.length - 1] >= 2) { return end(); }           // both trials of the previous length failed
            body.innerHTML = '';
            var show = el('p', 'tst-span-digit', '');
            body.appendChild(show);
            var d = 0;
            var iv = setInterval(function () {
                if (d < it.digits.length) { show.textContent = it.digits[d]; d += 1; }
                else { clearInterval(iv); ask(); }
            }, 1000);
            function ask() {
                body.innerHTML = '';
                var lab = el('label', 'tst-span-label', 'عددها را به همان ترتیب وارد کنید (' + fa(it.length) + ' رقم):');
                var inp = el('input', 'tst-span-input');
                inp.setAttribute('inputmode', 'numeric');
                inp.setAttribute('autocomplete', 'off');
                inp.setAttribute('dir', 'ltr');
                inp.id = 'tst-span-in';
                lab.setAttribute('for', inp.id);
                var at = now();
                var go = btn('ثبت', 'ts-btn--primary', submit);
                inp.addEventListener('keydown', function (e) { if (e.key === 'Enter') { submit(); } });
                body.appendChild(lab);
                body.appendChild(inp);
                body.appendChild(go);
                inp.focus();
                function submit() {
                    var v = inp.value.replace(/[۰-۹]/g, function (c) { return String(FA.indexOf(c)); }).replace(/[^0-9]/g, '');
                    var key = it.digits.map(function (c) { return String(FA.indexOf(c)); }).join('');
                    resp.push({ v: v, rt: Math.round(now() - at) });
                    if (v !== key) { failsAt[it.length] = (failsAt[it.length] || 0) + 1; }
                    k += 1;
                    trial();
                }
            }
        }
        trial();
    }

    // Unsent answers are flushed first (the server still accepts them for a few seconds after the deadline).
    function endBlock(b, extra, timeUp) {
        clear();
        onTimeUp = null;
        stage.appendChild(el('p', 'tst-wait', timeUp ? 'زمان این بخش تمام شد. در حال ثبت…' : 'در حال ثبت…'));
        var data = { i: b.i, focus_lost: focusLost };
        if (extra.responses) { data.responses = extra.responses; }
        flush(timeUp ? 5000 : 12000).then(function () { return post('finish', data); }).then(function (r) {
            b.done = true;
            if (r.url) { window.location.href = r.url; return; }
            cfg.current = r.next;
            showIntro();
        }).catch(function (e) { fail(e, function () { endBlock(b, extra, timeUp); }); });
    }

    // ------------------------------------------------------------------ one trial of any kind
    function choiceButtons(wrap, labels, onPick, selected, html) {
        var g = el('div', 'tst-opts' + (html ? ' tst-opts--fig' : ''));
        var picked = false;                       // one pick per drawing (a second quick tap changes nothing)
        g.setAttribute('role', 'group');
        labels.forEach(function (lab, n) {
            var b = el('button', 'tst-opt' + (selected === n ? ' is-chosen' : ''));
            b.type = 'button';
            b.setAttribute('aria-pressed', selected === n ? 'true' : 'false');
            if (html) { b.appendChild(svg(lab)); b.setAttribute('aria-label', 'گزینهٔ ' + fa(n + 1)); }
            else { b.textContent = lab; }
            b.addEventListener('click', function () {
                if (picked) { return; }
                picked = true;
                Array.prototype.forEach.call(g.querySelectorAll('.tst-opt'), function (o) { o.classList.remove('is-chosen'); o.setAttribute('aria-pressed', 'false'); });
                b.classList.add('is-chosen');
                b.setAttribute('aria-pressed', 'true');
                onPick({ c: n });
            });
            g.appendChild(b);
        });
        wrap.appendChild(g);
        return g;
    }

    function renderTrial(wrap, it, onAnswer, practice, selected) {
        var once = false;
        function answer(x) { if (once) { return; } once = true; if (keyHandler) { document.removeEventListener('keydown', keyHandler); keyHandler = null; } onAnswer(x); }
        if (it.kind === 'matrix') {
            var grid = el('div', 'tst-matrix');
            grid.setAttribute('dir', 'ltr');
            it.cells.forEach(function (c) { grid.appendChild(svg(c)); });
            grid.appendChild(el('span', 'tst-matrix__q', '؟'));
            wrap.appendChild(grid);
            choiceButtons(wrap, it.options, answer, selected, true);
        } else if (it.kind === 'series') {
            var s = el('p', 'tst-series');
            s.textContent = it.terms.join('،  ') + '،  ؟';
            wrap.appendChild(s);
            choiceButtons(wrap, it.options, answer, selected);
        } else if (it.kind === 'logic' || it.kind === 'numeric') {
            wrap.appendChild(el('p', 'tst-stem', it.stem));
            if (it.question) { wrap.appendChild(el('p', 'tst-q', it.question)); }
            choiceButtons(wrap, it.options, answer, selected);
        } else if (it.kind === 'rotation') {
            var pair = el('div', 'tst-pair');
            pair.appendChild(svg(it.left));
            pair.appendChild(svg(it.right));
            wrap.appendChild(pair);
            choiceButtons(wrap, it.options, answer, selected);
        } else if (it.kind === 'arith') {
            var st = el('p', 'tst-big');
            st.setAttribute('dir', 'ltr');
            st.textContent = it.stem + ' = ?';
            wrap.appendChild(st);
            choiceButtons(wrap, it.options, answer, null);
            keyHandler = function (e) { var m = { Digit1: 0, Digit2: 1, Digit3: 2, Digit4: 3, Numpad1: 0, Numpad2: 1, Numpad3: 2, Numpad4: 3 }[e.code]; if (m !== undefined && m < it.options.length) { e.preventDefault(); answer({ c: m }); } };
            document.addEventListener('keydown', keyHandler);
        } else if (it.kind === 'compare') {
            var pr = el('div', 'tst-cmp');
            pr.appendChild(el('span', 'tst-cmp__s', it.a));
            pr.appendChild(el('span', 'tst-cmp__s', it.b));
            wrap.appendChild(pr);
            choiceButtons(wrap, ['یکسان (F)', 'متفاوت (J)'], answer, null);
            keyHandler = function (e) { if (e.code === 'KeyF') { e.preventDefault(); answer({ c: 0 }); } else if (e.code === 'KeyJ') { e.preventDefault(); answer({ c: 1 }); } };
            document.addEventListener('keydown', keyHandler);
        } else if (it.kind === 'flanker' || it.kind === 'choice_rt') {
            if (it.kind === 'flanker') {
                var f = el('p', 'tst-flank', it.stim);
                f.setAttribute('dir', 'ltr');
                wrap.appendChild(f);
            } else {
                var field = el('div', 'tst-rt');
                field.setAttribute('dir', 'ltr');
                var dot = el('span', 'tst-rt__dot');
                dot.style.marginInlineStart = it.side ? 'auto' : '0';
                field.appendChild(dot);
                wrap.appendChild(field);
            }
            var g = el('div', 'tst-opts tst-opts--lr');
            g.setAttribute('dir', 'ltr');
            [['← چپ', 0], ['راست →', 1]].forEach(function (p) {
                var bb = el('button', 'tst-opt', p[0]);
                bb.type = 'button';
                bb.addEventListener('click', function () { answer({ c: p[1] }); });
                g.appendChild(bb);
            });
            wrap.appendChild(g);
            keyHandler = function (e) { if (e.code === 'ArrowLeft') { e.preventDefault(); answer({ c: 0 }); } else if (e.code === 'ArrowRight') { e.preventDefault(); answer({ c: 1 }); } };
            document.addEventListener('keydown', keyHandler);
        } else if (it.kind === 'span') {
            // practice only (the live span runs in runSpan)
            var show = el('p', 'tst-span-digit', '');
            wrap.appendChild(show);
            var d = 0;
            var iv = setInterval(function () {
                if (d < it.digits.length) { show.textContent = it.digits[d]; d += 1; return; }
                clearInterval(iv);
                show.remove();
                var inp = el('input', 'tst-span-input');
                inp.setAttribute('inputmode', 'numeric');
                inp.setAttribute('dir', 'ltr');
                inp.setAttribute('aria-label', 'عددها را وارد کنید');
                wrap.insertBefore(inp, wrap.lastChild);
                var go = btn('ثبت', 'ts-btn--primary', function () {
                    go.disabled = true;
                    answer({ v: inp.value.replace(/[۰-۹]/g, function (c) { return String(FA.indexOf(c)); }).replace(/[^0-9]/g, '') });
                });
                wrap.insertBefore(go, wrap.lastChild);
                inp.focus();
            }, 1000);
        }
    }

    function fail(e, retry) {
        clear();
        var box = el('div', 'ts-notice ts-notice--warn');
        box.setAttribute('role', 'alert');
        box.appendChild(el('p', '', (e && e.error) || 'اینترنت قطع شد یا سرور پاسخ نداد. صفحه را دوباره باز کنید؛ پاسخ‌های ثبت‌شده محفوظ است، اما زمان این بخش همچنان می‌گذرد.'));
        var row = el('div', 'tst-actions');
        if (retry && !(e && e.error)) { row.appendChild(btn('دوباره تلاش کن', 'ts-btn--primary', retry)); }
        row.appendChild(btn('بارگذاری دوباره', 'ts-btn--outline', function () { location.reload(); }));
        box.appendChild(row);
        stage.appendChild(box);
    }

    showDeviceCheck();
    }
}());
