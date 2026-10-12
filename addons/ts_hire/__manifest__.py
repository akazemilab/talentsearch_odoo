{
    'name': 'Talent Search - HR hiring (positions, job fit, email)',
    'summary': 'Employment panels: positions tied to O*NET occupations, the HR personality questionnaire (IPIP-HEXACO), '
               'two HR batteries, candidate job fit (JOBFIT-v1, bands, never a cut-off), response-validity signals, '
               'decisions, four-fifths fairness view, verification test, email invitations (docs/hr/01_architecture.md)',
    'version': '20.0.1.0.0',
    'category': 'Services/Talent Search',
    'author': 'EOT',
    'license': 'LGPL-3',
    'depends': ['ts_brand', 'ts_tasks', 'ts_onet', 'mail'],
    'data': [
        'security/ir.access.csv',
        'views/position_views.xml',
        'views/web_hire.xml',
        'views/web_hire_inherit.xml',
        'data/mail_templates.xml',
        'data/load.xml',
    ],
    'assets': {
        'ts_website.assets_ts': ['ts_hire/static/src/scss/hire.scss'],
        'ts_website.assets_ts_js': ['ts_hire/static/src/js/hire.js'],
    },
    'installable': True,
}
