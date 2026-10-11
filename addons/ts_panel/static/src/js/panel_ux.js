/** @odoo-module ignore **/
// Panel UX helpers (UX audit 2026-10-11). Owned by the admin/account area; keep it small and dependency-free.
// Every page works without this file; it only adds comfort.
(function () {
    'use strict';

    function onReady(fn) {
        if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', fn); } else { fn(); }
    }

    // The active item of a horizontally scrolling sub-navigation is scrolled into view (G4 PT11, G2 X1).
    function initSubnav() {
        document.querySelectorAll('[data-tsp-subnav] .is-on').forEach(function (el) {
            var nav = el.parentElement;
            if (nav && nav.scrollWidth > nav.clientWidth + 2) {
                var x = window.scrollX, y = window.scrollY;
                try { el.scrollIntoView({ block: 'nearest', inline: 'center' }); } catch (e) { /* old browsers */ }
                window.scrollTo(x, y);          // only the strip scrolls, never the page
            }
        });
    }

    // «کپی پیوند» next to a read-only link field (members invite link).
    function initCopy() {
        document.querySelectorAll('[data-tsp-copy]').forEach(function (btn) {
            var input = document.getElementById(btn.getAttribute('data-tsp-copy'));
            if (!input) { return; }
            btn.hidden = false;
            var label = btn.textContent;
            btn.addEventListener('click', function () {
                var done = function () {
                    btn.textContent = 'کپی شد';
                    setTimeout(function () { btn.textContent = label; }, 2500);
                };
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(input.value).then(done, function () { input.select(); });
                } else {
                    input.select();
                    try { document.execCommand('copy'); done(); } catch (e) { /* the field stays selected */ }
                }
            });
        });
    }

    // Transfer ownership: the button names the chosen member («انتقال مالکیت به …», G4 P11-3).
    function initTransfer() {
        var form = document.querySelector('form[data-tsp-transfer]');
        if (!form) { return; }
        var btn = form.querySelector('[data-tsp-transfer-btn]');
        if (!btn) { return; }
        var base = btn.textContent;
        function update() {
            var r = form.querySelector('input[name=new_owner]:checked');
            btn.textContent = r && r.getAttribute('data-name') ? base + ' به ' + r.getAttribute('data-name') : base;
        }
        form.addEventListener('change', update);
        update();
    }

    // A filter form behind a «پالایه» button (aria-expanded); open by default when a filter is active (G4 P9-5).
    function initToggle() {
        document.querySelectorAll('[data-tsp-toggle]').forEach(function (btn) {
            var target = document.getElementById(btn.getAttribute('data-tsp-toggle'));
            if (!target) { return; }
            btn.hidden = false;
            var open = btn.hasAttribute('data-tsp-start-open');
            function set(o) {
                target.hidden = !o;
                btn.setAttribute('aria-expanded', o ? 'true' : 'false');
            }
            set(open);
            btn.addEventListener('click', function () { set(target.hidden); if (!target.hidden) { var f = target.querySelector('input, select, button'); if (f) { f.focus(); } } });
        });
    }

    // Segmented radios: keep an .is-on class for browsers without :has().
    function initSegRadio() {
        document.querySelectorAll('.tsp-seg--radio').forEach(function (group) {
            function sync() {
                group.querySelectorAll('.tsp-seg__item').forEach(function (it) {
                    var i = it.querySelector('input');
                    it.classList.toggle('is-on', !!(i && i.checked));
                });
            }
            group.addEventListener('change', sync);
            sync();
        });
    }

    // Job page: while a job is queued or running, its status line is updated in place every 5 s (no meta refresh that
    // reloads the page under a screen reader, G4 P8-1). Stops by itself when the job ends or after 10 minutes.
    function initJobPoll() {
        var box = document.querySelector('[data-tsp-poll]');
        if (!box || !window.fetch || !window.DOMParser) { return; }
        var tries = 0;
        function tick() {
            tries += 1;
            if (tries > 120) { return; }
            fetch(window.location.href, { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } })
                .then(function (r) { return r.ok ? r.text() : null; })
                .then(function (html) {
                    if (!html) { setTimeout(tick, 10000); return; }
                    var doc = new DOMParser().parseFromString(html, 'text/html');
                    var fresh = doc.getElementById('tsp-job-status');
                    var pill = doc.getElementById('tsp-job-pill');
                    var oldPill = document.getElementById('tsp-job-pill');
                    if (pill && oldPill) { oldPill.innerHTML = pill.innerHTML; }
                    if (!fresh) { return; }
                    var still = fresh.hasAttribute('data-tsp-poll');
                    if (!still) {
                        box.innerHTML = fresh.innerHTML;
                        box.removeAttribute('data-tsp-poll');
                        return;
                    }
                    setTimeout(tick, 5000);
                })
                .catch(function () { setTimeout(tick, 10000); });
        }
        setTimeout(tick, 5000);
    }

    onReady(function () {
        initSubnav();
        initCopy();
        initTransfer();
        initToggle();
        initSegRadio();
        initJobPoll();
    });
})();
