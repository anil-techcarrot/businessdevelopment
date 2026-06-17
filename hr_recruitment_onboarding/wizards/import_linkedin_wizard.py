# -*- coding: utf-8 -*-
import requests
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class HrLinkedInImportWizard(models.TransientModel):
    """
    Import a candidate profile from LinkedIn URL.
    Uses LinkedIn's public profile scraping or official LinkedIn API
    (requires LinkedIn Partner Program access for full data).
    For Community edition: basic URL storage + manual fill.
    For Enterprise / LinkedIn API: full profile sync.
    """
    _name = 'hr.linkedin.import.wizard'
    _description = 'Import LinkedIn Candidate Profile'

    job_id = fields.Many2one('hr.job', string='Job Position', required=True)
    linkedin_url = fields.Char(
        string='LinkedIn Profile URL',
        placeholder='https://www.linkedin.com/in/candidate-name',
        required=True
    )
    # Pre-filled from LinkedIn (if API available)
    candidate_name  = fields.Char(string='Full Name')
    email           = fields.Char(string='Email')
    phone           = fields.Char(string='Phone')
    headline        = fields.Char(string='Headline / Title')
    location        = fields.Char(string='Location')
    summary         = fields.Text(string='About / Summary')
    skills_text     = fields.Text(string='Skills (comma separated)')

    use_api = fields.Boolean(
        string='Use LinkedIn API',
        default=False,
        help='If enabled, fetch profile data via LinkedIn API. '
             'Requires LinkedIn Partner token in Settings.'
    )

    def action_fetch_profile(self):
        """
        Attempt to fetch basic profile data from LinkedIn.
        Full data requires LinkedIn Recruiter API / Partner access.
        """
        self.ensure_one()
        if not self.use_api:
            return  # Manual fill mode

        li_token = self.env['ir.config_parameter'].sudo().get_param(
            'hr_recruitment_onboarding.linkedin_api_token'
        )
        if not li_token:
            raise UserError(_(
                'LinkedIn API token not configured.\n'
                'Go to Settings → Recruitment Settings → LinkedIn.'
            ))

        try:
            # LinkedIn Profile API (requires r_liteprofile + r_emailaddress scope)
            headers = {'Authorization': f'Bearer {li_token}'}
            profile_resp = requests.get(
                'https://api.linkedin.com/v2/me',
                headers=headers, timeout=10
            )
            profile_resp.raise_for_status()
            data = profile_resp.json()
            self.candidate_name = (
                data.get('localizedFirstName', '') + ' ' +
                data.get('localizedLastName', '')
            ).strip()
            self.headline = data.get('localizedHeadline', '')
        except Exception as e:
            _logger.error('LinkedIn API fetch failed: %s', e)
            raise UserError(_(
                'Could not fetch LinkedIn profile.\n'
                'Error: %s\n\n'
                'You can fill the details manually and proceed.'
            ) % str(e))

    def action_import(self):
        """Create an hr.applicant from the LinkedIn profile data."""
        self.ensure_one()
        if not self.candidate_name:
            raise UserError(_('Please provide at least the candidate name.'))

        # Create or find partner
        partner = self.env['res.partner'].search(
            [('email', '=', self.email)], limit=1
        ) if self.email else self.env['res.partner']

        if not partner and self.candidate_name:
            partner = self.env['res.partner'].create({
                'name': self.candidate_name,
                'email': self.email or '',
                'phone': self.phone or '',
            })

        # Build skills tags
        tag_ids = []
        if self.skills_text:
            for skill in self.skills_text.split(','):
                skill = skill.strip()
                if skill:
                    tag = self.env['hr.applicant.category'].search(
                        [('name', 'ilike', skill)], limit=1
                    )
                    if not tag:
                        tag = self.env['hr.applicant.category'].create({'name': skill})
                    tag_ids.append(tag.id)

        applicant_vals = {
            'partner_name': self.candidate_name,
            'job_id': self.job_id.id,
            'department_id': self.job_id.department_id.id,
            'email_from': self.email or '',
            'partner_phone': self.phone or '',
            'linkedin_profile': self.linkedin_url,
            'linkedin_imported': True,
            'source_channel': 'linkedin',
            'description': self.summary or '',
            'categ_ids': [(6, 0, tag_ids)] if tag_ids else [],
            'partner_id': partner.id if partner else False,
        }
        applicant = self.env['hr.applicant'].create(applicant_vals)

        # Auto-trigger AI scoring if enabled
        if self.env['ir.config_parameter'].sudo().get_param(
            'hr_recruitment_onboarding.ai_auto_score'
        ):
            try:
                applicant.action_compute_ai_score()
            except Exception:
                pass  # Don't block import if AI fails

        return {
            'type': 'ir.actions.act_window',
            'name': _('Applicant'),
            'res_model': 'hr.applicant',
            'res_id': applicant.id,
            'view_mode': 'form',
        }
