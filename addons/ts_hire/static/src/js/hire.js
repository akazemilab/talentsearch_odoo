/** @odoo-module ignore **/
// HR positions: at most three «کلیدی» requirements, a requirement is either critical or dropped, and compare 2-3.
(function () {
    'use strict';
    if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', main); } else { main(); }
    function main() {
    var FA = '۰۱۲۳۴۵۶۷۸۹';
    function fa(n) { return String(n).replace(/[0-9]/g, function (d) { return FA[+d]; }); }

    var prof = document.querySelector('.tsh-profile');
    if (prof) {
        var max = +(prof.getAttribute('data-tsh-critical-max') || 3);
        var live = prof.querySelector('.tsh-live');
        var sync = function () {
            var crit = prof.querySelectorAll('input[name="critical"]');
            var n = Array.prototype.filter.call(crit, function (c) { return c.checked; }).length;
            Array.prototype.forEach.call(crit, function (c) {
                var row = c.closest('tr');
                var drop = row && row.querySelector('input[name="dropped"]');
                if (drop && c.checked) { drop.checked = false; }
                if (!c.checked) { c.disabled = n >= max || (drop && drop.checked) || c.hasAttribute('data-ro'); }
                else { c.disabled = false; }
            });
            if (live) { live.textContent = n >= max ? 'حداکثر ' + fa(max) + ' نیاز کلیدی انتخاب شده است.' : ''; }
        };
        prof.addEventListener('change', function (ev) {
            var t = ev.target;
            if (t.name === 'dropped' && t.checked) {
                var row = t.closest('tr');
                var c = row && row.querySelector('input[name="critical"]');
                if (c) { c.checked = false; }
            }
            sync();
        });
        prof.querySelectorAll('input[disabled]').forEach(function (i) { i.setAttribute('data-ro', '1'); });
        sync();
    }

    var cmp = document.querySelector('.tsh-compare-form');
    if (cmp) {
        var btn = cmp.querySelector('.tsh-compare-btn');
        var upd = function () {
            var boxes = cmp.querySelectorAll('.tsh-cmp');
            var n = Array.prototype.filter.call(boxes, function (b) { return b.checked; }).length;
            Array.prototype.forEach.call(boxes, function (b) { if (!b.checked) { b.disabled = n >= 3; } });
            if (btn) { btn.disabled = n < 2; }
        };
        cmp.addEventListener('change', upd);
        upd();
    }
    }
}());
