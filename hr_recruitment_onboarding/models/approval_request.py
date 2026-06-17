# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
import datetime


class HrRecruitmentApproval(models.Model):
    _name = 'hr.recruitment.approval'
    _description = 'Recruitment Approval Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'create_date desc'

    name = fields.Char(
        string='Reference', readonly=True, copy=False,
        default=lambda self: _('New')
    )
    approval_type = fields.Selection([
        ('headcount', 'Headcount Request'),
        ('offer',     'Offer Approval'),
    ], string='Type', required=True, default='offer', tracking=True)

    job_id = fields.Many2one('hr.job', string='Job Position', tracking=True)
    applicant_id = fields.Many2one('hr.applicant', string='Applicant', tracking=True)
    department_id = fields.Many2one(
        'hr.department', related='job_id.department_id', store=True
    )
    offered_salary = fields.Monetary(
        string='Offered Salary', currency_field='currency_id', tracking=True
    )
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id
    )
    reason = fields.Text(string='Justification')

    state = fields.Selection([
        ('draft',    'Draft'),
        ('pending',  'Pending Approval'),
        ('approved', 'Approved'),
        ('refused',  'Refused'),
        ('cancelled','Cancelled'),
    ], string='Status', default='draft', tracking=True)

    approver_ids = fields.One2many(
        'hr.recruitment.approval.line', 'approval_id', string='Approvers'
    )
    current_level = fields.Integer(
        string='Current Approval Level', default=1, readonly=True
    )
    deadline = fields.Datetime(
        string='Response Deadline',
        default=lambda self: fields.Datetime.now() + datetime.timedelta(hours=48)
    )
    refused_reason = fields.Text(string='Refusal Reason')

    # ─────────────────────────────────────────────────────────────
    # ORM
    # ─────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                seq = 'hr_recruitment_onboarding.seq_recruitment_approval'
                vals['name'] = self.env['ir.sequence'].next_by_code(seq) or _('New')
        return super().create(vals_list)

    # ─────────────────────────────────────────────────────────────
    # Workflow
    # ─────────────────────────────────────────────────────────────

    def action_submit(self):
        self.write({'state': 'pending', 'current_level': 1})
        self._notify_current_approver()
        self.message_post(body=_('Approval request submitted.'))

    def action_approve(self):
        self.ensure_one()
        current_user = self.env.user
        approver_line = self.approver_ids.filtered(
            lambda l: l.approver_id == current_user and l.level == self.current_level
        )
        if not approver_line:
            raise UserError(_('You are not the current approver for this request.'))

        approver_line.write({
            'state': 'approved',
            'approved_date': fields.Datetime.now(),
        })

        next_level_approvers = self.approver_ids.filtered(
            lambda l: l.level == self.current_level + 1
        )
        if next_level_approvers:
            self.current_level += 1
            self._notify_current_approver()
            self.message_post(
                body=_('Level %d approved. Waiting for level %d approval.') % (
                    self.current_level - 1, self.current_level
                )
            )
        else:
            # All levels approved
            self.write({'state': 'approved'})
            self._on_fully_approved()

    def action_refuse(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Refuse Approval'),
            'res_model': 'hr.recruitment.refuse.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_approval_id': self.id},
        }

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def _on_fully_approved(self):
        """Called when all approval levels pass."""
        self.message_post(body=_('✅ Fully approved by all approvers.'))
        if self.approval_type == 'offer' and self.applicant_id:
            self.applicant_id.write({'offer_state': 'sent'})
            # Send offer email to candidate
            template = self.env.ref(
                'hr_recruitment_onboarding.email_template_offer_approved',
                raise_if_not_found=False
            )
            if template and self.applicant_id.partner_id:
                template.send_mail(self.applicant_id.id, force_send=True)
        elif self.approval_type == 'headcount' and self.job_id:
            self.job_id.headcount_approved = True

    def _notify_current_approver(self):
        """Send notification to the current level's approver."""
        approver_lines = self.approver_ids.filtered(
            lambda l: l.level == self.current_level
        )
        for line in approver_lines:
            if line.approver_id.partner_id:
                self.message_post(
                    body=_('Approval required from: <b>%s</b>') % line.approver_id.name,
                    partner_ids=[line.approver_id.partner_id.id],
                )
                self.env['mail.activity'].create({
                    'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
                    'note': _('Please review and approve/refuse this recruitment request.'),
                    'user_id': line.approver_id.id,
                    'res_model_id': self.env['ir.model']._get_id(self._name),
                    'res_id': self.id,
                    'date_deadline': fields.Date.today() + datetime.timedelta(days=2),
                })

    # ─────────────────────────────────────────────────────────────
    # Escalation (called by scheduled action)
    # ─────────────────────────────────────────────────────────────

    @api.model
    def _escalate_overdue_approvals(self):
        """Auto-escalate approvals past their deadline."""
        overdue = self.search([
            ('state', '=', 'pending'),
            ('deadline', '<', fields.Datetime.now()),
        ])
        for approval in overdue:
            approval.message_post(
                body=_('⚠️ Approval overdue. Escalating to next level / HR Manager.')
            )


class HrRecruitmentApprovalLine(models.Model):
    _name = 'hr.recruitment.approval.line'
    _description = 'Approval Line'
    _order = 'level'

    approval_id = fields.Many2one(
        'hr.recruitment.approval', string='Approval', required=True, ondelete='cascade'
    )
    level = fields.Integer(string='Level', required=True, default=1)
    role = fields.Char(string='Role', default='Approver')
    approver_id = fields.Many2one('res.users', string='Approver', required=True)
    state = fields.Selection([
        ('pending',  'Pending'),
        ('approved', 'Approved'),
        ('refused',  'Refused'),
    ], string='Status', default='pending')
    approved_date = fields.Datetime(string='Approved On', readonly=True)
    notes = fields.Text(string='Notes')


class HrRecruitmentRefuseWizard(models.TransientModel):
    _name = 'hr.recruitment.refuse.wizard'
    _description = 'Refuse Approval Wizard'

    approval_id = fields.Many2one('hr.recruitment.approval', required=True)
    reason = fields.Text(string='Reason for Refusal', required=True)

    def action_refuse(self):
        self.approval_id.write({
            'state': 'refused',
            'refused_reason': self.reason,
        })
        self.approval_id.message_post(
            body=_('❌ Refused by %s.\nReason: %s') % (
                self.env.user.name, self.reason
            )
        )
        if self.approval_id.applicant_id:
            self.approval_id.applicant_id.write({'offer_state': 'declined'})
