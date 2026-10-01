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

    function init() { initMenus(); initOnce(); }
    if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', init); } else { init(); }
})();
