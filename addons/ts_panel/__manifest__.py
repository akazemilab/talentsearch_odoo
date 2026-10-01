{
    'name': 'Talent Search - Panel v2',
    'summary': 'Panel v2: roles and permissions, clients, invitations, reports, audit, lifecycle (website 2 only). S0 = tooling and two fixes.',
    'version': '20.0.1.0.0',
    'category': 'Services/Talent Search',
    'author': 'EOT',
    'license': 'LGPL-3',
    'depends': ['ts_talent'],
    'data': [
        'views/report_share.xml',
    ],
    'assets': {
        'ts_website.assets_ts': ['ts_panel/static/src/scss/panel.scss'],
        'ts_website.assets_ts_js': ['ts_panel/static/src/js/panel.js'],
    },
    'installable': True,
}
