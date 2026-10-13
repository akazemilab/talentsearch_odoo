from odoo import models

FA = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _ts_verified_phones(self):
        """Mobile numbers this user has proven; ts_sms extends it."""
        return []

    def ts_account_label(self):
        """How a participant page names the signed-in account to its owner (UX T7 X6): {'label', 'kind'}.
        kind 'name' = the person's own name; 'phone' = the masked verified mobile (۰۹۱۲…۵۱۰۱) of an account made by
        mobile code with no name yet; 'email' = the masked e-mail (a…@example.com); '' = nothing to show.
        Display only: the account owner sees their own identifier, never someone else's."""
        self.ensure_one()
        if self._is_public():
            return {'label': '', 'kind': ''}
        name = self.partner_id.ts_known_name()
        if name:
            return {'label': name, 'kind': 'name'}
        user = self.sudo()
        phones = [p for p in user._ts_verified_phones() if p]
        login = user.login or ''
        phone = phones[0] if phones else (login if login.isdigit() else '')
        if len(phone) >= 7:
            # LRM around the ellipsis: Persian digits are bidi AN and would otherwise show the two parts swapped
            return {'label': (phone[:4] + '\u200e…\u200e' + phone[-4:]).translate(FA), 'kind': 'phone'}
        email = user.email or (login if '@' in login else '')
        if email and '@' in email:
            local, dom = email.split('@', 1)
            return {'label': local[:1] + '…@' + dom, 'kind': 'email'}
        return {'label': '', 'kind': ''}
