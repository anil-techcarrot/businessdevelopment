# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class HrOnboarding(models.Model):
    _name = 'hr.onboarding'
    _description = 'Employee Onboarding Plan'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'start_date desc, id desc'

    name = fields.Char(
        string='Onboarding Plan', compute='_compute_name', store=True
    )
    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True,
        ondelete='cascade', tracking=True
    )
    job_id = fields.Many2one('hr.job', string='Job Position', tracking=True)
    department_id = fields.Many2one('hr.department', string='Department', tracking=True)
    applicant_id = fields.Many2one('hr.applicant', string='From Application')
    buddy_id = fields.Many2one(
        'hr.employee', string='Onboarding Buddy',
        help='Experienced employee assigned to guide the new hire',
        tracking=True
    )
    hr_responsible_id = fields.Many2one(
        'hr.employee', string='HR Responsible', tracking=True
    )
    start_date = fields.Date(
        string='Start Date', default=fields.Date.today, required=True, tracking=True
    )
    end_date = fields.Date(string='Expected End Date', tracking=True)

    state = fields.Selection([
        ('draft',       'Draft'),
        ('in_progress', 'In Progress'),
        ('done',        'Completed'),
        ('cancelled',   'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    task_ids = fields.One2many(
        'hr.onboarding.task', 'onboarding_id', string='Tasks'
    )
    task_count = fields.Integer(
        string='Total Tasks', compute='_compute_task_stats'
    )
    task_done_count = fields.Integer(
        string='Done Tasks', compute='_compute_task_stats'
    )
    progress = fields.Float(
        string='Progress (%)', compute='_compute_task_stats', store=True
    )

    notes = fields.Html(string='Notes & Welcome Message')

    # ─────────────────────────────────────────────────────────────
    # Computes
    # ─────────────────────────────────────────────────────────────

    @api.depends('employee_id', 'start_date')
    def _compute_name(self):
        for rec in self:
            emp = rec.employee_id.name or ''
            date = rec.start_date.strftime('%b %Y') if rec.start_date else ''
            rec.name = f"Onboarding – {emp} ({date})" if emp else 'New Onboarding'

    @api.depends('task_ids.state')
    def _compute_task_stats(self):
        for rec in self:
            tasks = rec.task_ids
            total = len(tasks)
            done = len(tasks.filtered(lambda t: t.state == 'done'))
            rec.task_count = total
            rec.task_done_count = done
            rec.progress = (done / total * 100) if total else 0.0

    # ─────────────────────────────────────────────────────────────
    # Task generation
    # ─────────────────────────────────────────────────────────────

    def _generate_tasks(self):
        """Auto-generate tasks based on department template or default list."""
        self.ensure_one()
        templates = self.env['hr.onboarding.task.template'].search([
            '|',
            ('department_id', '=', self.department_id.id),
            ('department_id', '=', False),  # Global tasks
        ], order='sequence')

        if templates:
            for tmpl in templates:
                self.env['hr.onboarding.task'].create({
                    'onboarding_id': self.id,
                    'name': tmpl.name,
                    'description': tmpl.description,
                    'category': tmpl.category,
                    'responsible_role': tmpl.responsible_role,
                    'due_days': tmpl.due_days,
                    'due_date': fields.Date.today() + \
                        __import__('datetime').timedelta(days=tmpl.due_days or 7),
                    'sequence': tmpl.sequence,
                })
        else:
            self._generate_default_tasks()

    def _generate_default_tasks(self):
        """Fallback default tasks if no templates configured."""
        defaults = [
            ('IT Setup – Create email & system accounts',         'it',       'hr',        1,  1),
            ('Sign Employment Contract',                           'legal',    'hr',        1,  2),
            ('Sign NDA & Company Policies',                        'legal',    'hr',        2,  3),
            ('Office Tour & Introductions',                        'admin',    'buddy',     1,  4),
            ('Department Overview Meeting',                        'training', 'manager',   3,  5),
            ('Complete Compliance Training',                       'training', 'employee',  7,  6),
            ('Complete Role-Specific Training',                    'training', 'employee',  14, 7),
            ('Setup Workstation & Tools',                          'it',       'it_team',   2,  8),
            ('Add to Payroll',                                     'payroll',  'hr',        1,  9),
            ('30-Day Check-in with Manager',                       'review',   'manager',   30, 10),
            ('90-Day Probation Review',                            'review',   'manager',   90, 11),
        ]
        for name, category, role, days, seq in defaults:
            due = fields.Date.today() + __import__('datetime').timedelta(days=days)
            self.env['hr.onboarding.task'].create({
                'onboarding_id': self.id,
                'name': name,
                'category': category,
                'responsible_role': role,
                'due_days': days,
                'due_date': due,
                'sequence': seq,
            })

    # ─────────────────────────────────────────────────────────────
    # State transitions
    # ─────────────────────────────────────────────────────────────

    def action_start(self):
        self.write({'state': 'in_progress'})
        self._send_welcome_notification()

    def action_done(self):
        if any(t.state != 'done' for t in self.task_ids.filtered(lambda t: t.mandatory)):
            raise UserError(_(
                'All mandatory tasks must be completed before closing the onboarding plan.'
            ))
        self.write({'state': 'done'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})

    # ─────────────────────────────────────────────────────────────
    # Notifications
    # ─────────────────────────────────────────────────────────────

    def _send_welcome_notification(self):
        template = self.env.ref(
            'hr_recruitment_onboarding.email_template_onboarding_welcome',
            raise_if_not_found=False
        )
        if template and self.employee_id.work_email:
            template.send_mail(self.id, force_send=True)


class HrOnboardingTaskTemplate(models.Model):
    _name = 'hr.onboarding.task.template'
    _description = 'Onboarding Task Template'
    _order = 'sequence, id'

    name = fields.Char(string='Task Name', required=True)
    description = fields.Text(string='Description')
    department_id = fields.Many2one(
        'hr.department', string='Department',
        help='Leave empty to apply to all departments.'
    )
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
    ], string='Responsible', default='hr')
    due_days = fields.Integer(string='Due After (Days)', default=7)
    sequence = fields.Integer(string='Sequence', default=10)
    mandatory = fields.Boolean(string='Mandatory', default=False)
