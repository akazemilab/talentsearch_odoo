{
    'name': 'Talent Search - Organizations and Clinicians',
    'summary': 'Workspace invitations, purpose-bound result sharing, clinician reports, operations dashboards (website 2)',
    'version': '20.0.5.0.0',
    'category': 'Services/Talent Search',
    'author': 'EOT',
    'license': 'LGPL-3',
    'depends': ['ts_assessment'],
    'data': [
        'security/ir.access.csv',
        'data/sequence.xml',
        'views/backend.xml',
        'views/web_org.xml',
        'views/web_panel.xml',
        'views/emergency.xml',
    ],
    'assets': {
        'ts_website.assets_ts': ['ts_org/static/src/scss/org.scss'],
    },
    'installable': True,
}
