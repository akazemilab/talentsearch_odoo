from odoo import fields, models


class TsUsageEvent(models.Model):
    """One row per completed workspace attempt. Only recorded for now: nothing is deducted or blocked.
    The next phase (panel credit) will read this history."""
    _name = 'ts.usage.event'
    _description = 'Talent Search usage event'
    _order = 'id desc'

    workspace_id = fields.Many2one('ts.workspace', required=True, ondelete='restrict', index=True)
    attempt_id = fields.Many2one('ts.attempt', required=True, ondelete='restrict', index=True)
    assignment_id = fields.Many2one('ts.assignment', ondelete='set null')
    units = fields.Integer(default=1)
    event_date = fields.Datetime(default=fields.Datetime.now, required=True)

    _attempt_unique = models.Constraint('unique(attempt_id)', 'برای هر اجرا فقط یک رویداد مصرف ثبت می‌شود.')
