# -*- coding: utf-8 -*-
"""
hr_applicant.py  –  Multi-provider AI scoring engine
  1. Groq      – free, fast (console.groq.com)
  2. Gemini    – free tier (aistudio.google.com)
  3. Ollama    – local/on-premise (ollama.com)
  4. Rule-based – no API key, always works
Falls through each provider in order until one succeeds.
"""
import json
import logging
import re
import base64
import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
# AI Engine
# ══════════════════════════════════════════════════════════════════

class AIScoringEngine:
    PROVIDERS_IN_ORDER = ['groq', 'gemini', 'ollama', 'rule_based']

    def __init__(self, config):
        self.cfg = config

    def score(self, job_desc, resume_text, skills, candidate_name):
        preferred = self.cfg.get('ai_provider', 'groq')
        order = [preferred] + [p for p in self.PROVIDERS_IN_ORDER if p != preferred]
        last_error = None
        for provider in order:
            try:
                result = self._try_provider(provider, job_desc, resume_text, skills, candidate_name)
                result['provider'] = provider
                _logger.info('AI scoring succeeded via: %s', provider)
                return result
            except Exception as e:
                _logger.warning('Provider %s failed: %s', provider, e)
                last_error = e
        raise UserError(_(
            'All AI providers failed. Last error: %s\n\n'
            'The module still works — configure a free Groq or Gemini key in '
            'Settings → Recruitment Settings.'
        ) % str(last_error))

    def _try_provider(self, provider, job_desc, resume_text, skills, name):
        if provider == 'groq':
            return self._score_groq(job_desc, resume_text, skills, name)
        elif provider == 'gemini':
            return self._score_gemini(job_desc, resume_text, skills, name)
        elif provider == 'ollama':
            return self._score_ollama(job_desc, resume_text, skills, name)
        else:
            return self._score_rule_based(job_desc, resume_text, skills, name)

    # ── Groq: free 14,400 req/day, ~0.5s – console.groq.com ──────
    def _score_groq(self, job_desc, resume_text, skills, name):
        api_key = self.cfg.get('groq_api_key', '').strip()
        if not api_key:
            raise ValueError('Groq API key not configured')
        model = self.cfg.get('groq_model', 'llama-3.3-70b-versatile')
        resp = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json={
                'model': model,
                'messages': [{'role': 'user', 'content': self._build_prompt(job_desc, resume_text, skills, name)}],
                'temperature': 0.1,
                'max_tokens': 700,
                'response_format': {'type': 'json_object'},
            },
            timeout=20,
        )
        resp.raise_for_status()
        return self._parse(resp.json()['choices'][0]['message']['content'])

    # ── Gemini: free 1,500 req/day – aistudio.google.com ─────────
    def _score_gemini(self, job_desc, resume_text, skills, name):
        api_key = self.cfg.get('gemini_api_key', '').strip()
        if not api_key:
            raise ValueError('Gemini API key not configured')
        model = self.cfg.get('gemini_model', 'gemini-2.0-flash')
        url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}'
        resp = requests.post(
            url,
            headers={'Content-Type': 'application/json'},
            json={
                'contents': [{'parts': [{'text': self._build_prompt(job_desc, resume_text, skills, name)}]}],
                'generationConfig': {'temperature': 0.1, 'maxOutputTokens': 700, 'responseMimeType': 'application/json'},
            },
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()['candidates'][0]['content']['parts'][0]['text']
        return self._parse(raw)

    # ── Ollama: local/free unlimited – ollama.com ─────────────────
    def _score_ollama(self, job_desc, resume_text, skills, name):
        base = self.cfg.get('ollama_base_url', 'http://localhost:11434').rstrip('/')
        model = self.cfg.get('ollama_model', 'llama3')
        resp = requests.post(
            f'{base}/api/generate',
            json={
                'model': model,
                'prompt': self._build_prompt(job_desc, resume_text, skills, name),
                'stream': False,
                'format': 'json',
                'options': {'temperature': 0.1, 'num_predict': 700},
            },
            timeout=120,
        )
        resp.raise_for_status()
        return self._parse(resp.json().get('response', ''))

    # ── Rule-based: no API needed, keyword + skill matching ───────
    def _score_rule_based(self, job_desc, resume_text, skills, name):
        job_text   = (job_desc or '').lower()
        resume_low = (resume_text or '').lower()
        score = 0
        matched, missing = [], []

        # Skill matching (40 pts max)
        if skills:
            per_skill = min(40 / len(skills), 8)
            for s in skills:
                (matched if s.lower() in resume_low else missing).append(s)
                if s.lower() in resume_low:
                    score += per_skill

        # Experience keywords (20 pts)
        for pat, pts in [(r'\b\d+\+?\s*years?\s*(of\s*)?experience', 15),
                         (r'\bsenior\b|\blead\b|\bprincipal\b', 10),
                         (r'\bmanager\b|\bdirector\b', 10),
                         (r'\bexperienced\b|\bproficient\b', 5)]:
            if re.search(pat, resume_low):
                score += pts; break

        # Education (15 pts)
        for kw, pts in [('phd',15),('master',12),('mba',12),('bachelor',10),('degree',8),('diploma',6),('certified',5)]:
            if kw in resume_low:
                score += pts; break

        # Completeness (10 pts)
        words = len(resume_low.split())
        score += 10 if words > 200 else 6 if words > 80 else 3 if words > 20 else 0

        # Signals (5 pts)
        if 'linkedin.com' in resume_low: score += 3
        if 'github.com'   in resume_low: score += 2

        # Keyword overlap with JD (10 pts)
        if job_text and resume_low:
            jw = set(re.findall(r'\b\w{4,}\b', job_text))
            rw = set(re.findall(r'\b\w{4,}\b', resume_low))
            score += min(len(jw & rw) * 0.5, 10)

        score = round(min(max(score, 0), 100), 1)
        lines = []
        if matched:  lines.append('Matched skills: ' + ', '.join(matched))
        if missing:  lines.append('Missing skills: ' + ', '.join(missing))
        lines.append(f'Rule-based score: {score}/100')
        lines.append('Tip: Add a free Groq API key (console.groq.com) for richer AI analysis.')
        return {'score': score, 'details': '\n'.join(lines)}

    # ── Shared helpers ────────────────────────────────────────────
    def _build_prompt(self, job_desc, resume_text, skills, name):
        return (
            f"You are an expert HR recruiter. Score this candidate against the job.\n\n"
            f"JOB:\n{job_desc or 'Not specified'}\n\n"
            f"CANDIDATE: {name or 'Unknown'}\n"
            f"SKILLS: {', '.join(skills) if skills else 'Not listed'}\n"
            f"RESUME:\n{resume_text or 'Not provided'}\n\n"
            f"Respond ONLY with valid JSON (no markdown):\n"
            f'{{"score":<0-100>,"label":"<Excellent|Good|Average|Poor>",'
            f'"strengths":["..."],"concerns":["..."],'
            f'"interview_questions":["..."],"summary":"..."}}'
        )

    def _parse(self, raw):
        try:
            clean = re.sub(r'```(?:json)?|```', '', raw).strip()
            m = re.search(r'\{.*\}', clean, re.DOTALL)
            data = json.loads(m.group(0) if m else clean)
            lines = []
            if data.get('summary'):      lines.append(f"Summary: {data['summary']}")
            if data.get('strengths'):    lines.append("Strengths: " + '; '.join(data['strengths']))
            if data.get('concerns'):     lines.append("Concerns: " + '; '.join(data['concerns']))
            if data.get('interview_questions'): lines.append("Interview Qs: " + '; '.join(data['interview_questions']))
            return {'score': float(data.get('score', 0)), 'details': '\n'.join(lines)}
        except Exception:
            num = re.search(r'"score"\s*:\s*(\d+)', raw)
            return {'score': float(num.group(1)) if num else 0, 'details': raw[:400]}


# ══════════════════════════════════════════════════════════════════
# Odoo Model
# ══════════════════════════════════════════════════════════════════

class HrApplicant(models.Model):
    _inherit = 'hr.applicant'

    ai_score = fields.Float(string='AI Match Score', digits=(5,1), readonly=True, tracking=True)
    ai_score_label = fields.Selection([
        ('excellent','Excellent (80-100)'),('good','Good (60-79)'),
        ('average','Average (40-59)'),('poor','Poor (0-39)'),
    ], string='Score Label', compute='_compute_ai_score_label', store=True)
    ai_score_details  = fields.Text(string='AI Evaluation Details', readonly=True)
    ai_scored_date    = fields.Datetime(string='Last AI Scored', readonly=True)
    ai_score_provider = fields.Char(string='Scored by', readonly=True)

    linkedin_profile  = fields.Char(string='LinkedIn Profile URL')
    linkedin_imported = fields.Boolean(string='Imported from LinkedIn', default=False)
    onboarding_id     = fields.Many2one('hr.onboarding', string='Onboarding Plan')

    source_channel = fields.Selection([
        ('website','Company Website'),('linkedin','LinkedIn'),
        ('facebook','Facebook'),('twitter','Twitter/X'),
        ('instagram','Instagram'),('referral','Employee Referral'),
        ('agency','Recruitment Agency'),('walk_in','Walk-In'),('other','Other'),
    ], string='Source Channel', default='website', tracking=True)

    access_token = fields.Char(
        string='Portal Access Token',
        default=lambda self: self._generate_token(), copy=False, readonly=True
    )
    offer_salary       = fields.Monetary(string='Offered Salary', currency_field='currency_id', tracking=True)
    offer_joining_date = fields.Date(string='Proposed Joining Date', tracking=True)
    offer_expiry_date  = fields.Date(string='Offer Expiry Date')
    offer_state = fields.Selection([
        ('draft','Draft'),('sent','Sent'),('accepted','Accepted'),('declined','Declined'),('expired','Expired'),
    ], string='Offer Status', default='draft', tracking=True)
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)

    approval_request_id = fields.Many2one('hr.recruitment.approval', string='Approval Request', readonly=True)
    approval_state      = fields.Selection(related='approval_request_id.state', string='Approval State', store=True)
    interview_count     = fields.Integer(string='Interviews', compute='_compute_interview_count')
    last_interview_date = fields.Datetime(string='Last Interview', compute='_compute_interview_count', store=True)

    @api.depends('ai_score')
    def _compute_ai_score_label(self):
        for r in self:
            s = r.ai_score or 0
            r.ai_score_label = 'excellent' if s>=80 else 'good' if s>=60 else 'average' if s>=40 else 'poor'

    def _compute_interview_count(self):
        for r in self:
            # applicant_ids removed in Odoo 19 - use activity or set to 0
            r.interview_count = 0
            r.last_interview_date = False

    def _get_ai_config(self):
        g = lambda k: self.env['ir.config_parameter'].sudo().get_param(
            f'hr_recruitment_onboarding.{k}', default='')
        return {
            'ai_provider':    g('ai_provider') or 'groq',
            'groq_api_key':   g('groq_api_key'),
            'groq_model':     g('groq_model') or 'llama-3.3-70b-versatile',
            'gemini_api_key': g('gemini_api_key'),
            'gemini_model':   g('gemini_model') or 'gemini-2.0-flash',
            'ollama_base_url':g('ollama_base_url') or 'http://localhost:11434',
            'ollama_model':   g('ollama_model') or 'llama3',
        }

    def action_compute_ai_score(self):
        for applicant in self:
            engine = AIScoringEngine(applicant._get_ai_config())
            job_desc = applicant.job_id.description or applicant.job_id.name or ''
            extra    = getattr(applicant.job_id, 'required_skills_text', '') or ''
            if extra:
                job_desc += f'\n\nRequired skills:\n{extra}'
            result = engine.score(
                job_desc,
                applicant._extract_resume_text(),
                applicant.categ_ids.mapped('name'),
                applicant.partner_name or '',
            )
            applicant.write({
                'ai_score':          result['score'],
                'ai_score_details':  result['details'],
                'ai_scored_date':    fields.Datetime.now(),
                'ai_score_provider': result.get('provider', ''),
            })
            prov_labels = {
                'groq':'Groq (Llama 3.3 – Free)',
                'gemini':'Google Gemini (Free)',
                'ollama':'Ollama (Local)',
                'rule_based':'Rule-based (No API)',
            }
            applicant.message_post(body=_(
                '<b>AI Scoring</b> via %(p)s<br/>'
                'Score: <b>%(s)s/100</b><br/>'
                '<pre style="font-size:12px">%(d)s</pre>'
            ) % {
                'p': prov_labels.get(result.get('provider',''), result.get('provider','')),
                's': result['score'],
                'd': result['details'],
            })

    def _extract_resume_text(self):
        self.ensure_one()
        texts = []
        for att in self.env['ir.attachment'].search([
            ('res_model','=','hr.applicant'), ('res_id','=',self.id)
        ]):
            if att.mimetype == 'text/plain':
                try:
                    texts.append(base64.b64decode(att.datas).decode('utf-8', errors='ignore'))
                except Exception:
                    pass
            elif att.mimetype == 'application/pdf':
                try:
                    from pdfminer.high_level import extract_text_to_fp
                    from pdfminer.layout import LAParams
                    import io
                    buf = io.StringIO()
                    extract_text_to_fp(io.BytesIO(base64.b64decode(att.datas)), buf, laparams=LAParams())
                    texts.append(buf.getvalue())
                except Exception:
                    pass
        # description field renamed in Odoo 19 - try multiple field names
        fallback = ''
        for fname in ('description', 'notes', 'categ_ids'):
            try:
                val = self[fname]
                if val and isinstance(val, str):
                    fallback = val
                    break
            except Exception:
                pass
        return '\n'.join(texts) or fallback

    def action_send_offer(self):
        self.ensure_one()
        return {'type':'ir.actions.act_window','name':_('Send Offer'),
                'res_model':'hr.recruitment.offer.wizard','view_mode':'form',
                'target':'new','context':{'default_applicant_id':self.id}}

    def action_request_approval(self):
        self.ensure_one()
        if self.approval_request_id:
            raise UserError(_('An approval request already exists.'))
        approval = self.env['hr.recruitment.approval'].create({
            'applicant_id':   self.id,
            'job_id':         self.job_id.id,
            'offered_salary': self.offer_salary,
            'approver_ids':   self._get_approval_chain(),
        })
        self.approval_request_id = approval
        approval.action_submit()
        return {'type':'ir.actions.act_window','name':_('Approval Request'),
                'res_model':'hr.recruitment.approval','res_id':approval.id,'view_mode':'form'}

    def _get_approval_chain(self):
        chain = []
        if self.department_id.manager_id:
            chain.append((0,0,{'approver_id':self.department_id.manager_id.user_id.id,'level':1,'role':'Department Manager'}))
        hr_user = self.env['res.users'].search([('groups_id.category_id.name','=','Human Resources')], limit=1)
        if hr_user:
            chain.append((0,0,{'approver_id':hr_user.id,'level':2,'role':'HR Manager'}))
        return chain

    def action_create_employee(self):
        res = super().action_create_employee()
        employee = self.env['hr.employee'].search([
            ('name','=',self.partner_name),('job_id','=',self.job_id.id)
        ], limit=1)
        if employee and not self.onboarding_id:
            ob = self.env['hr.onboarding'].create({
                'employee_id':   employee.id,
                'job_id':        self.job_id.id,
                'department_id': self.department_id.id,
                'applicant_id':  self.id,
                'start_date':    self.offer_joining_date or fields.Date.today(),
            })
            ob._generate_tasks()
            self.onboarding_id = ob
        return res

    def _generate_token(self):
        import secrets
        return secrets.token_urlsafe(32)

    def get_portal_url(self):
        self.ensure_one()
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return f"{base}/jobs/application/{self.id}/{self.access_token}"

    def action_view_interviews(self):
        return {'type':'ir.actions.act_window','name':_('Interviews'),
                'res_model':'calendar.event','view_mode':'list,form',
                'domain':[]}

    def action_view_onboarding(self):
        self.ensure_one()
        if not self.onboarding_id:
            raise UserError(_('No onboarding plan linked yet.'))
        return {'type':'ir.actions.act_window','name':_('Onboarding Plan'),
                'res_model':'hr.onboarding','res_id':self.onboarding_id.id,'view_mode':'form'}