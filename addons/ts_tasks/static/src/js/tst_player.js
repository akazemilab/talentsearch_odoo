/** @odoo-module ignore **/
// Timed task player (docs/hr/01_architecture.md section 4). One block at a time: intro -> optional practice with
// feedback -> timed run. Answers of power blocks are saved one by one; speed blocks post all trials at the end.
// The server keeps the keys and the deadline; this script only shows items and measures response times.
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
    function now() { return (window.performance && performance.now) ? performance.now() : Date.now(); }

    var root = document.querySelector('.tst-player');
    if (!root) { return; }
    var token = root.getAttribute('data-token');
    var csrf = root.getAttribute('data-csrf');
    var cfg = JSON.parse(root.getAttribute('data-config'));
    var stage = root.querySelector('.tst-stage');
    var live = root.querySelector('.tst-live');
    var focusLost = 0, running = false, timerId = null, keyHandler = null;

    document.addEventListener('visibilitychange', function () { if (running && document.hidden) { focusLost += 1; } });
    window.addEventListener('blur', function () { if (running) { focusLost += 1; } });

    function post(path, data) {
        var body = new FormData();
        body.append('csrf_token', csrf);
        Object.keys(data || {}).forEach(function (k) { body.append(k, typeof data[k] === 'object' ? JSON.stringify(data[k]) : data[k]); });
        return fetch('/take/' + token + '/task/' + path, { method: 'POST', body: body, credentials: 'same-origin' })
            .then(function (r) { return r.json().then(function (j) { if (!r.ok || j.ok === false) { throw j; } return j; }); });
    }
    function say(t) { if (live) { live.textContent = t; } }
    function clear() {
        stage.innerHTML = '';
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
            var li = el('li', 'tst-dots__i' + (b.done ? ' is-done' : '') + (b.i === cfg.current ? ' is-current' : ''), b.title);
            ol.appendChild(li);
        });
        return ol;
    }

    // ------------------------------------------------------------------ start screens
    function showDeviceCheck() {
        var touch = window.matchMedia && window.matchMedia('(pointer: coarse)').matches;
        if (!cfg.desktop || !touch || window.innerWidth >= 900) { return showIntro(); }
        clear();
        var box = el('div', 'ts-card tst-card');
        box.appendChild(el('h2', 'tst-h', 'این آزمون را بهتر است با رایانه انجام دهید'));
        box.appendChild(el('p', '', 'بخش‌های سرعت با صفحه‌کلید دقیق‌تر سنجیده می‌شوند. اگر رایانه در دسترس ندارید، با دکمه‌های روی صفحه هم می‌توانید پاسخ دهید.'));
        var row = el('div', 'tst-actions');
        row.appendChild(btn('ادامه با همین دستگاه', 'ts-btn--outline', showIntro));
        var later = el('a', 'ts-btn ts-btn--quiet', 'بعداً با رایانه');
        later.href = '/my/assessments';
        row.appendChild(later);
        box.appendChild(row);
        stage.appendChild(box);
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
        var facts = [];
        if (b.n && b.key !== 'span') { facts.push(fa(b.n) + (b.speed ? ' مورد' : ' پرسش')); }
        if (b.limit) { facts.push('زمان: ' + mmss(b.limit) + ' دقیقه'); } else { facts.push('بدون محدودیت زمانی کلی؛ سرعت هر پاسخ ثبت می‌شود'); }
        box.appendChild(el('p', 'tst-facts', facts.join(' · ')));
        if (b.started && !b.done) {
            box.appendChild(el('p', 'ts-notice ts-notice--warn', 'این بخش پیش‌تر شروع شده است؛ با ادامه، زمان باقی‌مانده را دارید.'));
        }
        var row = el('div', 'tst-actions');
        if (!b.started) { row.appendChild(btn('تمرین (بدون نمره)', 'ts-btn--outline', function () { runPractice(b); })); }
        row.appendChild(btn(b.started ? 'ادامهٔ بخش' : 'شروع بخش', 'ts-btn--primary', function () { startBlock(b); }));
        box.appendChild(row);
        if (b.limit && !b.started) { box.appendChild(el('p', 'ts-hint', 'با زدن «شروع بخش» زمان این بخش آغاز می‌شود و با بستن صفحه متوقف نمی‌شود.')); }
        stage.appendChild(box);
        var h = box.querySelector('.tst-h');
        if (h) { h.setAttribute('tabindex', '-1'); h.focus(); }
    }

    // ------------------------------------------------------------------ practice (keys are known: immediate feedback)
    function runPractice(b) {
        var items = b.practice.items, keys = b.practice.keys, k = 0;
        function next() {
            if (k >= items.length) {
                clear();
                var box = el('div', 'ts-card tst-card');
                box.appendChild(el('h2', 'tst-h', 'تمرین تمام شد'));
                box.appendChild(el('p', '', 'اکنون بخش اصلی را شروع کنید. در بخش اصلی درستی پاسخ‌ها نشان داده نمی‌شود.'));
                var row = el('div', 'tst-actions');
                row.appendChild(btn('شروع بخش', 'ts-btn--primary', function () { startBlock(b); }));
                row.appendChild(btn('تمرین دوباره', 'ts-btn--quiet', function () { runPractice(b); }));
                box.appendChild(row);
                stage.appendChild(box);
                return;
            }
            var it = items[k];
            var key = keys[k];
            clear();
            var wrap = el('div', 'tst-run');
            wrap.appendChild(el('p', 'tst-kicker', 'تمرین ' + fa(k + 1) + ' از ' + fa(items.length)));
            var fb = el('p', 'tst-feedback');
            fb.setAttribute('aria-live', 'polite');
            renderTrial(wrap, it, function (resp) {
                var ok = it.kind === 'span' ? (resp.v === key) : (resp.c === key);
                fb.textContent = ok ? 'درست است.' : 'نادرست بود؛ پاسخ درست نشان داده شد.';
                fb.className = 'tst-feedback ' + (ok ? 'is-ok' : 'is-bad');
                var opts = wrap.querySelectorAll('.tst-opt');
                if (opts.length && it.kind !== 'span') { opts[key].classList.add('is-key'); }
                setTimeout(function () { k += 1; next(); }, ok ? 700 : 1800);
            }, true);
            wrap.appendChild(fb);
            stage.appendChild(wrap);
        }
        next();
    }

    // ------------------------------------------------------------------ live block
    function startBlock(b) {
        clear();
        stage.appendChild(el('p', 'tst-wait', 'در حال آماده‌سازی…'));
        post('start', { i: b.i }).then(function (r) {
            b.started = true;
            running = true;
            focusLost = 0;
            if (b.speed) { runSpeed(b, r); } else { runPower(b, r); }
        }).catch(function (e) { fail(e); });
    }

    function timerBar(wrap, seconds, onEnd) {
        if (!seconds && seconds !== 0) { return; }
        var t = el('p', 'tst-timer', '');
        t.setAttribute('role', 'timer');
        wrap.insertBefore(t, wrap.firstChild);
        var end = Date.now() + seconds * 1000, warned = false;
        function tick() {
            var left = (end - Date.now()) / 1000;
            t.textContent = 'زمان باقی‌مانده ' + mmss(left);
            if (left <= 30 && !warned) { warned = true; t.classList.add('is-low'); say('سی ثانیه باقی مانده است'); }
            if (left <= 0) { clearInterval(timerId); timerId = null; onEnd(); }
        }
        tick();
        timerId = setInterval(tick, 500);
    }

    function runPower(b, r) {
        var items = r.items, answers = r.answers.slice(), idx = answers.findIndex(function (a) { return a === null || a === undefined; });
        if (idx < 0) { idx = 0; }
        var finished = false, shownAt = now();
        var wrap = el('div', 'tst-run');
        var body = el('div', 'tst-body');
        var nav = el('div', 'tst-nav');
        stage.appendChild(wrap);
        timerBar(wrap, r.remaining, function () { finish(true); });
        var count = el('p', 'tst-kicker');
        wrap.appendChild(count);
        wrap.appendChild(body);
        wrap.appendChild(nav);
        function draw() {
            body.innerHTML = '';
            count.textContent = b.title + ' · پرسش ' + fa(idx + 1) + ' از ' + fa(items.length);
            shownAt = now();
            renderTrial(body, items[idx], function (resp) {
                answers[idx] = resp.c;
                var rt = Math.round(now() - shownAt);
                post('answer', { i: b.i, idx: idx, c: resp.c, rt: rt }).catch(function (e) {
                    if (e && e.reason === 'time') { finish(true); }
                });
                if (idx < items.length - 1) { idx += 1; draw(); } else { draw(); }
            }, false, answers[idx]);
            nav.innerHTML = '';
            if (idx > 0) { nav.appendChild(btn('پرسش قبلی', 'ts-btn--quiet', function () { idx -= 1; draw(); })); }
            if (idx < items.length - 1) { nav.appendChild(btn('رد شدن', 'ts-btn--quiet', function () { idx += 1; draw(); })); }
            var left = answers.filter(function (a) { return a === null || a === undefined; }).length;
            nav.appendChild(btn(left ? 'پایان بخش (' + fa(left) + ' بی‌پاسخ)' : 'پایان بخش', 'ts-btn--outline', function () { confirmEnd(left); }));
        }
        function confirmEnd(left) {
            if (!left) { return finish(false); }
            var box = el('div', 'ts-notice ts-notice--warn tst-confirm');
            box.appendChild(el('p', '', fa(left) + ' پرسش بی‌پاسخ مانده است. پرسش بی‌پاسخ نادرست حساب می‌شود.'));
            box.appendChild(btn('برگشت به پرسش‌ها', 'ts-btn--quiet', function () { box.remove(); }));
            box.appendChild(btn('پایان بخش', 'ts-btn--primary', function () { finish(false); }));
            nav.appendChild(box);
        }
        function finish(timeUp) {
            if (finished) { return; }
            finished = true;
            running = false;
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
        function end() { if (done) { return; } done = true; running = false; endBlock(b, { responses: resp }, false); }
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

    function endBlock(b, extra, timeUp) {
        clear();
        stage.appendChild(el('p', 'tst-wait', timeUp ? 'زمان این بخش تمام شد. در حال ثبت…' : 'در حال ثبت…'));
        var data = { i: b.i, focus_lost: focusLost };
        if (extra.responses) { data.responses = extra.responses; }
        post('finish', data).then(function (r) {
            b.done = true;
            if (r.url) { window.location.href = r.url; return; }
            cfg.current = r.next;
            showIntro();
        }).catch(function (e) { fail(e); });
    }

    // ------------------------------------------------------------------ one trial of any kind
    function choiceButtons(wrap, labels, onPick, selected, html) {
        var g = el('div', 'tst-opts' + (html ? ' tst-opts--fig' : ''));
        g.setAttribute('role', 'group');
        labels.forEach(function (lab, n) {
            var b = el('button', 'tst-opt' + (selected === n ? ' is-chosen' : ''));
            b.type = 'button';
            if (html) { b.appendChild(svg(lab)); b.setAttribute('aria-label', 'گزینهٔ ' + fa(n + 1)); }
            else { b.textContent = lab; }
            b.addEventListener('click', function () { onPick({ c: n }); });
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
                    answer({ v: inp.value.replace(/[۰-۹]/g, function (c) { return String(FA.indexOf(c)); }).replace(/[^0-9]/g, '') });
                });
                wrap.insertBefore(go, wrap.lastChild);
                inp.focus();
            }, 1000);
        }
    }

    function fail(e) {
        clear();
        var box = el('div', 'ts-notice ts-notice--warn');
        box.appendChild(el('p', '', (e && e.error) || 'ارتباط با سرور برقرار نشد. صفحه را دوباره باز کنید؛ پاسخ‌های ثبت‌شده محفوظ است.'));
        box.appendChild(btn('بارگذاری دوباره', 'ts-btn--outline', function () { location.reload(); }));
        stage.appendChild(box);
    }

    showDeviceCheck();
    }
}());
