{
    'name': 'Talent Search - Core',
    'summary': 'Workspaces, memberships, purpose separation and audit trail for Talent Search (website 2)',
    'version': '20.0.1.0.0',
    'category': 'Services/Talent Search',
    'author': 'EOT',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'portal'],
    'data': [
        'security/ts_security.xml',
        'security/ir.access.csv',
        'data/ts_sequence.xml',
        'views/workspace_views.xml',
        'views/audit_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': True,
}
