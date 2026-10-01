/** @odoo-module ignore **/
// Panel v2 enhancements. Pages work without JavaScript; this file only adds comfort.
(function () {
    'use strict';

    function initMenus() {
        document.querySelectorAll('.tsp-nav').forEach(function (nav) {
            var btn = nav.querySelector('.tsp-nav__toggle');
            var list = nav.querySelector('.tsp-nav__list');
            if (!btn || !list) { return; }
            nav.setAttribute('data-js', '1');
            list.hidden = true;
            btn.addEventListener('click', function () {
                var open = btn.getAttribute('aria-expanded') === 'true';
                btn.setAttribute('aria-expanded', open ? 'false' : 'true');
                list.hidden = open;
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

    function init() { initMenus(); initOnce(); initSelect(); initCopy(); initAutoPrint(); }
    if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', init); } else { init(); }
})();
