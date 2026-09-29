from odoo import fields, models

KV_FAILURES = [
    ('kv_ip', 'Kavenegar: IP not allowed'),
    ('kv_sender', 'Kavenegar: invalid sender line'),
    ('kv_message', 'Kavenegar: empty or too long message'),
    ('kv_links', 'Kavenegar: links not allowed on this line'),
    ('kv_charset', 'Kavenegar: forbidden characters'),
    ('kv_rate', 'Kavenegar: rate limited'),
    ('kv_test_only', 'Kavenegar: test messages only to the owner number'),
    ('kv_service', 'Kavenegar: service not available on account'),
]


class MailNotification(models.Model):
    _inherit = 'mail.notification'

    failure_type = fields.Selection(selection_add=KV_FAILURES)
