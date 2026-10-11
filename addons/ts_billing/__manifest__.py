{
    'name': 'Talent Search - Prepaid billing',
    'summary': 'Prepaid credit on native Odoo (clinic phase 4): one product per instrument and battery, pricelist prices, '
               'hold at invitation, charge at completion, release, monthly caps, top-up by customer invoice, low-balance '
               'alert, company currency USD -> IRR (guarded)',
    'version': '20.0.1.0.0',
    'category': 'Services/Talent Search',
    'author': 'EOT',
    'license': 'LGPL-3',
    'depends': ['ts_battery', 'account', 'product'],
    'pre_init_hook': 'pre_init_hook',
    'data': [
        'security/ir.access.csv',
        'data/product_data.xml',
        'data/cron.xml',
        'data/billing_functions.xml',
        'views/backend_views.xml',
        'views/web_credits.xml',
        'views/web_inherit.xml',
    ],
    'assets': {
        'ts_website.assets_ts': ['ts_billing/static/src/scss/billing.scss'],
    },
    'installable': True,
}
