/** @odoo-module ignore **/
// Clinic phase 5: live preview of the report header on the panel settings page (name, contact line, colour, the logo file
// just chosen), the character count of the SMS name and the colour swatch beside the #rrggbb field; on the member page, the
// title in the counselor preview. The forms work without this file (the server validates everything).
(function () {
    'use strict';

    function settings() {
        var form = document.querySelector('form[data-tsbr-form]');
        var preview = document.querySelector('[data-tsbr-preview]');
        if (!form || !preview) { return; }
        var head = preview.querySelector('[data-tsbr-head]');
        var fallbackName = preview.getAttribute('data-tsbr-default') || '';
        var hex = /^#[0-9a-fA-F]{6}$/;

        function out(key) { return preview.querySelector('[data-tsbr-out="' + key + '"]'); }

        form.querySelectorAll('[data-tsbr-bind]').forEach(function (input) {
            var key = input.getAttribute('data-tsbr-bind');
            function sync() {
                var v = (input.value || '').trim();
                if (key === 'name') {
                    var n = out('name');
                    if (n) { n.textContent = v || fallbackName; }
                } else if (key === 'contact') {
                    var c = out('contact');
                    if (c) {
                        c.textContent = v;
                        c.setAttribute('dir', /[\u0600-\u06ff]/.test(v.replace(/[\u06f0-\u06f9]/g, '')) ? 'rtl' : 'ltr');
                        if (c.parentNode) { c.parentNode.hidden = !v; }
                    }
                } else if (key === 'color' && head) {
                    if (hex.test(v)) { head.style.setProperty('--tsbr-color', v); } else if (!v) { head.style.removeProperty('--tsbr-color'); }
                }
            }
            input.addEventListener('input', sync);
        });

        // the logo file just chosen, shown in the preview before it is saved (never uploaded by this script)
        var logoIn = form.querySelector('input[type="file"][name="logo"]');
        var logoImg = out('logo');
        var logoEmpty = out('logo-empty');
        var logoRm = form.querySelector('[data-tsbr-logo-rm]');
        var savedSrc = logoImg ? logoImg.getAttribute('src') : null;
        var objUrl = null;
        function showLogo(src) {
            if (!logoImg) { return; }
            if (src) { logoImg.src = src; } else { logoImg.removeAttribute('src'); }
            logoImg.hidden = !src;
            if (logoEmpty) { logoEmpty.hidden = !!src; }
        }
        function syncLogo() {
            var f = logoIn && logoIn.files && logoIn.files[0];
            if (objUrl) { URL.revokeObjectURL(objUrl); objUrl = null; }
            if (f && /^image\//.test(f.type) && window.URL && URL.createObjectURL) {
                objUrl = URL.createObjectURL(f);
                showLogo(objUrl);
            } else {
                showLogo(logoRm && logoRm.checked ? null : savedSrc);
            }
        }
        if (logoIn) { logoIn.addEventListener('change', syncLogo); }
        if (logoRm) { logoRm.addEventListener('change', syncLogo); }

        var wrap = form.querySelector('[data-tsbr-pickwrap]');
        var pick = form.querySelector('[data-tsbr-pick]');
        var colorText = form.querySelector('[data-tsbr-bind="color"]');
        if (wrap && pick && colorText) {
            wrap.hidden = false;
            pick.addEventListener('input', function () {
                colorText.value = pick.value;
                colorText.dispatchEvent(new Event('input', {bubbles: true}));
            });
            colorText.addEventListener('input', function () {
                if (hex.test(colorText.value.trim())) { pick.value = colorText.value.trim().toLowerCase(); }
            });
        }

        form.querySelectorAll('[data-tsbr-count]').forEach(function (input) {
            var max = parseInt(input.getAttribute('data-tsbr-count'), 10) || 0;
            var line = document.getElementById(input.id + '_n');
            if (!line || !max) { return; }
            var fa = '۰۱۲۳۴۵۶۷۸۹';
            function faNum(n) { return String(n).replace(/[0-9]/g, function (d) { return fa[+d]; }); }
            function count() {
                var len = (input.value || '').length;
                line.textContent = len ? faNum(len) + ' از ' + faNum(max) + ' نویسه' : '';
            }
            input.addEventListener('input', count);
            count();
        });
    }

    function member() {
        var form = document.querySelector('form[data-tsbr-mform]');
        var prev = document.querySelector('[data-tsbr-mprev]');
        if (!form || !prev) { return; }
        var title = form.querySelector('[data-tsbr-mbind="title"]');
        var outTitle = prev.querySelector('[data-tsbr-mout="title"]');
        if (title && outTitle) {
            title.addEventListener('input', function () {
                var v = (title.value || '').trim();
                outTitle.textContent = v;
                outTitle.hidden = !v;
            });
        }
    }

    function init() { settings(); member(); }

    if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', init); } else { init(); }
})();

/* Print mode for participant report pages (fallback of the PDF download when the server has no PDF engine):
   /my/assessments/<id>?print=1 and /my/assessments/battery/<id>?print=1 open the browser print dialog once.
   Panel pages already do this through data-tsp-autoprint (ts_panel/static/src/js/panel.js). */
(function () {
    'use strict';
    function go() {
        if (!/^\/my\/assessments\//.test(location.pathname) || !/[?&]print=1/.test(location.search)) { return; }
        if (document.querySelector('[data-tsp-autoprint]')) { return; }
        setTimeout(function () { window.print(); }, 300);
    }
    if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', go); } else { go(); }
})();
