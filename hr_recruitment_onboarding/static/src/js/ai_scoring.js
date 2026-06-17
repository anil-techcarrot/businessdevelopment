/** @odoo-module **/
// hr_recruitment_onboarding/static/src/js/ai_scoring.js
// Colorizes AI score fields in list/kanban views

import { patch } from "@web/core/utils/patch";

// Utility: get color class based on score value
export function getAiScoreClass(score) {
    if (score >= 80) return "badge_ai_excellent";
    if (score >= 60) return "badge_ai_good";
    if (score >= 40) return "badge_ai_average";
    return "badge_ai_poor";
}

// Export for use in templates
export default { getAiScoreClass };
