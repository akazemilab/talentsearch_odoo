"""Battery run (docs/clinic/01_architecture.md section 3): one invitation, several instruments.

* `ts.assignment.battery_id` marks a battery invitation; its `instrument_id` is the first line's instrument, so every
  existing constraint, list and `result_level()` keeps working. `attempt_id` stays the first attempt.
* Accepting creates one attempt per battery line at once (state consent), in sequence order; every attempt carries
  `assignment_id` (single invitations get it too: `attempt_ids == attempt_id` there).
* Consent is given once, on the first attempt; `give_consent()` copies it to the siblings (one record per attempt).
* Result access is unchanged: a sibling attempt answers `ts_result_level()` through its invitation, i.e. the level of
  the whole battery, and never more than 'status' while it is not done.
"""
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from .catalog import BATTERY_NOT_IN_CATALOG
from .battery import ts_strip_limit

PERSIAN_DIGITS = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')


def fa(n):
    return str(n).translate(PERSIAN_DIGITS)


class TsAssignmentBattery(models.Model):
    _inherit = 'ts.assignment'

    battery_id = fields.Many2one('ts.battery', 'مجموعه', index=True, ondelete='restrict', readonly=True,
                                 help='دعوت به یک مجموعه: سنجهٔ این دعوت نخستین سنجهٔ مجموعه است.')
    attempt_ids = fields.One2many('ts.attempt', 'assignment_id', 'اجراها', readonly=True)

    @api.depends('withdrawn', 'declined', 'user_id', 'attempt_id.state', 'expired', 'opened_at',
                 'battery_id', 'attempt_ids.state')
    def _compute_state(self):
        super()._compute_state()
        for a in self:
            if not a.battery_id or a.state in ('withdrawn', 'declined') or not a.attempt_ids:
                continue
            states = a.attempt_ids.mapped('state')
            if all(s == 'done' for s in states):
                a.state = 'done'
            elif any(s in ('in_progress', 'done') for s in states):
                a.state = 'in_progress'
            else:
                a.state = 'accepted'

    @api.model_create_multi
    def create(self, vals_list):
        Campaign = self.env['ts.campaign'].sudo()
        B = self.env['ts.battery'].sudo()
        for vals in vals_list:
            # a list or open-link campaign of a battery: every invitation it creates is a battery invitation
            if not vals.get('battery_id') and vals.get('campaign_id'):
                camp = Campaign.browse(vals['campaign_id'])
                if camp.battery_id:
                    vals['battery_id'] = camp.battery_id.id
            if vals.get('battery_id'):
                first = B.browse(vals['battery_id']).ts_first_instrument()
                if first:
                    vals['instrument_id'] = first.id
        return super().create(vals_list)

    @api.constrains('battery_id', 'instrument_id', 'workspace_id', 'invited_by_id')
    def _check_battery(self):
        """Server-side: a battery invitation needs a published battery inside the inviter's allowed batteries (the
        panel catalog when the inviter is not a member, e.g. the back office)."""
        M = self.env['ts.workspace.member'].sudo()
        for a in self.sudo():
            b = a.battery_id
            if not b:
                continue
            if b.state != 'published' or a.instrument_id != b.ts_first_instrument():
                raise ValidationError('این مجموعه منتشر نشده است یا سنجهٔ نخست آن با دعوت یکی نیست.')
            m = M.search([('workspace_id', '=', a.workspace_id.id), ('user_id', '=', a.invited_by_id.id),
                          ('active', '=', True)], limit=1) if a.invited_by_id else M
            allowed = m.allowed_batteries() if m else a.workspace_id.ts_catalog_batteries()
            if b not in allowed:
                raise UserError(BATTERY_NOT_IN_CATALOG)

    # ------------------------------------------------------------------ accept: one attempt per line
    def action_accept(self, user, share):
        self.ensure_one()
        attempt = super().action_accept(user, share)
        a = self.sudo()
        if attempt and a.attempt_id == attempt and a.user_id == user:
            a._ts_battery_make_attempts(attempt)
        return attempt

    def _ts_battery_make_attempts(self, first):
        """Idempotent: the first attempt gets assignment_id (and battery_seq 1); a battery gets the missing attempts of
        its other lines, in sequence order, with the same workspace, client and person as the first one."""
        self.ensure_one()
        first = first.sudo()
        if not first.assignment_id:
            first.write({'assignment_id': self.id, 'battery_seq': 1 if self.battery_id else 0})
        if not self.battery_id:
            return first
        self.invalidate_recordset(['attempt_ids'])
        have = {t.instrument_id.id for t in self.attempt_ids}
        T = self.env['ts.attempt'].sudo()
        made = T.browse()
        for n, line in enumerate(self.battery_id.ts_lines(), start=1):
            inst = line.instrument_id
            if inst.id in have:
                continue
            vals = {'user_id': first.user_id.id, 'instrument_id': inst.id, 'version_id': inst.current_version_id.id,
                    'workspace_id': first.workspace_id.id, 'assignment_id': self.id, 'battery_seq': n,
                    'ts_preview': bool(first.ts_preview)}      # onb3: every part of a try-out is a try-out
            if 'client_id' in T._fields and first.client_id:
                vals['client_id'] = first.client_id.id
            if 'person_id' in T._fields and first.person_id:
                vals['person_id'] = first.person_id.id
            made |= T.create(vals)
            have.add(inst.id)
        if made:
            self.env['ts.audit.event'].log('battery.attempts', self, workspace=self.workspace_id,
                                           battery=self.battery_id.code, attempts=len(have))
        return first

    # ------------------------------------------------------------------ helpers for pages
    def ts_battery_attempts(self):
        """The attempts of this invitation in battery order (single invitation: the one attempt)."""
        self.ensure_one()
        rows = self.sudo().attempt_ids or self.sudo().attempt_id
        return rows.sorted(lambda t: (t.battery_seq or 0, t.id))

    def ts_battery_progress(self):
        """(done, total) over the battery's attempts; (0, n lines) before acceptance."""
        self.ensure_one()
        if not self.battery_id:
            return (1 if self.attempt_id.state == 'done' else 0), 1
        rows = self.ts_battery_attempts()
        total = len(rows) or len(self.battery_id.line_ids)
        return len(rows.filtered(lambda t: t.state == 'done')), total

    def ts_item_name(self):
        """What was invited, in words: the battery name or the instrument's display title."""
        self.ensure_one()
        return ('مجموعهٔ %s' % self.battery_id.name) if self.battery_id else self.instrument_id.ts_title()

    def ts_battery_progress_text(self):
        """«۱ از ۲ سنجه انجام شده» ('' for a single invitation)."""
        self.ensure_one()
        if not self.battery_id:
            return ''
        done, total = self.ts_battery_progress()
        return '%s از %s سنجه انجام شده' % (fa(done), fa(total))

    # ------------------------------------------------------------------ invitation SMS names the battery
    def _ts_invite_sms_body(self):
        self.ensure_one()
        if not self.battery_id:
            return super()._ts_invite_sms_body()
        return '«%s» شما را به مجموعهٔ «%s» در استعدادیاب دعوت کرده است. پذیرش اختیاری است:\n%s' % (
            self.workspace_id.ts_public_name(), self.battery_id.ts_title(), self.invite_url())


