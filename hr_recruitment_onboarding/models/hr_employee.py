# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    onboarding_ids = fields.One2many(
        'hr.onboarding', 'employee_id', string='Onboarding Plans'
    )
    onboarding_count = fields.Integer(
        string='Onboarding Plans',
        compute='_compute_onboarding_count',
        store=True
    )
    onboarding_progress = fields.Float(
        string='Onboarding Progress (%)',
        compute='_compute_onboarding_count',
        store=True
    )

    @api.depends('onboarding_ids', 'onboarding_ids.state')
    def _compute_onboarding_count(self):
        for emp in self:
            plans = emp.onboarding_ids.filtered(
                lambda o: o.state != 'cancelled'
            )
            emp.onboarding_count = len(plans)
            emp.onboarding_progress = plans[0].progress if plans else 0.0

    def action_view_onboarding(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Onboarding Plans'),
            'res_model': 'hr.onboarding',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }