from odoo import api, fields, models

FA = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')


def fmt_mobile(phone, persian=True):
    """09123456789 -> «۰۹۱۲ ۳۴۵ ۶۷۸۹» (or Latin digits)."""
    p = phone or ''
    out = '%s %s %s' % (p[:4], p[4:7], p[7:]) if len(p) == 11 else p
    return out.translate(FA) if persian else out


class ResPartner(models.Model):
    _inherit = 'res.partner'

    ts_phone = fields.Char('Talent Search verified mobile', copy=False, readonly=True)
    ts_phone_verified_at = fields.Datetime(copy=False, readonly=True)
    ts_sms_results = fields.Boolean('Notify by SMS when a result is ready', copy=False)
    # onb1: the one-time offer «شمارهٔ موبایل را به حسابتان وصل کنید» on /my (ts_name_unknown lives in ts_core)
    ts_phone_offer_seen = fields.Boolean('پیشنهاد اتصال موبایل دیده شد', copy=False, readonly=True)


class ResUsersPhoneOwner(models.Model):
    _inherit = 'res.users'

    @api.model
    def ts_phone_owner(self, phone, exclude=None):
        """Every account (archived included) that already holds this mobile: as its verified number or as its login."""
        if not phone:
            return self.browse()
        U = self.sudo().with_context(active_test=False)
        users = U.search(['|', ('login', '=', phone), ('partner_id.ts_phone', '=', phone)])
        return users - exclude if exclude else users