class TsBatteryRunHelpers(models.Model):
    _inherit = 'ts.battery'

    def ts_lines(self):
        self.ensure_one()
        return self.sudo().line_ids.sorted(lambda l: (l.sequence, l.id))

    def ts_first_instrument(self):
        self.ensure_one()
        return self.ts_lines()[:1].instrument_id

    def ts_card(self):
        """Facts of a battery card (wizard, consent, invitation page): instruments with item counts and minutes.
        The description is shown without the «… نه تشخیص» sentence: the pages say the limit once (UX audit G6-PT9)."""
        self.ensure_one()
        b = self.sudo()
        # effort/duration: the instrument's own labels («۳ بخش زمان‌دار», «۲ تا ۸ زمینه…»), never «۰ پرسش» (T7, W20)
        lines = [{'name': l.instrument_id.ts_title(), 'items': l.instrument_id.active_item_count or 0,
                  'minutes': l.instrument_id.duration_minutes or 0,
                  'effort': l.instrument_id.ts_effort_label(), 'duration': l.instrument_id.ts_total_time_label()}
                 for l in b.ts_lines()]
        return {'name': b.name, 'description': ts_strip_limit(b.description), 'count': len(lines), 'items': b.item_count,
                'minutes': b.ts_minutes_text(), 'lines': lines}   # = sum of the lines (verify T7), not est_minutes

    def ts_facts(self):
        """One line for a panel page: «۲ سنجه، ۱۳ پرسش، حدود ۵ دقیقه: فهرست پاکزیستی، فهرست تعهد فردی»."""
        self.ensure_one()
        c = self.ts_card()
        return '%s سنجه، %s پرسش، حدود %s دقیقه: %s' % (fa(c['count']), fa(c['items']), fa(c['minutes']),
                                                       '، '.join(ln['name'] for ln in c['lines']))


