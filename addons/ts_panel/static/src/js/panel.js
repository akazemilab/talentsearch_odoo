/** @odoo-module ignore **/
// Panel v2 enhancements. Pages work without JavaScript; this file only adds comfort.
(function () {
    'use strict';

    // The panel menu: a rail on wide screens; on narrow ones a drawer opened by the top bar and the tab bar.
    function initMenus() {
        var shell = document.getElementById('tsp-shell');
        var rail = document.getElementById('tsp-rail');
        if (!shell || !rail) { return; }
        var scrim = shell.querySelector('.tsp-scrim');
        var openers = document.querySelectorAll('[data-tsp-open]');
        var lastOpener = null;
        shell.setAttribute('data-js', '1');
        function setOpen(open, opener) {
            if (open) { shell.setAttribute('data-open', '1'); } else { shell.removeAttribute('data-open'); }
            if (scrim) { scrim.hidden = !open; }
            openers.forEach(function (b) { b.setAttribute('aria-expanded', open ? 'true' : 'false'); });
            document.documentElement.style.overflow = open ? 'hidden' : '';
            if (open) {
                lastOpener = opener || lastOpener;
                var first = rail.querySelector('a, button');
                if (first) { first.focus(); }
            } else if (lastOpener) {
                lastOpener.focus();
            }
        }
        openers.forEach(function (b) { b.addEventListener('click', function () { setOpen(!shell.hasAttribute('data-open'), b); }); });
        document.querySelectorAll('[data-tsp-close]').forEach(function (b) { b.addEventListener('click', function () { setOpen(false); }); });
        document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape' && shell.hasAttribute('data-open')) { setOpen(false); } });
        var mq = window.matchMedia('(min-width: 1024px)');
        var onChange = function () { if (mq.matches && shell.hasAttribute('data-open')) { setOpen(false); } };
        if (mq.addEventListener) { mq.addEventListener('change', onChange); } else if (mq.addListener) { mq.addListener(onChange); }
    }

    // A card marked data-tsp-collapse opens on demand; without JavaScript it is simply visible.
    function initCollapse() {
        document.querySelectorAll('[data-tsp-collapse]').forEach(function (card) {
            var h = card.querySelector('h2');
            if (!h) { return; }
            var btn = document.createElement('button');
            btn.type = 'button'; btn.className = 'tsp-collapse__btn'; btn.setAttribute('aria-expanded', 'false');
            btn.textContent = h.textContent;
            h.textContent = ''; h.appendChild(btn);
            card.setAttribute('data-js', '1');
            btn.addEventListener('click', function () {
                var open = card.hasAttribute('data-open');
                if (open) { card.removeAttribute('data-open'); } else { card.setAttribute('data-open', '1'); }
                btn.setAttribute('aria-expanded', open ? 'false' : 'true');
            });
        });
    }

    // A form marked data-tsp-once cannot be sent twice: the button says what is happening.
    function initOnce() {
        document.querySelectorAll('form[data-tsp-once]').forEach(function (form) {
            form.addEventListener('submit', function () {
                var btn = form.querySelector('button[type=submit]');
                if (btn && !btn.disabled) {
                    btn.setAttribute('aria-disabled', 'true');
                    btn.textContent = 'در حال انجام…';
                    setTimeout(function () { btn.disabled = true; }, 0);
                }
            });
        });
    }

    // List selection: the header box selects the page; the count is announced politely (works without it too).
    function initSelect() {
        var all = document.querySelector('[data-tsp-selectall]');
        var out = document.querySelector('[data-tsp-count]');
        var boxes = Array.prototype.slice.call(document.querySelectorAll('input[name=sel]'));
        if (!boxes.length) { return; }
        function count() {
            var n = boxes.filter(function (b) { return b.checked; }).length;
            if (out) { out.textContent = n ? ' · ' + n.toLocaleString('fa-IR') + ' انتخاب‌شده' : ''; }
        }
        if (all) {
            all.addEventListener('change', function () {
                boxes.forEach(function (b) { b.checked = all.checked; });
                count();
            });
        }
        boxes.forEach(function (b) { b.addEventListener('change', count); });
    }

    // Copy button: shown only when the browser can copy; the field stays selectable without it.
    function initCopy() {
        document.querySelectorAll('[data-tsp-copy]').forEach(function (btn) {
            var field = document.getElementById(btn.getAttribute('data-tsp-copy'));
            var note = btn.parentNode.querySelector('[data-tsp-copied]');
            if (!field) { return; }
            field.addEventListener('focus', function () { field.select(); });
            btn.hidden = false;
            btn.addEventListener('click', function () {
                function done(ok) { if (note) { note.textContent = ok ? 'پیوند رونوشت شد.' : 'رونوشت نشد؛ پیوند را انتخاب و کپی کنید.'; } }
                field.select();
                if (navigator.clipboard && window.isSecureContext) {
                    navigator.clipboard.writeText(field.value).then(function () { done(true); }, function () { done(false); });
                } else {
                    try { done(document.execCommand('copy')); } catch (e) { done(false); }
                }
            });
        });
    }

    // After a logged print click the server sends the page back with ?print=1: open the print dialog once.
    function initAutoPrint() {
        if (document.querySelector('[data-tsp-autoprint]') && /[?&]print=1/.test(location.search)) {
            if (window.history && history.replaceState) { history.replaceState(null, '', location.pathname); }
            setTimeout(function () { window.print(); }, 300);
        }
    }

    function init() { initMenus(); initCollapse(); initOnce(); initSelect(); initCopy(); initAutoPrint(); }
    if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', init); } else { init(); }
})();
