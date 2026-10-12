"""HR positions inside an employment panel (docs/hr/01_architecture.md section 5).

Every page: membership check (member_or_404), one permission (require), purpose = employment. What HR sees of a
candidate is decided by the existing `result_level()`: the job-fit summary only at level 'summary' (the candidate
shared the result); otherwise the status only. Reads are sudo after those checks, as in the rest of the panel."""
import re
from datetime import date, timedelta

from odoo import fields, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from odoo.addons.ts_onet.models import jobfit as J
from odoo.addons.ts_onet.models.occupation import CREDIT
from odoo.addons.ts_panel.controllers.base import (MENU, STATE_LABELS, flash_error, flash_ok, forbidden,
                                                   member_or_404, render_in_shell, require)

from ..models.position import DECISIONS, MAX_CRITICAL

MENU.append({'seq': 15, 'key': 'positions', 'group': 'استخدام', 'label': 'موقعیت‌های شغلی', 'suffix': '/positions',
             'perm': 'results:summary', 'needs_act': True})

STATUS = {'match': 'نقطهٔ قوت نسبی', 'neutral': 'در حد میانگین خودش', 'gap': 'کمتر از دیگر ویژگی‌هایش',
          'met': 'در حد نیاز یا بالاتر', 'short': 'پایین‌تر از نیاز'}
DEC = dict(DECISIONS)
PHONE_RE = re.compile(r'^0?9\d{9}$')
FA_TO_EN = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


def _base(ws_id, pid=None):
    return '/my/workspaces/%s/positions%s' % (ws_id, '/%s' % pid if pid else '')


def _employment_or_404(me):
    if me.workspace_id.purpose != 'employment':
        raise request.not_found()


def _position_or_404(me, pid):
    p = request.env['ts.hire.position'].sudo().browse(int(pid)).exists()
    if not p or p.workspace_id != me.workspace_id:
        raise request.not_found()
    return p


def _candidate_or_404(me, p, aid):
    a = request.env['ts.assignment'].sudo().browse(int(aid)).exists()
    if not a or a.position_id != p or a.workspace_id != me.workspace_id:
        raise request.not_found()
    if not me.can_see(a):
        raise request.not_found()
    return a


def _row(me, a):
    """One candidate as the list/compare pages show it; result content only at level 'summary'."""
    level = a.result_level(me) if a.attempt_id else 'status'
    res = a.ts_jobfit() if level == 'summary' else None
    progress = a.ts_battery_progress() if hasattr(a, 'ts_battery_progress') else None
    return {'a': a, 'level': level, 'res': res, 'band': res and res.get('band'),
            'band_fa': J.BAND_FA[res.get('band')] if res else None,
            'ws_band': res and res.get('ws') and res['ws'].get('band'), 'ab_band': res and res['ab'].get('band'),
            'explain': J.explain(res) if res else None, 'flags': a.ts_validity_labels() if res else [],
            'state': STATE_LABELS.get(a.state, a.state), 'progress': progress,
            'decision': DEC.get(a.hire_decision or 'none'), 'complete': a.ts_hire_complete}


def _visible(me, p):
    """The candidates of a position this member may see, as rows; order and counts never use what the member may not
    see (a candidate who did not share is listed by state only and never counted in a band)."""
    cands = p.assignment_ids.sudo().filtered(lambda a: a.state != 'withdrawn' and me.can_see(a))
    rows = [_row(me, a) for a in cands]
    order = {'done': 0, 'in_progress': 1, 'accepted': 2, 'invited': 3, 'declined': 4}
    rows.sort(key=lambda r: (0, r['a'].jobfit_order or 99, -r['a'].id) if r['res']
              else (1, order.get(r['a'].state, 5), -r['a'].id))
    counts = {'invited': len(rows), 'done': sum(1 for r in rows if r['complete']),
              'going': sum(1 for r in rows if r['a'].state in ('accepted', 'in_progress') and not r['complete']),
              'strong': sum(1 for r in rows if r['band'] == 'strong')}
    return rows, counts


