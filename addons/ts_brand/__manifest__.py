{
    'name': 'Talent Search - Institution branding, PDF reports and SMS templates',
    'summary': 'Clinic phase 5 (docs/clinic/01_architecture.md sections 5 and 6): the counseling center and its counselor on '
               'every report (screen, print, PDF), on-demand PDF downloads that are never stored, native sms.template texts '
               '(docs/clinic/05_sms_texts.md) with short links /i/<code> and /j/<code>',
    'version': '20.0.1.0.0',
    'category': 'Services/Talent Search',
    'author': 'EOT',
    'license': 'LGPL-3',
    'depends': ['ts_billing', 'sms', 'web'],
    'post_init_hook': 'post_init_hook',
    'data': [
        'data/sms_templates.xml',
        'data/report.xml',
        'views/web_brand.xml',
        'views/web_brand_inherit.xml',
        'views/report_pdf.xml',
    ],
    'assets': {
        'ts_website.assets_ts': ['ts_brand/static/src/scss/brand.scss'],
        'ts_website.assets_ts_js': ['ts_brand/static/src/js/brand_preview.js'],
    },
    'installable': True,
}
