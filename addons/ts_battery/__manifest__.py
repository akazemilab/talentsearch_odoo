{
    'name': 'Talent Search - Batteries and panel catalog',
    'summary': 'Instrument batteries (ordered sets of instruments), per-panel / per-member catalog grants (counseling-center '
               'phase 2) and the battery run: one invitation, one consent, chained instruments, battery reports (phase 3)',
    'version': '20.0.2.0.0',
    'category': 'Services/Talent Search',
    'author': 'EOT',
    'license': 'LGPL-3',
    'depends': ['ts_panel', 'product'],
    'data': [
        'security/ir.access.csv',
        'views/battery_views.xml',
        'views/catalog_views.xml',
        'views/web_battery.xml',
        'views/web_battery_inherit.xml',
        'data/batteries.xml',
        'data/batteries_texts.xml',
    ],
    'assets': {
        'ts_website.assets_ts': ['ts_battery/static/src/scss/battery.scss'],
    },
    'installable': True,
}
