{
    'name': 'Talent Search - Timed cognitive tasks',
    'summary': 'Timed task instruments (reasoning, spatial, numeric, speed and attention) played inside the normal '
               'attempt and battery flow; items generated per candidate, keys and deadlines kept on the server, '
               'provisional then empirical norms, integrity signals (docs/hr/01_architecture.md section 4)',
    'version': '20.0.1.0.0',
    'category': 'Services/Talent Search',
    'author': 'EOT',
    'license': 'LGPL-3',
    'depends': ['ts_battery', 'ts_onet', 'website'],
    'data': [
        'security/ir.access.csv',
        'views/web_tasks.xml',
        'data/load.xml',
        'data/cron.xml',
    ],
    'assets': {
        'ts_website.assets_ts': ['ts_tasks/static/src/scss/tasks.scss'],
        'ts_website.assets_ts_js': ['ts_tasks/static/src/js/tst_player.js'],
    },
    'installable': True,
}
