# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrRecruitmentOfferWizard(models.TransientModel):
    _name = 'hr.recruitment.offer.wizard'
    _description = 'Send Offer to Candidate'

    applicant_id = fields.Many2one('hr.applicant', required=True, readonly=True)
    candidate_name = fields.Char(related='applicant_id.partner_name', readonly=True)
    job_name = fields.Char(related='applicant_id.job_id.name', readonly=True)

    offered_salary = fields.Monetary(
        string='Offered Salary',
        currency_field='currency_id',
        default=lambda self: self.applicant_id.offer_salary
    )
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id
    )
    joining_date = fields.Date(
        string='Proposed Start Date',
        default=fields.Date.today
    )
    offer_expiry = fields.Date(string='Offer Expires On')
    email_to = fields.Char(
        string='Send To',
        compute='_compute_email_to', store=True, readonly=False
    )
    subject = fields.Char(string='Email Subject')
    body_html = fields.Html(string='Message Body')
    require_approval = fields.Boolean(
        string='Require Approval First',
        default=lambda self: self.env['ir.config_parameter'].sudo().get_param(
            'hr_recruitment_onboarding.offer_approval_required', default=True
        )
    )

    @api.depends('applicant_id')
    def _compute_email_to(self):
        for wiz in self:
            wiz.email_to = (
                wiz.applicant_id.partner_id.email or
                wiz.applicant_id.email_from or ''
            )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if res.get('applicant_id'):
            applicant = self.env['hr.applicant'].browse(res['applicant_id'])
            res.update({
                'subject': f"Job Offer – {applicant.job_id.name} at {applicant.company_id.name}",
                'offered_salary': applicant.offer_salary or 0,
            })
        return res

    def action_send(self):
        self.ensure_one()
        if not self.email_to:
            raise UserError(_('No email address found for this candidate.'))

        # Save offer details to applicant
        self.applicant_id.write({
            'offer_salary': self.offered_salary,
            'offer_joining_date': self.joining_date,
            'offer_expiry_date': self.offer_expiry,
            'offer_state': 'sent',
        })

        if self.require_approval and not self.applicant_id.approval_state == 'approved':
            # Request approval first
            self.applicant_id.action_request_approval()
        else:
            # Send directly
            template = self.env.ref(
                'hr_recruitment_onboarding.email_template_offer_approved',
                raise_if_not_found=False
            )
            if template:
                template.send_mail(self.applicant_id.id, force_send=True)
            else:
                # Fallback: send composed email
                mail = self.env['mail.mail'].create({
                    'subject': self.subject,
                    'body_html': self.body_html,
                    'email_to': self.email_to,
                    'res_id': self.applicant_id.id,
                    'model': 'hr.applicant',
                })
                mail.send()

            self.applicant_id.message_post(
                body=_('Offer sent to candidate: %s') % self.email_to
            )

        return {'type': 'ir.actions.act_window_close'}
