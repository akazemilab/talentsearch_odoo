/** @odoo-module ignore **/
// Clinic phase 5: live preview of the report header on the panel settings page, the character count of the SMS name and
// the colour picker beside the #rrggbb field. The form works without this file (the server validates everything).
(function () {
    'use strict';

    function init() {
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
                    if (c) { c.textContent = v; c.hidden = !v; }
                } else if (key === 'color' && head) {
                    if (hex.test(v)) { head.style.setProperty('--tsbr-color', v); } else if (!v) { head.style.removeProperty('--tsbr-color'); }
                }
            }
            input.addEventListener('input', sync);
        });

        var pick = form.querySelector('[data-tsbr-pick]');
        var colorText = form.querySelector('[data-tsbr-bind="color"]');
        if (pick && colorText) {
            pick.hidden = false;
            pick.addEventListener('input', function () {
                colorText.value = pick.value;
                colorText.dispatchEvent(new Event('input'));
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