class TsCampaignBattery(models.Model):
    _inherit = 'ts.campaign'

    battery_id = fields.Many2one('ts.battery', 'مجموعه', ondelete='restrict', index=True)

    @api.model_create_multi
    def create(self, vals_list):
        B = self.env['ts.battery'].sudo()
        for vals in vals_list:
            if vals.get('battery_id'):
                first = B.browse(vals['battery_id']).ts_first_instrument()
                if first:
                    vals['instrument_id'] = first.id
        return super().create(vals_list)

    @api.constrains('instrument_id', 'workspace_id', 'created_by_id')
    def _check_instrument(self):
        """A battery campaign is checked against the creator's allowed batteries; a single one as before."""
        single = self.filtered(lambda c: not c.battery_id)
        if single:
            super(TsCampaignBattery, single)._check_instrument()
        for c in self - single:
            allowed = c.created_by_id.allowed_batteries() if c.created_by_id else c.workspace_id.ts_catalog_batteries()
            if c.battery_id not in allowed:
                raise ValidationError(BATTERY_NOT_IN_CATALOG)

    @api.constrains('battery_id')
    def _check_battery_campaign(self):
        self._check_instrument()

    def ts_item_name(self):
        self.ensure_one()
        return ('مجموعهٔ %s' % self.battery_id.name) if self.battery_id else self.instrument_id.ts_title()


