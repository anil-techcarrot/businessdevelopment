# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
import datetime


class HrOnboardingTask(models.Model):
    _name = 'hr.onboarding.task'
    _description = 'Onboarding Task'
    _inherit = ['mail.thread']
    _order = 'sequence, due_date, id'

    onboarding_id = fields.Many2one(
        'hr.onboarding', string='Onboarding Plan',
        required=True, ondelete='cascade'
    )
    name = fields.Char(string='Task', required=True)
    description = fields.Text(string='Description / Instructions')
    sequence = fields.Integer(string='Sequence', default=10)

    category = fields.Selection([
        ('it',       'IT Setup'),
        ('legal',    'Legal & Compliance'),
        ('training', 'Training'),
        ('admin',    'Administration'),
        ('payroll',  'Payroll'),
        ('review',   'Review & Feedback'),
        ('other',    'Other'),
    ], string='Category', default='other')

    responsible_role = fields.Selection([
        ('hr',       'HR Team'),
        ('manager',  'Line Manager'),
        ('it_team',  'IT Team'),
        ('buddy',    'Onboarding Buddy'),
        ('employee', 'New Employee'),
    ], string='Responsible Role', default='hr')

    assigned_to_id = fields.Many2one('res.users', string='Assigned To')

    state = fields.Selection([
        ('pending',     'Pending'),
        ('in_progress', 'In Progress'),
        ('done',        'Done'),
        ('skipped',     'Skipped'),
    ], string='Status', default='pending', tracking=True)

    due_days = fields.Integer(string='Due After (Days)', default=7)
    due_date = fields.Date(string='Due Date', tracking=True)
    completed_date = fields.Date(string='Completed On', readonly=True)
    mandatory = fields.Boolean(string='Mandatory', default=False)
    is_overdue = fields.Boolean(
        string='Overdue', compute='_compute_is_overdue', store=True
    )

    document_ids = fields.Many2many(
        'ir.attachment', string='Documents',
        help='Attach relevant documents, forms, or policies.'
    )
    notes = fields.Text(string='Completion Notes')

    # ─────────────────────────────────────────────────────────────
    # Computes
    # ─────────────────────────────────────────────────────────────

    @api.depends('due_date', 'state')
    def _compute_is_overdue(self):
        today = fields.Date.today()
        for task in self:
            task.is_overdue = (
                task.due_date and
                task.due_date < today and
                task.state not in ('done', 'skipped')
            )

    # ─────────────────────────────────────────────────────────────
    # State transitions
    # ─────────────────────────────────────────────────────────────

    def action_start(self):
        self.write({'state': 'in_progress'})

    def action_done(self):
        self.write({
            'state': 'done',
            'completed_date': fields.Date.today(),
        })
        # Check if all tasks done → auto-complete onboarding
        if all(t.state in ('done', 'skipped') for t in self.onboarding_id.task_ids):
            self.onboarding_id.message_post(
                body=_('🎉 All onboarding tasks completed!')
            )

    def action_skip(self):
        if self.mandatory:
            raise UserError(_('Mandatory tasks cannot be skipped.'))
        self.write({'state': 'skipped'})

    def action_reset(self):
        self.write({'state': 'pending', 'completed_date': False})

    # ─────────────────────────────────────────────────────────────
    # Overdue reminder (called by scheduled action)
    # ─────────────────────────────────────────────────────────────

    @api.model
    def _send_overdue_reminders(self):
        overdue_tasks = self.search([
            ('state', 'not in', ['done', 'skipped']),
            ('due_date', '<', fields.Date.today()),
        ])
        for task in overdue_tasks:
            task.onboarding_id.message_post(
                body=_('⚠️ Overdue task: <b>%s</b> was due on %s') % (
                    task.name, task.due_date
                ),
                partner_ids=task.onboarding_id.hr_responsible_id.user_id.partner_id.ids,
            )
