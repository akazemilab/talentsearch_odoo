{
    'name': 'Kavenegar SMS',
    'summary': 'Native Odoo SMS gateway for Kavenegar: send, schedule, status webhook, inbox, '
               'verify templates, voice, blocked list, media, account tools',
    'version': '20.0.1.0.0',
    'category': 'Hidden/Tools',
    'author': 'EOT',
    'license': 'LGPL-3',
    'depends': ['sms', 'phone_validation'],
    'data': [
        'security/ir.access.csv',
        'data/cron.xml',
        'views/kavenegar_views.xml',
        'views/res_config_settings_views.xml',
        'wizard/wizard_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
}
