# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request
from odoo.exceptions import AccessError
import logging

_logger = logging.getLogger(__name__)


class RecruitmentPortalController(http.Controller):

    # ── Candidate application status page ────────────────────────
    @http.route(
        '/jobs/application/<int:applicant_id>/<string:token>',
        type='http', auth='public', website=True
    )
    def application_status(self, applicant_id, token, **kwargs):
        applicant = request.env['hr.applicant'].sudo().browse(applicant_id)
        if not applicant.exists() or applicant.access_token != token:
            return request.not_found()

        values = {
            'applicant': applicant,
            'stages': request.env['hr.recruitment.stage'].sudo().search(
                [], order='sequence'
            ),
            'page_name': 'application_status',
        }
        return request.render(
            'hr_recruitment_onboarding.portal_application_status', values
        )

    # ── Accept offer ─────────────────────────────────────────────
    @http.route(
        '/jobs/application/<int:applicant_id>/<string:token>/accept',
        type='http', auth='public', website=True, methods=['POST']
    )
    def accept_offer(self, applicant_id, token, **kwargs):
        applicant = request.env['hr.applicant'].sudo().browse(applicant_id)
        if not applicant.exists() or applicant.access_token != token:
            return request.not_found()

        applicant.write({'offer_state': 'accepted'})
        applicant.message_post(
            body=_('✅ Candidate accepted the offer via portal.')
        )
        return request.redirect(
            f'/jobs/application/{applicant_id}/{token}?accepted=1'
        )

    # ── Decline offer ─────────────────────────────────────────────
    @http.route(
        '/jobs/application/<int:applicant_id>/<string:token>/decline',
        type='http', auth='public', website=True, methods=['POST']
    )
    def decline_offer(self, applicant_id, token, **kwargs):
        applicant = request.env['hr.applicant'].sudo().browse(applicant_id)
        if not applicant.exists() or applicant.access_token != token:
            return request.not_found()

        reason = kwargs.get('reason', '')
        applicant.write({'offer_state': 'declined'})
        applicant.message_post(
            body=_('❌ Candidate declined the offer via portal. Reason: %s') % reason
        )
        return request.redirect(
            f'/jobs/application/{applicant_id}/{token}?declined=1'
        )

    # ── Public job listings ───────────────────────────────────────
    @http.route('/jobs', type='http', auth='public', website=True)
    def job_listings(self, **kwargs):
        jobs = request.env['hr.job'].sudo().search([
            ('website_published', '=', True)
        ], order='sequence, name')
        values = {
            'jobs': jobs,
            'page_name': 'jobs',
        }
        return request.render(
            'hr_recruitment_onboarding.website_jobs_list', values
        )

    # ── Single job detail + apply form ───────────────────────────
    @http.route('/jobs/<int:job_id>', type='http', auth='public', website=True)
    def job_detail(self, job_id, **kwargs):
        job = request.env['hr.job'].sudo().browse(job_id)
        if not job.exists():
            return request.not_found()
        values = {
            'job': job,
            'page_name': 'job_detail',
        }
        return request.render(
            'hr_recruitment_onboarding.website_job_detail', values
        )

    # ── Submit application ────────────────────────────────────────
    @http.route(
        '/jobs/<int:job_id>/apply',
        type='http', auth='public', website=True, methods=['POST']
    )
    def apply_job(self, job_id, **kwargs):
        job = request.env['hr.job'].sudo().browse(job_id)
        if not job.exists():
            return request.not_found()

        name    = kwargs.get('candidate_name', '').strip()
        email   = kwargs.get('email', '').strip()
        phone   = kwargs.get('phone', '').strip()
        linkedin = kwargs.get('linkedin_url', '').strip()
        cover   = kwargs.get('cover_letter', '').strip()

        if not name or not email:
            return request.redirect(f'/jobs/{job_id}?error=missing_fields')

        applicant = request.env['hr.applicant'].sudo().create({
            'partner_name': name,
            'email_from': email,
            'partner_phone': phone,
            'job_id': job_id,
            'department_id': job.department_id.id,
            'description': cover,
            'linkedin_profile': linkedin,
            'source_channel': 'website',
        })

        # Handle resume upload
        resume_file = kwargs.get('resume')
        if resume_file and hasattr(resume_file, 'read'):
            import base64
            request.env['ir.attachment'].sudo().create({
                'name': resume_file.filename,
                'res_model': 'hr.applicant',
                'res_id': applicant.id,
                'datas': base64.b64encode(resume_file.read()),
                'mimetype': resume_file.content_type,
            })

        return request.redirect(
            f'/jobs/application/{applicant.id}/{applicant.access_token}'
        )


class OnboardingPortalController(http.Controller):
    """Employee self-service onboarding portal."""

    @http.route('/onboarding', type='http', auth='user', website=True)
    def my_onboarding(self, **kwargs):
        employee = request.env['hr.employee'].sudo().search([
            ('user_id', '=', request.env.user.id)
        ], limit=1)
        if not employee:
            return request.redirect('/')

        onboarding = request.env['hr.onboarding'].sudo().search([
            ('employee_id', '=', employee.id),
            ('state', '!=', 'cancelled'),
        ], limit=1, order='start_date desc')

        values = {
            'employee': employee,
            'onboarding': onboarding,
            'page_name': 'onboarding',
        }
        return request.render(
            'hr_recruitment_onboarding.portal_onboarding', values
        )

    @http.route(
        '/onboarding/task/<int:task_id>/done',
        type='json', auth='user'
    )
    def mark_task_done(self, task_id, **kwargs):
        task = request.env['hr.onboarding.task'].sudo().browse(task_id)
        employee = request.env['hr.employee'].sudo().search([
            ('user_id', '=', request.env.user.id)
        ], limit=1)
        if task.exists() and task.onboarding_id.employee_id == employee:
            task.action_done()
            return {'success': True, 'progress': task.onboarding_id.progress}
        return {'success': False}
