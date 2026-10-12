/** @odoo-module ignore **/
// Clinic phase 6: «راه‌اندازی مرکز» on a phone. The list of steps folds behind a button (aria-expanded) on narrow screens and
// is always open on wide ones. Without this file the list is simply open and the button stays hidden.
(function () {
    'use strict';

    function init() {
        var mq = window.matchMedia ? window.matchMedia('(max-width: 767.98px)') : null;
        document.querySelectorAll('[data-tsob-toggle]').forEach(function (btn) {
            var list = document.getElementById(btn.getAttribute('aria-controls'));
            if (!list) { return; }
            function set(open) {
                list.hidden = !open;
                btn.setAttribute('aria-expanded', open ? 'true' : 'false');
            }
            btn.hidden = false;
            set(!(mq && mq.matches));
            btn.addEventListener('click', function () { set(list.hidden); });
            if (mq) {
                var onChange = function (e) { if (!e.matches) { set(true); } };
                if (mq.addEventListener) { mq.addEventListener('change', onChange); } else if (mq.addListener) { mq.addListener(onChange); }
            }
        });
    }

    if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', init); } else { init(); }
})();