class TsAttemptBattery(models.Model):
    _inherit = 'ts.attempt'

    assignment_id = fields.Many2one('ts.assignment', 'دعوت', index=True, ondelete='set null', readonly=True)
    battery_seq = fields.Integer('ردیف در مجموعه', readonly=True)

    # ------------------------------------------------------------------ battery facts
    def ts_battery(self):
        self.ensure_one()
        return self.sudo().assignment_id.battery_id

    def ts_battery_siblings(self):
        """All attempts of this attempt's battery, in order (this one included); empty for a single attempt."""
        self.ensure_one()
        a = self.sudo().assignment_id
        return a.ts_battery_attempts() if a.battery_id else self.browse()

    def ts_battery_first(self):
        self.ensure_one()
        return self.ts_battery_siblings()[:1]

    def ts_battery_index(self):
        self.ensure_one()
        sib = self.ts_battery_siblings()
        return (sib.ids.index(self.id) + 1) if self.id in sib.ids else 0

    def ts_battery_next(self):
        """The first attempt of the battery that is not done (None when all are done)."""
        self.ensure_one()
        return self.ts_battery_siblings().filtered(lambda t: t.state != 'done')[:1]

    def ts_battery_earlier_open(self):
        """An attempt earlier in the battery that is not done yet (the player sends the participant there first)."""
        self.ensure_one()
        sib = self.ts_battery_siblings()
        if self.id not in sib.ids:
            return self.browse()
        return sib[:sib.ids.index(self.id)].filtered(lambda t: t.state != 'done')[:1]

    def ts_battery_label(self):
        """Player header: «مجموعهٔ X، سنجهٔ ۲ از ۵» (empty for a single attempt). A comma, never « · »: the middle dot
        next to a Persian digit reads as zero (UX audit G6-PT1)."""
        self.ensure_one()
        b = self.ts_battery()
        if not b:
            return ''
        return 'مجموعهٔ %s، سنجهٔ %s از %s' % (b.name, fa(self.ts_battery_index()), fa(len(self.ts_battery_siblings())))

    def ts_battery_info(self):
        """Consent page of the first attempt: the battery card, or None for a single attempt / a sibling."""
        self.ensure_one()
        b = self.ts_battery()
        if not b or self.ts_battery_first() != self:
            return None
        card = b.ts_card()
        card['shared'] = self.sudo().assignment_id.share_level not in (False, 'none')
        # size and total time from the same helper as the invitation page (ts_org effort_facts): a timed task is
        # counted in timed sections, never «۰ پرسش» (T7 integrator, A handoff W20)
        from odoo.addons.ts_org.controllers.main import effort_facts
        facts = effort_facts(None, battery=b, purpose=self.sudo().assignment_id.workspace_id.purpose)
        card['size'], card['time'] = facts['size'], facts['time']
        return card

    # ------------------------------------------------------------------ consent once, recorded per attempt
    def give_consent(self, research=False, role='self', subject=None):
        res = super().give_consent(research=research, role=role, subject=subject)
        if self.env.context.get('ts_battery_sibling'):
            return res
        for at in self:
            if at.state != 'in_progress' or not at.ts_battery() or at.ts_battery_first() != at:
                continue
            for sib in at.ts_battery_siblings() - at:
                if sib.state == 'consent':
                    sib.with_context(ts_battery_sibling=True).give_consent(research=research, role=role, subject=subject)
        return res

    def ts_battery_copy_consent(self):
        """A sibling opened while still in consent although the first attempt was agreed to (should not happen):
        give it the first attempt's consent values instead of showing a second consent page."""
        self.ensure_one()
        first = self.ts_battery_first()
        if self.state == 'consent' and first and first != self and first.state != 'consent' and first.consent_service:
            self.with_context(ts_battery_sibling=True).give_consent(
                research=first.consent_research, role=first.respondent_role or 'self', subject=first.subject_label)
        return self

    # ------------------------------------------------------------------ invitation lookups through assignment_id
    def ts_org_assignment(self):
        self.ensure_one()
        a = self.sudo().assignment_id
        if a.battery_id and a.user_id == self.user_id:
            return a
        return super().ts_org_assignment()

    def ts_shares(self):
        self.ensure_one()
        a = self.sudo().assignment_id
        if a.battery_id and a.user_id == self.user_id:
            return a
        return super().ts_shares()

    def ts_result_level(self, member):
        """A battery attempt answers with its invitation's level (the same for the whole battery), never more than
        'status' while it is not done. Single attempts: unchanged."""
        self.ensure_one()
        a = self.sudo().assignment_id
        if not a.battery_id or self.source == 'import':
            return super().ts_result_level(member)
        if self.workspace_id != member.workspace_id or a.workspace_id != member.workspace_id or not member.can_act():
            return 'none'
        level = a.result_level(member)
        if level not in ('none', 'status') and (self.state != 'done' or not self.released):
            return 'status'
        return level

    # ------------------------------------------------------------------ notifications once per battery
    def _ts_notify_done(self):
        self.ensure_one()
        a = self.sudo().assignment_id
        if not a.battery_id:
            return super()._ts_notify_done()
        if any(t.state != 'done' for t in a.attempt_ids):
            return None
        from odoo.addons.ts_panel.models.notify import _staff_users
        N = self.env['ts.notification']
        if self.user_id:
            N._notify(self.user_id, 'result_ready_participant', '/my/assessments/battery/%s' % a.id, self.workspace_id)
        if a.share_level != 'none':
            for u in _staff_users(a.workspace_id, a.client_id.responsible_id):
                N._notify(u, 'result_ready_staff', '/my/workspaces/%s/clients/%s' % (a.workspace_id.id, a.client_id.id),
                          a.workspace_id)
        return None

    def _ts_notify_result_ready(self):
        self.ensure_one()
        a = self.sudo().assignment_id
        if a.battery_id and any(t.state != 'done' for t in a.attempt_ids):
            return False                          # one result SMS per battery, when its last instrument is done
        return super()._ts_notify_result_ready()


class TsConsentRecordBattery(models.Model):
    """The minor's assent / the self-tester's guardian row is written by the consent route for the attempt whose page was
    shown (the first of a battery); the siblings get the same row, so the ledger stays one row per attempt."""
    _inherit = 'ts.consent.record'

    @api.model
    def _log(self, kind, user, assignment=None, attempt=None, workspace=None, level=False, version=False, method='checkbox',
             given_as='self', client=None):
        rec = super()._log(kind, user, assignment=assignment, attempt=attempt, workspace=workspace, level=level,
                           version=version, method=method, given_as=given_as, client=client)
        if attempt and kind in ('guardian', 'assent') and not self.env.context.get('ts_battery_sibling'):
            at = attempt.sudo()
            if at.ts_battery() and at.ts_battery_first() == at:
                for sib in at.ts_battery_siblings() - at:
                    self.with_context(ts_battery_sibling=True)._log(
                        kind, user, attempt=sib, workspace=sib.workspace_id, level=level, version=version, method=method,
                        given_as=given_as, client=sib.client_id if 'client_id' in sib._fields else client)
        return rec