def _parse_people(text):
    """Lines of «نام، موبایل، ایمیل» (comma, Persian comma, tab or semicolon). -> (people, errors)"""
    people, errors = [], []
    for n, line in enumerate((text or '').splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        parts = [x.strip() for x in re.split(r'[,،;\t]', line)]
        name = parts[0] if parts else ''
        phone = email = ''
        for x in parts[1:]:
            y = x.translate(FA_TO_EN).replace(' ', '').replace('-', '')
            if '@' in x:
                email = x
            elif PHONE_RE.match(y):
                phone = y if y.startswith('0') else '0' + y
        if len(name) < 2:
            errors.append('سطر %s: نام لازم است.' % n)
            continue
        people.append({'name': name[:80], 'phone': phone, 'email': email[:120]})
    return people, errors


class TsHirePositions(http.Controller):

    # ------------------------------------------------------------------ list
    @http.route('/my/workspaces/<int:ws_id>/positions', type='http', auth='user', website=True, sitemap=False)
    def positions(self, ws_id, **kw):
        me = member_or_404(ws_id)
        _employment_or_404(me)
        denied = require(me, 'results:summary', 'positions')
        if denied:
            return denied
        P = request.env['ts.hire.position'].sudo()
        rows = P.search([('workspace_id', '=', ws_id)])
        return render_in_shell('ts_hire.positions', me, 'positions', 'موقعیت‌های شغلی', rows=rows,
                               counts={p.id: _visible(me, p)[1] for p in rows}, can_create=me.has_perm('invites:create'))

    # ------------------------------------------------------------------ new
    @http.route('/my/workspaces/<int:ws_id>/positions/new', type='http', auth='user', website=True, sitemap=False,
                methods=['GET', 'POST'])
    def position_new(self, ws_id, **post):
        me = member_or_404(ws_id)
        _employment_or_404(me)
        denied = require(me, 'invites:create', 'positions')
        if denied:
            return denied
        Occ = request.env['ts.onet.occupation'].sudo()
        if request.httprequest.method == 'POST':
            name = (post.get('name') or '').strip()
            occ = Occ.browse(int(post.get('occupation_id') or 0)).exists()
            choice = post.get('battery_choice') if post.get('battery_choice') in ('short', 'full') else 'short'
            if len(name) < 2 or not occ:
                flash_error('عنوان موقعیت و شغل مرجع را انتخاب کنید.')
                return request.redirect(_base(ws_id) + '/new?q=%s' % (post.get('q') or ''))
            try:
                deadline = fields.Date.from_string(post.get('deadline')) if post.get('deadline') else date.today() + timedelta(days=14)
            except ValueError:
                deadline = date.today() + timedelta(days=14)
            try:
                p = request.env['ts.hire.position'].sudo().create({
                    'name': name[:100], 'workspace_id': ws_id, 'occupation_id': occ.id, 'battery_choice': choice,
                    'deadline': deadline, 'created_by_id': request.env.user.id})
            except (UserError, ValidationError) as e:
                flash_error(str(e.args[0] if e.args else e))
                return request.redirect(_base(ws_id) + '/new')
            if not p.battery_id or p.battery_id.state != 'published':
                flash_error('مجموعهٔ ارزیابی هنوز آماده نیست؛ با پشتیبانی استعدادیاب تماس بگیرید.')
            request.env['ts.audit.event'].sudo().log('position.create', p, workspace=me.workspace_id, occupation=occ.code)
            return request.redirect(_base(ws_id, p.id) + '/profile')
        q = (post.get('q') or '').strip()
        found = Occ.ts_search(q, limit=15) if len(q) >= 2 else Occ.browse()
        return render_in_shell('ts_hire.position_new', me, 'positions', 'موقعیت شغلی تازه', q=q, found=found,
                               back_url=_base(ws_id), back_label='موقعیت‌های شغلی',
                               default_deadline=(date.today() + timedelta(days=14)).isoformat())

    # ------------------------------------------------------------------ requirement profile
    @http.route('/my/workspaces/<int:ws_id>/positions/<int:pid>/profile', type='http', auth='user', website=True,
                sitemap=False, methods=['GET', 'POST'])
    def position_profile(self, ws_id, pid, **post):
        me = member_or_404(ws_id)
        _employment_or_404(me)
        p = _position_or_404(me, pid)
        can_edit = me.has_perm('invites:create')
        if request.httprequest.method == 'POST':
            if not can_edit:
                return forbidden(me, 'invites:create', 'positions')
            form = request.httprequest.form
            try:
                p.ts_set_profile(form.getlist('critical'), form.getlist('dropped'), me)
            except UserError as e:
                flash_error(str(e.args[0]))
                return request.redirect(_base(ws_id, p.id) + '/profile')
            flash_ok('نیمرخ نیازهای موقعیت ذخیره شد.')
            return request.redirect(_base(ws_id, p.id))
        denied = require(me, 'results:summary', 'positions')
        if denied:
            return denied
        all_reqs = p.occupation_id.ts_requirements()
        ov = p.ts_overrides()
        return render_in_shell('ts_hire.position_profile', me, 'positions', 'نیازهای %s' % p.name, p=p,
                               styles=[r for r in all_reqs if r['kind'] == 'WS'],
                               abilities=[r for r in all_reqs if r['kind'] == 'AB'],
                               critical=set(ov['critical']), dropped=set(ov['dropped']), can_edit=can_edit,
                               max_critical=MAX_CRITICAL, clinic=p.occupation_id.ts_profile().get('clinic') or [],
                               ab_fa=J.AB_FA, back_url=_base(ws_id, p.id), back_label=p.name, credit=CREDIT)

    # ------------------------------------------------------------------ one position: pipeline
    @http.route('/my/workspaces/<int:ws_id>/positions/<int:pid>', type='http', auth='user', website=True, sitemap=False)
    def position(self, ws_id, pid, **kw):
        me = member_or_404(ws_id)
        _employment_or_404(me)
        denied = require(me, 'results:summary', 'positions')
        if denied:
            return denied
        p = _position_or_404(me, pid)
        rows, counts = _visible(me, p)
        from datetime import datetime, time
        from odoo.addons.ts_assessment.models.attempt import jalali
        deadline_fa = jalali(datetime.combine(p.deadline, time(12)), with_time=False) if p.deadline else ''
        return render_in_shell('ts_hire.position', me, 'positions', p.name, p=p, rows=rows, counts=counts,
                               deadline_fa=deadline_fa,
                               can_invite=me.has_perm('invites:create') and p.state == 'open' and me.can_act(),
                               can_fair=me.has_perm('reports:group'), base=_base(ws_id, p.id),
                               back_url=_base(ws_id), back_label='موقعیت‌های شغلی',
                               email_on=request.env['ts.assignment'].sudo()._ts_email_enabled(), credit=CREDIT)

    @http.route('/my/workspaces/<int:ws_id>/positions/<int:pid>/state', type='http', auth='user', website=True,
                sitemap=False, methods=['POST'])
    def position_state(self, ws_id, pid, **post):
        me = member_or_404(ws_id)
        _employment_or_404(me)
        denied = require(me, 'invites:create', 'positions')
        if denied:
            return denied
        if not me.can_act():
            return forbidden(me, 'invites:create', 'positions')
        p = _position_or_404(me, pid)
        new = post.get('state')
        if new in ('open', 'closed') and new != p.state:
            if new == 'open' and not p.profile_reviewed:
                return request.redirect(_base(ws_id, p.id) + '/profile')
            p.write({'state': new})
            request.env['ts.audit.event'].sudo().log('position.state', p, workspace=me.workspace_id, state=new)
            flash_ok('موقعیت بسته شد؛ دعوت تازه ممکن نیست.' if new == 'closed' else 'موقعیت دوباره باز شد.')
        return request.redirect(_base(ws_id, p.id))

    # ------------------------------------------------------------------ invite candidates
    @http.route('/my/workspaces/<int:ws_id>/positions/<int:pid>/invite', type='http', auth='user', website=True,
                sitemap=False, methods=['POST'])
    def position_invite(self, ws_id, pid, **post):
        me = member_or_404(ws_id)
        _employment_or_404(me)
        denied = require(me, 'invites:create', 'positions')
        if denied:
            return denied
        p = _position_or_404(me, pid)
        back = _base(ws_id, p.id)
        if p.state != 'open' or not me.can_act():
            flash_error('این موقعیت برای دعوت باز نیست.')
            return request.redirect(back)
        if not p.battery_id or p.battery_id.state != 'published':
            flash_error('مجموعهٔ ارزیابی این موقعیت در دسترس نیست.')
            return request.redirect(back)
        allowed = me.allowed_batteries() if hasattr(me, 'allowed_batteries') else p.battery_id
        if p.battery_id not in allowed:
            flash_error('این مجموعهٔ ارزیابی برای پنل شما فعال نشده است؛ از مدیر پنل یا پشتیبانی بخواهید آن را فعال کند.')
            return request.redirect(back)
        people, errors = _parse_people(post.get('people'))
        if errors or not people:
            flash_error(' '.join(errors) or 'دست‌کم یک داوطلب وارد کنید: در هر سطر نام، موبایل و ایمیل.')
            return request.redirect(back + '#tsh-invite')
        if len(people) > 50:
            flash_error('در هر بار حداکثر ۵۰ داوطلب را دعوت کنید.')
            return request.redirect(back + '#tsh-invite')
        extra = post.get('extra_time') if post.get('extra_time') in ('1.0', '1.25', '1.5') else '1.0'
        want_sms, want_email = post.get('send_sms') == '1', post.get('send_email') == '1'
        try:
            from odoo.addons.ts_panel.controllers.invites import sms_available
            sms_ok = sms_available(me.workspace_id)
        except ImportError:
            sms_ok = False
        A = request.env['ts.assignment'].sudo()
        made, sent_sms, sent_email, to_mail = 0, 0, 0, []
        try:
            with request.env.cr.savepoint():
                for x in people:
                    vals = {'workspace_id': ws_id, 'battery_id': p.battery_id.id,
                            'instrument_id': p.battery_id.ts_first_instrument().id, 'invited_by_id': request.env.user.id,
                            'invitee_name': x['name'], 'invitee_email': x['email'] or False,
                            'invitee_phone': x['phone'] or False, 'deadline': p.deadline, 'position_id': p.id,
                            'ts_extra_time': extra, 'note': 'ارزیابی برای موقعیت «%s»' % p.name}
                    if want_sms and sms_ok and x['phone']:
                        vals.update(sms_consent=True, remind_ok=True)
                    a = A.with_user(request.env.user).sudo().create(vals)
                    made += 1
                    if a.sms_sent_at if 'sms_sent_at' in a._fields else False:
                        sent_sms += 1
                    if want_email and x['email']:
                        to_mail.append(a)
        except (UserError, ValidationError) as e:
            flash_error(str(e.args[0] if e.args else e))
            return request.redirect(back + '#tsh-invite')
        for a in to_mail:
            if a._ts_send_invite_email():
                sent_email += 1
        msg = '%s دعوت ساخته شد' % _fa(made)
        if want_sms:
            msg += '؛ پیامک: %s' % _fa(sent_sms)
        if want_email:
            msg += '؛ ایمیل: %s' % _fa(sent_email)
        flash_ok(msg + '. برای کسانی که پیامک یا ایمیل نگرفتند، پیوند دعوت را از صفحهٔ داوطلب کپی کنید.')
        return request.redirect(back)

    # ------------------------------------------------------------------ one candidate
    @http.route('/my/workspaces/<int:ws_id>/positions/<int:pid>/c/<int:aid>', type='http', auth='user', website=True,
                sitemap=False)
    def candidate(self, ws_id, pid, aid, **kw):
        me = member_or_404(ws_id)
        _employment_or_404(me)
        denied = require(me, 'results:summary', 'positions')
        if denied:
            return denied
        p = _position_or_404(me, pid)
        a = _candidate_or_404(me, p, aid)
        row = _row(me, a)
        request.env['ts.audit.event'].sudo().log('hire.view', a, workspace=me.workspace_id, level=row['level'])
        ver = request.env['ts.assignment'].sudo().search([('verify_of_id', '=', a.id)], limit=1)
        open_link = a.state in ('invited', 'opened', 'expired')
        return render_in_shell('ts_hire.candidate', me, 'positions', a.invitee_name, p=p, r=row, a=a, st_labels=STATUS,
                               decisions=DECISIONS, can_decide=me.has_perm('invites:manage') and me.can_act(),
                               can_invite=me.has_perm('invites:create') and me.can_act(), ver=ver,
                               url=a.invite_url() if open_link else None, base=_base(ws_id, p.id),
                               back_url=_base(ws_id, p.id), back_label=p.name, credit=CREDIT,
                               model=J.MODEL)

    @http.route('/my/workspaces/<int:ws_id>/positions/<int:pid>/c/<int:aid>/decision', type='http', auth='user',
                website=True, sitemap=False, methods=['POST'])
    def candidate_decision(self, ws_id, pid, aid, **post):
        me = member_or_404(ws_id)
        _employment_or_404(me)
        denied = require(me, 'invites:manage', 'positions')
        if denied:
            return denied
        if not me.can_act():
            return forbidden(me, 'invites:manage', 'positions')
        p = _position_or_404(me, pid)
        a = _candidate_or_404(me, p, aid)
        try:
            a.ts_set_decision(post.get('decision'), post.get('note'), request.env.user)
            flash_ok('تصمیم ثبت شد.')
        except UserError as e:
            flash_error(str(e.args[0]))
        return request.redirect(_base(ws_id, p.id) + '/c/%s' % a.id)

    @http.route('/my/workspaces/<int:ws_id>/positions/<int:pid>/c/<int:aid>/verify', type='http', auth='user',
                website=True, sitemap=False, methods=['POST'])
    def candidate_verify(self, ws_id, pid, aid, **post):
        me = member_or_404(ws_id)
        _employment_or_404(me)
        denied = require(me, 'invites:create', 'positions')
        if denied:
            return denied
        if not me.can_act():
            return forbidden(me, 'invites:create', 'positions')
        p = _position_or_404(me, pid)
        a = _candidate_or_404(me, p, aid)
        try:
            a.ts_invite_verification(me)
            flash_ok('آزمون تأیید ساخته شد. پیوند آن را هنگام حضور داوطلب در سازمان باز کنید.')
        except (UserError, ValidationError) as e:
            flash_error(str(e.args[0] if e.args else e))
        return request.redirect(_base(ws_id, p.id) + '/c/%s' % a.id)

    @http.route('/my/workspaces/<int:ws_id>/positions/<int:pid>/c/<int:aid>/remind', type='http', auth='user',
                website=True, sitemap=False, methods=['POST'])
    def candidate_remind(self, ws_id, pid, aid, **post):
        me = member_or_404(ws_id)
        _employment_or_404(me)
        denied = require(me, 'invites:manage', 'positions')
        if denied:
            return denied
        if not me.can_act():
            return forbidden(me, 'invites:manage', 'positions')
        p = _position_or_404(me, pid)
        a = _candidate_or_404(me, p, aid)
        ok, msg = a.ts_manual_reminder(me) if hasattr(a, 'ts_manual_reminder') else (False, 'یادآوری در دسترس نیست.')
        (flash_ok if ok else flash_error)(msg)
        return request.redirect(_base(ws_id, p.id) + '/c/%s' % a.id)

    # ------------------------------------------------------------------ compare
    @http.route('/my/workspaces/<int:ws_id>/positions/<int:pid>/compare', type='http', auth='user', website=True,
                sitemap=False)
    def compare(self, ws_id, pid, **kw):
        me = member_or_404(ws_id)
        _employment_or_404(me)
        denied = require(me, 'results:summary', 'positions')
        if denied:
            return denied
        p = _position_or_404(me, pid)
        ids = [int(x) for x in request.httprequest.args.getlist('ids') if x.isdigit()][:3]
        rows = []
        for aid in ids:
            try:
                rows.append(_row(me, _candidate_or_404(me, p, aid)))
            except Exception:  # noqa: BLE001 - a foreign or hidden id is skipped, never shown
                continue
        rows = [r for r in rows if r['res']]
        if len(rows) < 2:
            flash_error('برای مقایسه دو یا سه داوطلب را انتخاب کنید که نتیجه‌شان در دسترس است.')
            return request.redirect(_base(ws_id, p.id))
        reqs = p.ts_requirements()
        return render_in_shell('ts_hire.compare', me, 'positions', 'مقایسهٔ داوطلبان', p=p, rows=rows, reqs=reqs,
                               st_labels=STATUS, back_url=_base(ws_id, p.id), back_label=p.name)

    # ------------------------------------------------------------------ fairness
    @http.route('/my/workspaces/<int:ws_id>/positions/<int:pid>/fairness', type='http', auth='user', website=True,
                sitemap=False)
    def fairness(self, ws_id, pid, **kw):
        me = member_or_404(ws_id)
        _employment_or_404(me)
        denied = require(me, 'reports:group', 'positions')
        if denied:
            return denied
        p = _position_or_404(me, pid)
        return render_in_shell('ts_hire.fairness', me, 'positions', 'بررسی منصفانه بودن', p=p,
                               fair=p.ts_fairness() if p.state == 'closed' else None,
                               back_url=_base(ws_id, p.id), back_label=p.name)


def _fa(n):
    from odoo.addons.ts_assessment.models.attempt import fa_digits
    return fa_digits(n)
