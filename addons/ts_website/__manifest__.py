{
    'name': 'Talent Search - Website',
    'summary': 'talentsearch.ir as website 2 in eot_main: layout, pages, lead forms. Everything is bound to website 2.',
    'version': '20.0.1.0.0',
    'category': 'Website',
    'author': 'EOT',
    'license': 'LGPL-3',
    'depends': ['website', 'crm', 'website_crm', 'ts_core'],
    'data': [
        'data/website.xml',
        'data/crm.xml',
        'views/layout.xml',
        'views/snippets.xml',
        'views/page_home.xml',
        'views/pages_audience.xml',
        'views/pages_trust.xml',
        'views/pages_company.xml',
        'views/page_404.xml',
        'data/pages.xml',
        'data/setup.xml',
    ],
    'assets': {
        # Own bundle, loaded only by website-2 layout views. Never add to
        # web.assets_frontend: that bundle is shared with eot.ir.
        'ts_website.assets_ts': [
            'ts_website/static/src/scss/ts.scss',
        ],
        'ts_website.assets_ts_js': [
            'ts_website/static/src/js/ts_nav.js',
        ],
    },
    'installable': True,
}
