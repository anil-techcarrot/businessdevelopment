# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class HrJob(models.Model):
    _inherit = 'hr.job'

    # ── Social media settings ─────────────────────────────────────
    auto_post_social = fields.Boolean(
        string='Auto-Post on Social Media',
        default=True,
        help='Automatically post this job to all connected social media accounts '
             'when the position is published.'
    )
    social_post_ids = fields.One2many(
        'social.post', 'hr_job_id',
        string='Social Media Posts'
    )
    social_post_count = fields.Integer(
        string='Social Posts', compute='_compute_social_post_count'
    )
    last_social_post_date = fields.Datetime(
        string='Last Posted', compute='_compute_social_post_count', store=True
    )

    # ── AI configuration per job ──────────────────────────────────
    ai_screening_enabled = fields.Boolean(
        string='Enable AI Screening', default=True,
        help='Automatically score incoming applicants using AI.'
    )
    required_skills_text = fields.Text(
        string='Required Skills (for AI)',
        help='Plain-text list of required skills. AI uses this for matching.'
    )
    min_ai_score = fields.Float(
        string='Minimum AI Score to Shortlist', default=60.0,
        help='Applicants below this score are moved to "Needs Review" stage.'
    )

    # ── Headcount approval ────────────────────────────────────────
    headcount_approval_id = fields.Many2one(
        'hr.recruitment.approval', string='Headcount Approval'
    )
    headcount_approved = fields.Boolean(
        string='Headcount Approved', default=False, tracking=True
    )

    # ── Extra metadata ────────────────────────────────────────────
    salary_min = fields.Monetary(
        string='Salary Min', currency_field='currency_id'
    )
    salary_max = fields.Monetary(
        string='Salary Max', currency_field='currency_id'
    )
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id
    )
    employment_type = fields.Selection([
        ('full_time',  'Full Time'),
        ('part_time',  'Part Time'),
        ('contract',   'Contract'),
        ('internship', 'Internship'),
        ('freelance',  'Freelance'),
    ], string='Employment Type', default='full_time')
    work_mode = fields.Selection([
        ('onsite',  'On-site'),
        ('remote',  'Remote'),
        ('hybrid',  'Hybrid'),
    ], string='Work Mode', default='onsite')
    application_deadline = fields.Date(string='Application Deadline')

    # ─────────────────────────────────────────────────────────────
    # Computes
    # ─────────────────────────────────────────────────────────────

    def _compute_social_post_count(self):
        for job in self:
            posts = job.social_post_ids
            job.social_post_count = len(posts)
            job.last_social_post_date = max(
                posts.mapped('published_date'), default=False
            ) if posts else False

    # ─────────────────────────────────────────────────────────────
    # Override set_recruit — auto-post when job goes live
    # ─────────────────────────────────────────────────────────────

    def set_recruit(self):
        """Called when job status changes to 'In Recruitment'."""
        res = super().set_recruit()
        for job in self.filtered('auto_post_social'):
            job._post_to_social_media()
        return res

    # ─────────────────────────────────────────────────────────────
    # Social media posting
    # ─────────────────────────────────────────────────────────────

    def _post_to_social_media(self):
        """
        Create social.post records for every connected social account
        and publish them immediately.
        """
        self.ensure_one()

        # Get all connected social accounts
        social_accounts = self.env['social.account'].search([
            ('has_account_option_post', '=', True)
        ])
        if not social_accounts:
            _logger.warning(
                'No social media accounts connected. '
                'Configure them in Social Marketing → Configuration → Social Accounts.'
            )
            return

        message = self._build_social_post_message()
        post_vals = {
            'account_ids': [(6, 0, social_accounts.ids)],
            'message': message,
            'hr_job_id': self.id,
            'state': 'posted',
            'post_method': 'now',
        }

        try:
            post = self.env['social.post'].create(post_vals)
            post.action_post()
            _logger.info(
                'Job "%s" auto-posted to %d social account(s).',
                self.name, len(social_accounts)
            )
            self.message_post(
                body=_('Job position auto-posted to: %s') % ', '.join(
                    social_accounts.mapped('name')
                )
            )
        except Exception as e:
            _logger.error('Social media post failed for job %s: %s', self.name, e)

    def _build_social_post_message(self):
        """Compose the social media post text."""
        lines = [f"🚀 We're Hiring! – {self.name}"]
        if self.department_id:
            lines.append(f"📂 Department: {self.department_id.name}")
        if self.work_mode:
            mode_labels = dict(self._fields['work_mode'].selection)
            lines.append(f"🏢 Mode: {mode_labels.get(self.work_mode, '')}")
        if self.employment_type:
            type_labels = dict(self._fields['employment_type'].selection)
            lines.append(f"⏱ Type: {type_labels.get(self.employment_type, '')}")
        if self.salary_min and self.salary_max:
            lines.append(
                f"💰 Salary: {self.currency_id.symbol}{self.salary_min:,.0f}"
                f" – {self.currency_id.symbol}{self.salary_max:,.0f}"
            )
        if self.application_deadline:
            lines.append(f"📅 Apply by: {self.application_deadline.strftime('%d %b %Y')}")
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        apply_url = f"{base_url}/jobs"
        lines.append(f"\n🔗 Apply now: {apply_url}")
        lines.append("\n#Hiring #Jobs #Careers #WeAreHiring")
        return '\n'.join(lines)

    # ─────────────────────────────────────────────────────────────
    # Manual re-post action
    # ─────────────────────────────────────────────────────────────

    def action_post_to_social_media(self):
        """Manual button to re-post the job."""
        self._post_to_social_media()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Posted!'),
                'message': _('Job "%s" posted to all connected social media accounts.') % self.name,
                'type': 'success',
            }
        }

    def action_view_social_posts(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Social Media Posts'),
            'res_model': 'social.post',
            'view_mode': 'list,form',
            'domain': [('hr_job_id', '=', self.id)],
        }

    def action_request_headcount_approval(self):
        self.ensure_one()
        approval = self.env['hr.recruitment.approval'].create({
            'job_id': self.id,
            'approval_type': 'headcount',
        })
        self.headcount_approval_id = approval
        approval.action_submit()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Headcount Approval'),
            'res_model': 'hr.recruitment.approval',
            'res_id': approval.id,
            'view_mode': 'form',
        }


class SocialPost(models.Model):
    """Extend social.post to link back to hr.job."""
    _inherit = 'social.post'

    hr_job_id = fields.Many2one('hr.job', string='Related Job Position', ondelete='set null')
