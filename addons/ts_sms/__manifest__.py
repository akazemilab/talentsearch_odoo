{
    'name': 'Talent Search - SMS',
    'summary': 'Invitation SMS, result-ready notice and mobile-number OTP verification (website 2) on top of ts_kavenegar',
    'version': '20.0.1.0.0',
    'category': 'Services/Talent Search',
    'author': 'EOT',
    'license': 'LGPL-3',
    'depends': ['ts_kavenegar', 'ts_org', 'ts_assessment', 'ts_website'],
    'data': [
        'security/ir.access.csv',
        'data/cron.xml',
        'views/backend.xml',
        'views/web_sms.xml',
    ],
    'assets': {},
    'installable': True,
}
