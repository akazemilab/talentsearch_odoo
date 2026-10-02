{
    'name': 'Talent Search - Assessments',
    'summary': 'Versioned instrument catalog, Persian RTL player, S09-V3.0 scoring engine, participant results (website 2)',
    'version': '20.0.3.0.0',
    'category': 'Services/Talent Search',
    'author': 'EOT',
    'license': 'LGPL-3',
    'depends': ['ts_core', 'ts_website', 'portal', 'website'],
    'data': [
        'security/ir.access.csv',
        'data/sequence.xml',
        'views/backend.xml',
        'views/web_catalog.xml',
        'views/web_player.xml',
        'views/web_portal.xml',
        'data/load.xml',
    ],
    'assets': {
        'ts_website.assets_ts': ['ts_assessment/static/src/scss/assessment.scss'],
        'ts_website.assets_ts_js': ['ts_assessment/static/src/js/ts_player.js'],
    },
    'installable': True,
}
