{
    'name': 'Talent Search - SMS',
    'summary': 'Invitation SMS, result-ready notice and mobile-number OTP verification (website 2) on top of ts_kavenegar',
    'version': '20.0.2.0.1',
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
    'assets': {
        # the website-4 bundles only (never web.assets_frontend, shared with eot.ir)
        'ts_website.assets_ts': ['ts_sms/static/src/scss/signin.scss'],
        'ts_website.assets_ts_js': ['ts_sms/static/src/js/signin.js'],
    },
    'installable': True,
}
