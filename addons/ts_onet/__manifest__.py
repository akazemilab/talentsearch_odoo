{
    'name': 'Talent Search - O*NET occupation catalogue and job fit',
    'summary': 'Persian catalogue of 923 O*NET 31.0 occupations (CC BY 4.0) with their work-style and ability '
               'requirements, and the JOBFIT-v1 engine used by HR positions (docs/hr/01_architecture.md)',
    'version': '20.0.1.0.0',
    'category': 'Services/Talent Search',
    'author': 'EOT',
    'license': 'LGPL-3',
    'depends': ['ts_core', 'website'],
    'data': [
        'security/ir.access.csv',
        'views/occupation_views.xml',
        'data/load.xml',
    ],
    'installable': True,
}
