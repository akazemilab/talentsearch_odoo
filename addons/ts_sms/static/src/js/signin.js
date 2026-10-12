/** @odoo-module ignore **/
// S-AUTH (onb1): number -> code on one page without a reload. The page works without this file (plain forms and
// redirects); here the same endpoints answer JSON (header X-TS-Auth: 1). Countdown before «ارسال دوباره کد», auto-submit
// at six digits, Persian/Arabic digits and pasted spaces accepted, WebOTP when the browser offers it.
(function () {
    'use strict';
    if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', main); } else { main(); }

    function main() {
        var root = document.getElementById('ts-auth');
        if (!root || !window.fetch || !window.FormData) { return; }
        var FA = '۰۱۲۳۴۵۶۷۸۹';
        var fa = function (s) { return String(s).replace(/[0-9]/g, function (d) { return FA[+d]; }); };
        var latin = function (s) {
            return String(s || '').replace(/[۰-۹]/g, function (d) { return String(d.charCodeAt(0) - 0x06F0); })
                .replace(/[٠-٩]/g, function (d) { return String(d.charCodeAt(0) - 0x0660); });
        };
        var digits = function (s) { return latin(s).replace(/\D/g, ''); };

        var phoneForm = document.getElementById('tsa-phone');
        var codeForm = document.getElementById('tsa-code');
        var resendForm = document.getElementById('tsa-resend');
        var help = document.getElementById('tsa-help');
        var msg = document.getElementById('tsa-msg');
        if (!phoneForm || !codeForm || !resendForm) { return; }
        var phoneIn = phoneForm.querySelector('input[name="phone"]');
        var codeIn = codeForm.querySelector('input[name="code"]');
        var sentNum = codeForm.querySelector('.tsa-sent__num');
        var count = resendForm.querySelector('[data-tsa-count]');
        var resendBtn = resendForm.querySelector('button');
        var helpAfter = +(root.getAttribute('data-tsa-help') || 2);
        var timer = null, otpAbort = null, busy = false;

        function say(text, tone) {
            if (!msg) { return; }
            msg.textContent = text || '';
            msg.className = 'ts-notice' + (tone === 'warn' ? ' ts-notice--warn' : '');
            msg.hidden = !text;
        }
        function invalid(input, on) { if (on) { input.setAttribute('aria-invalid', 'true'); } else { input.removeAttribute('aria-invalid'); } }

        function countdown(sec) {
            clearInterval(timer);
            var left = Math.max(0, +sec || 0);
            var paint = function () {
                if (left > 0) {
                    count.textContent = 'ارسال دوباره تا ' + fa(Math.floor(left / 60) + ':' + ('0' + (left % 60)).slice(-2));
                    count.hidden = false;
                    resendBtn.hidden = true;
                } else {
                    count.hidden = true;
                    resendBtn.hidden = false;
                    clearInterval(timer);
                }
            };
            paint();
            if (left > 0) { timer = setInterval(function () { left -= 1; paint(); }, 1000); }
        }
        function showHelp(resends) { if (help && +resends >= helpAfter) { help.hidden = false; } }

        function webOtp() {
            if (!('OTPCredential' in window) || !navigator.credentials) { return; }
            if (otpAbort) { otpAbort.abort(); }
            otpAbort = new AbortController();
            navigator.credentials.get({ otp: { transport: ['sms'] }, signal: otpAbort.signal }).then(function (otp) {
                if (otp && otp.code && !codeForm.hidden) {
                    codeIn.value = digits(otp.code).slice(0, 6);
                    submitCode();
                }
            }).catch(function () { /* aborted or not allowed: typing still works */ });
        }
        function stopOtp() { if (otpAbort) { otpAbort.abort(); otpAbort = null; } }

        function toState(state, data) {
            var code = state === 'code';
            phoneForm.hidden = code;
            codeForm.hidden = !code;
            resendForm.hidden = !code;
            if (help && !code) { help.hidden = true; }
            root.setAttribute('data-tsa-state', code ? 'code' : 'phone');
            if (code) {
                if (data && data.phone_fa && sentNum) { sentNum.textContent = data.phone_fa; }
                codeIn.value = '';
                invalid(codeIn, false);
                countdown(data ? data.wait : 0);
                if (data) { showHelp(data.resends); }
                codeIn.focus();
                webOtp();
            } else {
                stopOtp();
                clearInterval(timer);
                phoneIn.focus();
                if (phoneIn.select) { phoneIn.select(); }
            }
        }
        // the server already validated the path (ts_core.safe_url); the page navigates only to a same-site path that
        // passes the same rules again, never to anything that could become another host
        function samePath(p) {
            p = String(p || '');
            if (p.charAt(0) !== '/' || /^\/[\/\\]/.test(p) || /^\/%(2f|5c|09)/i.test(p)) { return '/my'; }
            for (var i = 0; i < p.length; i += 1) {
                if (p.charCodeAt(i) < 0x21 || p.charAt(i) === '\\') { return '/my'; }
            }
            return p;
        }

        function post(form, extra) {
            var fd = new FormData(form);
            Object.keys(extra || {}).forEach(function (k) { fd.set(k, extra[k]); });
            return fetch(form.action, { method: 'POST', body: fd, credentials: 'same-origin', headers: { 'X-TS-Auth': '1' } })
                .then(function (r) {
                    var type = r.headers.get('Content-Type') || '';
                    if (!r.ok || type.indexOf('json') < 0) { throw new Error('not json'); }
                    return r.json();
                });
        }

        phoneForm.addEventListener('submit', function (ev) {
            ev.preventDefault();
            if (busy) { return; }
            var n = digits(phoneIn.value);
            if (n.length < 10) {
                say('شمارهٔ موبایل ایران را به شکل ۰۹۱۲۳۴۵۶۷۸۹ وارد کنید.', 'warn');
                invalid(phoneIn, true);
                phoneIn.focus();
                return;
            }
            invalid(phoneIn, false);
            busy = true;
            post(phoneForm).then(function (data) {
                busy = false;
                say(data.msg, data.tone);
                if (data.state === 'code') { toState('code', data); } else { invalid(phoneIn, data.key === 'format'); phoneIn.focus(); }
            }).catch(function () { busy = false; phoneForm.submit(); });
        });

        function submitCode() {
            if (busy) { return; }
            var c = digits(codeIn.value);
            if (c.length !== 6) {
                say('کد ۶ رقمی است.', 'warn');
                invalid(codeIn, true);
                codeIn.focus();
                return;
            }
            busy = true;
            invalid(codeIn, false);
            post(codeForm, { code: c }).then(function (data) {
                if (data.ok && data.redirect) { stopOtp(); window.location.assign(samePath(data.redirect)); return; }
                busy = false;
                say(data.msg, data.tone);
                if (data.state === 'phone') { toState('phone'); return; }
                codeIn.value = '';
                invalid(codeIn, true);
                codeIn.focus();
            }).catch(function () { busy = false; codeForm.submit(); });
        }
        codeForm.addEventListener('submit', function (ev) { ev.preventDefault(); submitCode(); });
        codeIn.addEventListener('input', function () {
            var c = digits(codeIn.value).slice(0, 6);
            if (codeIn.value !== c) { codeIn.value = c; }
            if (c.length === 6) { submitCode(); }
        });
        codeIn.addEventListener('paste', function (ev) {
            var text = (ev.clipboardData || window.clipboardData);
            text = text && text.getData ? text.getData('text') : '';
            var c = digits(text);
            if (c) {
                ev.preventDefault();
                codeIn.value = c.slice(0, 6);
                if (codeIn.value.length === 6) { submitCode(); }
            }
        });

        resendForm.addEventListener('submit', function (ev) {
            ev.preventDefault();
            if (busy) { return; }
            busy = true;
            post(resendForm).then(function (data) {
                busy = false;
                say(data.msg, data.tone);
                if (data.state === 'phone') { toState('phone'); return; }
                countdown(data.wait);
                showHelp(data.resends);
                codeIn.focus();
                webOtp();
            }).catch(function () { busy = false; resendForm.submit(); });
        });

        var edit = codeForm.querySelector('[data-tsa-edit]');
        if (edit) {
            edit.addEventListener('click', function (ev) {
                ev.preventDefault();
                say('', '');
                if (!phoneIn.value && sentNum) { phoneIn.value = sentNum.textContent.replace(/\s/g, ''); }
                toState('phone');
            });
        }

        // a page that opens on the code (no-JS redirect, or reload): start the countdown and WebOTP
        if (root.getAttribute('data-tsa-state') === 'code') {
            countdown(root.getAttribute('data-tsa-wait'));
            webOtp();
        }
    }
})();
