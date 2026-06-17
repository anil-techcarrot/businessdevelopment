/** @odoo-module **/
// hr_recruitment_onboarding/static/src/js/recruitment_dashboard.js
// Recruitment dashboard enhancements – Odoo 18 / 19 OWL components

import { registry } from "@web/core/registry";
import { Component, useState, onMounted } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

// Simple stat card component for the recruitment dashboard
class RecruitmentDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            stats: {
                new_applications: 0,
                in_progress: 0,
                offers_pending: 0,
                onboarding_active: 0,
            },
            loading: true,
        });
        onMounted(() => this.loadStats());
    }

    async loadStats() {
        try {
            const [apps, onboarding] = await Promise.all([
                this.orm.searchCount("hr.applicant", [["stage_id.name", "=", "New Application"]]),
                this.orm.searchCount("hr.onboarding", [["state", "=", "in_progress"]]),
            ]);
            this.state.stats.new_applications = apps;
            this.state.stats.onboarding_active = onboarding;
        } catch (e) {
            console.warn("Dashboard stats load failed:", e);
        } finally {
            this.state.loading = false;
        }
    }

    openApplications() {
        this.action.doAction("hr_recruitment.action_hr_applicant");
    }

    openOnboarding() {
        this.action.doAction("hr_recruitment_onboarding.action_hr_onboarding");
    }
}

RecruitmentDashboard.template = "hr_recruitment_onboarding.Dashboard";

// Register as client action
registry.category("actions").add("hr_recruitment_onboarding_dashboard", RecruitmentDashboard);
