// Talent Search mobile menu: a disclosure button (aria-expanded) controlling
// the panel. Loaded only on website 2 via ts_website.assets_ts_js.
(function () {
    'use strict';
    function setOpen(btn, open) {
        var panel = document.getElementById(btn.getAttribute('aria-controls'));
        if (!panel) { return; }
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
        panel.hidden = !open;
    }
    document.addEventListener('click', function (ev) {
        var btn = ev.target.closest && ev.target.closest('.ts-nav__toggle');
        if (btn) {
            setOpen(btn, btn.getAttribute('aria-expanded') !== 'true');
            return;
        }
        document.querySelectorAll('.ts-nav__toggle[aria-expanded="true"]').forEach(function (b) {
            var panel = document.getElementById(b.getAttribute('aria-controls'));
            if (panel && !panel.contains(ev.target)) { setOpen(b, false); }
        });
    });
    document.addEventListener('keydown', function (ev) {
        if (ev.key !== 'Escape') { return; }
        document.querySelectorAll('.ts-nav__toggle[aria-expanded="true"]').forEach(function (b) {
            setOpen(b, false);
            b.focus();
        });
    });
})();
