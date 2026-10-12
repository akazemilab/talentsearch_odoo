/** @odoo-module ignore **/
// Clinic phase 6: «راه‌اندازی مرکز» on a phone (UX audit G8-P1-3). The open steps are always visible; only the done steps and
// «بعداً نشانم نده» fold behind a button (aria-expanded) on narrow screens, so the next action is never hidden behind the hide
// action. On wide screens everything is open. Without this file everything is open and the button stays hidden.
(function () {
    'use strict';

    function init() {
        var mq = window.matchMedia ? window.matchMedia('(max-width: 767.98px)') : null;
        document.querySelectorAll('[data-tsob-toggle]').forEach(function (btn) {
            var more = document.getElementById(btn.getAttribute('aria-controls'));
            if (!more) { return; }
            function set(open) {
                more.hidden = !open;
                btn.setAttribute('aria-expanded', open ? 'true' : 'false');
            }
            btn.hidden = false;
            set(!(mq && mq.matches));
            btn.addEventListener('click', function () { set(more.hidden); });
            if (mq) {
                var onChange = function (e) { set(!e.matches); };
                if (mq.addEventListener) { mq.addEventListener('change', onChange); } else if (mq.addListener) { mq.addListener(onChange); }
            }
        });
    }

    if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', init); } else { init(); }
})();
