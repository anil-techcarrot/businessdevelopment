# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ── AI Provider ───────────────────────────────────────────────
    ai_provider = fields.Selection([
        ('groq',       'Groq (Free – Recommended)'),
        ('gemini',     'Google Gemini (Free)'),
        ('ollama',     'Ollama (Local / On-premise)'),
        ('rule_based', 'Rule-Based Scoring (No API needed)'),
    ], string='AI Provider',
        config_parameter='hr_recruitment_onboarding.ai_provider',
        default='groq',
        help='Groq is recommended: free, fast (0.5s), 14,400 requests/day, no credit card.'
    )

    # ── Groq ──────────────────────────────────────────────────────
    groq_api_key = fields.Char(
        string='Groq API Key',
        config_parameter='hr_recruitment_onboarding.groq_api_key',
        help='Free at console.groq.com — no credit card required. '
             'Supports Llama 3.3 70B, Mixtral 8x7B and more.'
    )
    groq_model = fields.Selection([
        ('llama-3.3-70b-versatile',  'Llama 3.3 70B (Best quality)'),
        ('llama3-8b-8192',           'Llama 3 8B (Faster)'),
        ('mixtral-8x7b-32768',       'Mixtral 8x7B (Balanced)'),
        ('gemma2-9b-it',             'Gemma 2 9B (Lightweight)'),
    ], string='Groq Model',
        config_parameter='hr_recruitment_onboarding.groq_model',
        default='llama-3.3-70b-versatile'
    )

    # ── Google Gemini ─────────────────────────────────────────────
    gemini_api_key = fields.Char(
        string='Google Gemini API Key',
        config_parameter='hr_recruitment_onboarding.gemini_api_key',
        help='Free at aistudio.google.com — 1,500 requests/day free. '
             'No billing required for free tier.'
    )
    gemini_model = fields.Selection([
        ('gemini-2.0-flash',      'Gemini 2.0 Flash (Recommended)'),
        ('gemini-1.5-flash',      'Gemini 1.5 Flash'),
        ('gemini-1.5-flash-8b',   'Gemini 1.5 Flash 8B (Lightweight)'),
    ], string='Gemini Model',
        config_parameter='hr_recruitment_onboarding.gemini_model',
        default='gemini-2.0-flash'
    )

    # ── Ollama (local) ────────────────────────────────────────────
    ollama_base_url = fields.Char(
        string='Ollama Server URL',
        config_parameter='hr_recruitment_onboarding.ollama_base_url',
        default='http://localhost:11434',
        help='Local Ollama server URL. Install from ollama.com and run: ollama pull llama3'
    )
    ollama_model = fields.Char(
        string='Ollama Model Name',
        config_parameter='hr_recruitment_onboarding.ollama_model',
        default='llama3',
        help='Model name as shown by "ollama list". E.g. llama3, mistral, gemma2'
    )

    # ── Shared AI settings ────────────────────────────────────────
    ai_auto_score = fields.Boolean(
        string='Auto-Score New Applicants',
        config_parameter='hr_recruitment_onboarding.ai_auto_score',
        default=True,
        help='Automatically run AI scoring when a new application is received.'
    )
    ai_min_score_shortlist = fields.Float(
        string='Min Score to Auto-Shortlist',
        config_parameter='hr_recruitment_onboarding.ai_min_score_shortlist',
        default=70.0
    )
    ai_min_score_reject = fields.Float(
        string='Max Score for Auto-Reject',
        config_parameter='hr_recruitment_onboarding.ai_min_score_reject',
        default=20.0
    )

    # ── Social Media ──────────────────────────────────────────────
    social_auto_post_jobs = fields.Boolean(
        string='Auto-Post Jobs to Social Media',
        config_parameter='hr_recruitment_onboarding.social_auto_post_jobs',
        default=True,
    )
    social_post_include_salary = fields.Boolean(
        string='Include Salary Range in Social Posts',
        config_parameter='hr_recruitment_onboarding.social_post_include_salary',
        default=False
    )

    # ── Onboarding ────────────────────────────────────────────────
    onboarding_auto_create = fields.Boolean(
        string='Auto-Create Onboarding Plan on Hire',
        config_parameter='hr_recruitment_onboarding.onboarding_auto_create',
        default=True
    )
    onboarding_reminder_days = fields.Integer(
        string='Send Overdue Reminder After (Days)',
        config_parameter='hr_recruitment_onboarding.onboarding_reminder_days',
        default=1
    )

    # ── Approvals ─────────────────────────────────────────────────
    offer_approval_required = fields.Boolean(
        string='Require Approval Before Sending Offer',
        config_parameter='hr_recruitment_onboarding.offer_approval_required',
        default=True
    )
    approval_deadline_hours = fields.Integer(
        string='Approval Deadline (Hours)',
        config_parameter='hr_recruitment_onboarding.approval_deadline_hours',
        default=48
    )
    headcount_approval_required = fields.Boolean(
        string='Require Headcount Approval Before Publishing Job',
        config_parameter='hr_recruitment_onboarding.headcount_approval_required',
        default=False
    )
