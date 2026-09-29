{
    'name': 'Talent Search - Interactive Talent Inventory',
    'summary': 'فهرست تعاملی استعداد: the participant names 2-8 fields, answers the same 15 statements per field; matrix engine, report, import of historical participants',
    'version': '20.0.1.0.0',
    'category': 'Services/Talent Search',
    'author': 'EOT',
    'license': 'LGPL-3',
    # ts_sms is a dependency so this module sits above it in the action_submit chain
    # (the result-ready SMS, a link only, is then sent for matrix attempts too).
    'depends': ['ts_assessment', 'ts_org', 'ts_sms'],
    'data': [
        'security/ir.access.csv',
        'views/web_talent.xml',
        'data/load.xml',
    ],
    'assets': {
        'ts_website.assets_ts': ['ts_talent/static/src/scss/talent.scss'],
        'ts_website.assets_ts_js': ['ts_talent/static/src/js/tt_player.js'],
    },
    'installable': True,
}
