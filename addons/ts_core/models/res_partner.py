from odoo import fields, models


class ResPartner(models.Model):
    """onb1: an account made by mobile code alone has no name yet. `name` then holds the formatted mobile so the back
    office can find the person; the site never shows it as the person's name (use ts_known_name())."""
    _inherit = 'res.partner'

    ts_name_unknown = fields.Boolean('نام هنوز وارد نشده', copy=False, readonly=True)

    def ts_known_name(self):
        """The person's own name, or '' when the account was made by mobile code and no name was given yet."""
        self.ensure_one()
        return '' if self.sudo().ts_name_unknown else (self.name or '').strip()

    def write(self, vals):
        # a real name written anywhere (account page, a form that asks for it, the back office) ends «unknown»
        if 'name' in vals and 'ts_name_unknown' not in vals and not self.env.context.get('ts_name_placeholder'):
            if any(p.ts_name_unknown for p in self):
                vals = dict(vals, ts_name_unknown=False)
        return super().write(vals)
