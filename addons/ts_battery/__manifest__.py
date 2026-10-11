{
    'name': 'Talent Search - Batteries and panel catalog',
    'summary': 'Instrument batteries (ordered sets of instruments) and per-panel / per-member catalog grants (counseling-center phase 2)',
    'version': '20.0.1.0.0',
    'category': 'Services/Talent Search',
    'author': 'EOT',
    'license': 'LGPL-3',
    'depends': ['ts_panel', 'product'],
    'data': [
        'security/ir.access.csv',
        'views/battery_views.xml',
        'views/catalog_views.xml',
        'data/batteries.xml',
        'data/batteries_texts.xml',
    ],
    'installable': True,
}
