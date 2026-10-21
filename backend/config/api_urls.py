from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.accounts.admin_views import LoginAttemptViewSet, UserLookupViewSet, UserViewSet
from apps.assets import views as ast
from apps.attendance import views as att
from apps.audit.views import AuditLogViewSet
from apps.compensation import views as comp
from apps.documents import views as docs
from apps.employees import views as emp
from apps.engagement import views as eng
from apps.expenses import views as exp
from apps.hospital import views as hosp
from apps.integrations import views as integ
from apps.learning import views as lrn
from apps.leave import views as leave
from apps.notifications import views as notif
from apps.offboarding import views as offb
from apps.onboarding import views as onb
from apps.organization import views as org
from apps.payroll import views as pay
from apps.performance import views as perf
from apps.rbac.views import PermissionViewSet, RoleAssignmentViewSet, RoleViewSet
from apps.recruitment import views as rec
from apps.relations import views as er
from apps.reports import views as rep
from apps.safety import views as ohs
from apps.selfservice import views as me
from apps.assistant import views as ai
from apps.licensing import views as lic
from apps.servicedesk import views as sd
from apps.talent import views as tal
from apps.sso import views as sso
from apps.tenancy import platform as plat
from apps.tenancy import views as ten
from apps.workflow import views as wf

router = DefaultRouter()
# administration
router.register("admin/users", UserViewSet, basename="users")
router.register("platform/organizations", plat.OrganizationAdminViewSet, basename="platform-organizations")
router.register("platform/plans", plat.PlanViewSet, basename="platform-plans")
router.register("admin/sso-providers", sso.IdentityProviderViewSet, basename="sso-providers")
router.register("assistant/conversations", ai.ConversationViewSet, basename="assistant-conversations")
router.register("admin/login-attempts", LoginAttemptViewSet, basename="login-attempts")
router.register("users/lookup", UserLookupViewSet, basename="user-lookup")
router.register("admin/permissions", PermissionViewSet, basename="permissions")
router.register("admin/roles", RoleViewSet, basename="roles")
router.register("admin/role-assignments", RoleAssignmentViewSet, basename="role-assignments")
router.register("admin/holidays", ten.HolidayViewSet, basename="holidays")
router.register("admin/number-sequences", ten.NumberSequenceViewSet, basename="number-sequences")
router.register("admin/custom-fields", ten.CustomFieldViewSet, basename="custom-fields")
router.register("admin/config-changes", ten.ConfigChangeViewSet, basename="config-changes")
router.register("audit/logs", AuditLogViewSet, basename="audit")
# organization
router.register("org/branches", org.BranchViewSet, basename="branches")
router.register("org/locations", org.LocationViewSet, basename="locations")
router.register("org/cost-centers", org.CostCenterViewSet, basename="cost-centers")
router.register("org/departments", org.DepartmentViewSet, basename="departments")
router.register("org/job-families", org.JobFamilyViewSet, basename="job-families")
router.register("org/grades", org.GradeViewSet, basename="grades")
router.register("org/grade-steps", org.GradeStepViewSet, basename="grade-steps")
router.register("org/job-titles", org.JobTitleViewSet, basename="job-titles")
router.register("org/positions", org.PositionViewSet, basename="positions")
router.register("org/chart", org.OrgChartViewSet, basename="org-chart")
# employees
router.register("employees/categories", emp.CategoryViewSet, basename="categories")
router.register("employees/contracts", emp.ContractViewSet, basename="contracts")
router.register("employees/emergency-contacts", emp.EmergencyContactViewSet, basename="emergency-contacts")
router.register("employees/beneficiaries", emp.BeneficiaryViewSet, basename="beneficiaries")
router.register("employees/bank-accounts", emp.BankAccountViewSet, basename="bank-accounts")
router.register("employees/qualifications", emp.QualificationViewSet, basename="qualifications")
router.register("employees/concurrent-assignments", emp.ConcurrentAssignmentViewSet, basename="concurrent")
router.register("employees/change-requests", emp.ChangeRequestViewSet, basename="change-requests")
router.register("employees/consents", emp.DataConsentViewSet, basename="consents")
router.register("directory", emp.DirectoryViewSet, basename="directory")
router.register("employees", emp.EmployeeViewSet, basename="employees")
# documents
router.register("documents/categories", docs.CategoryViewSet, basename="doc-categories")
router.register("documents/templates", docs.LetterTemplateViewSet, basename="letter-templates")
router.register("documents/letter-requests", docs.LetterRequestViewSet, basename="letter-requests")
router.register("documents/signatures", docs.SignatureRequestViewSet, basename="signatures")
router.register("documents", docs.DocumentViewSet, basename="documents")
# service desk
router.register("helpdesk/categories", sd.CategoryViewSet, basename="sd-categories")
router.register("helpdesk/services", sd.ServiceTypeViewSet, basename="sd-services")
router.register("helpdesk/articles", sd.ArticleViewSet, basename="sd-articles")
router.register("helpdesk/tickets", sd.TicketViewSet, basename="sd-tickets")
# travel & expenses
router.register("expenses/per-diem", exp.PerDiemViewSet, basename="per-diem")
router.register("expenses/budgets", exp.BudgetViewSet, basename="expense-budgets")
router.register("expenses/travel", exp.TravelViewSet, basename="travel")
router.register("expenses/claims", exp.ClaimViewSet, basename="claims")
# compensation & benefits
router.register("compensation/reviews", comp.CycleViewSet, basename="salary-reviews")
router.register("compensation/bonus-schemes", comp.SchemeViewSet, basename="bonus-schemes")
router.register("compensation/bonus-awards", comp.AwardViewSet, basename="bonus-awards")
router.register("benefits/plans", comp.PlanViewSet, basename="benefit-plans")
router.register("benefits/enrollments", comp.EnrollmentViewSet, basename="benefit-enrollments")
# recruitment
router.register("recruitment/requisitions", rec.RequisitionViewSet, basename="requisitions")
router.register("recruitment/vacancies", rec.VacancyViewSet, basename="vacancies")
router.register("recruitment/candidates", rec.CandidateViewSet, basename="candidates")
router.register("recruitment/applications", rec.ApplicationViewSet, basename="applications")
router.register("recruitment/interviews", rec.InterviewViewSet, basename="interviews")
router.register("recruitment/checks", rec.CheckViewSet, basename="reference-checks")
router.register("recruitment/offers", rec.OfferViewSet, basename="offers")
# onboarding & probation
router.register("onboarding/templates", onb.TemplateViewSet, basename="onboarding-templates")
router.register("onboarding/template-tasks", onb.TemplateTaskViewSet, basename="onboarding-template-tasks")
router.register("onboarding/tasks", onb.TaskViewSet, basename="onboarding-tasks")
router.register("onboarding/probation", onb.ReviewViewSet, basename="probation-reviews")
router.register("onboarding/records", onb.OnboardingViewSet, basename="onboardings")
# performance
router.register("performance/scales", perf.ScaleViewSet, basename="rating-scales")
router.register("performance/competencies", perf.CompetencyViewSet, basename="competencies")
router.register("performance/templates", perf.TemplateViewSet, basename="appraisal-templates")
router.register("performance/cycles", perf.CycleViewSet, basename="review-cycles")
router.register("performance/goals", perf.GoalViewSet, basename="goals")
router.register("performance/appraisals", perf.AppraisalViewSet, basename="appraisals")
router.register("performance/objectives", perf.ObjectiveViewSet, basename="objectives")
router.register("performance/feedback", perf.FeedbackViewSet, basename="feedback")
router.register("performance/plans", perf.PlanViewSet, basename="improvement-plans")
router.register("performance/milestones", perf.MilestoneViewSet, basename="plan-milestones")
# learning
router.register("learning/courses", lrn.CourseViewSet, basename="courses")
router.register("learning/modules", lrn.ModuleViewSet, basename="course-modules")
router.register("learning/questions", lrn.QuestionViewSet, basename="quiz-questions")
router.register("learning/sessions", lrn.SessionViewSet, basename="training-sessions")
router.register("learning/enrollments", lrn.EnrollmentViewSet, basename="training-enrollments")
router.register("learning/budgets", lrn.BudgetViewSet, basename="training-budgets")
router.register("learning/cpd", lrn.CPDViewSet, basename="cpd")
router.register("learning/cpd-requirements", lrn.CPDRequirementViewSet, basename="cpd-requirements")
router.register("learning/development-goals", lrn.GoalViewSet, basename="development-goals")
router.register("learning/mentorships", lrn.MentorshipViewSet, basename="mentorships")
# employee relations, assets, offboarding
router.register("relations/cases", er.CaseViewSet, basename="er-cases")
router.register("assets/categories", ast.CategoryViewSet, basename="asset-categories")
router.register("assets/items", ast.AssetViewSet, basename="assets")
router.register("assets/assignments", ast.AssignmentViewSet, basename="asset-assignments")
router.register("offboarding/separations", offb.SeparationViewSet, basename="separations")
# engagement & safety
router.register("engagement/surveys", eng.SurveyViewSet, basename="surveys")
router.register("engagement/action-plans", eng.ActionPlanViewSet, basename="engagement-actions")
router.register("engagement/recognition", eng.RecognitionViewSet, basename="recognition")
router.register("engagement/suggestions", eng.SuggestionViewSet, basename="suggestions")
router.register("engagement/events", eng.EventViewSet, basename="events")
router.register("safety/incidents", ohs.IncidentViewSet, basename="incidents")
router.register("safety/actions", ohs.ActionViewSet, basename="safety-actions")
router.register("safety/risks", ohs.RiskViewSet, basename="risk-assessments")
router.register("safety/inspections", ohs.InspectionViewSet, basename="inspections")
router.register("safety/oh-records", ohs.OHRecordViewSet, basename="oh-records")
# talent & workforce planning
router.register("talent/assessments", tal.AssessmentViewSet, basename="talent-assessments")
router.register("talent/succession", tal.SuccessionViewSet, basename="succession")
router.register("talent/career-paths", tal.CareerPathViewSet, basename="career-paths")
router.register("planning/plans", tal.WorkforcePlanViewSet, basename="workforce-plans")
router.register("planning/lines", tal.LineViewSet, basename="plan-lines")
router.register("planning/scenarios", tal.ScenarioViewSet, basename="scenarios")
# workflow
router.register("workflow/definitions", wf.DefinitionViewSet, basename="wf-definitions")
router.register("workflow/steps", wf.StepViewSet, basename="wf-steps")
router.register("workflow/inbox", wf.InboxViewSet, basename="wf-inbox")
router.register("workflow/requests", wf.InstanceViewSet, basename="wf-requests")
router.register("workflow/delegations", wf.DelegationViewSet, basename="wf-delegations")
# notifications
router.register("notifications/templates", notif.TemplateViewSet, basename="notif-templates")
router.register("notifications/deliveries", notif.DeliveryLogViewSet, basename="notif-deliveries")
router.register("notifications", notif.NotificationViewSet, basename="notifications")
router.register("announcements", notif.AnnouncementViewSet, basename="announcements")
# leave
router.register("leave/types", leave.LeaveTypeViewSet, basename="leave-types")
router.register("leave/policies", leave.LeavePolicyViewSet, basename="leave-policies")
router.register("leave/requests", leave.LeaveRequestViewSet, basename="leave-requests")
# attendance
router.register("attendance/shifts", att.ShiftViewSet, basename="shifts")
router.register("attendance/policies", att.PolicyViewSet, basename="attendance-policies")
router.register("attendance/patterns", att.PatternViewSet, basename="shift-patterns")
router.register("attendance/devices", att.DeviceViewSet, basename="devices")
router.register("attendance/enrollments", att.EnrollmentViewSet, basename="enrollments")
router.register("attendance/roster", att.RosterViewSet, basename="roster")
router.register("attendance/days", att.DayViewSet, basename="attendance-days")
router.register("attendance/corrections", att.CorrectionViewSet, basename="corrections")
router.register("attendance/summaries", att.SummaryViewSet, basename="attendance-summaries")
# payroll
router.register("payroll/pay-groups", pay.PayGroupViewSet, basename="pay-groups")
router.register("payroll/rate-sets", pay.RateSetViewSet, basename="rate-sets")
router.register("payroll/tax-tables", pay.TaxTableViewSet, basename="tax-tables")
router.register("payroll/reliefs", pay.ReliefViewSet, basename="reliefs")
router.register("payroll/relief-claims", pay.ReliefClaimViewSet, basename="relief-claims")
router.register("payroll/elements", pay.ElementViewSet, basename="pay-elements")
router.register("payroll/profiles", pay.PayProfileViewSet, basename="pay-profiles")
router.register("payroll/employee-elements", pay.EmployeeElementViewSet, basename="employee-elements")
router.register("payroll/periods", pay.PeriodViewSet, basename="periods")
router.register("payroll/adjustments", pay.AdjustmentViewSet, basename="adjustments")
router.register("payroll/runs", pay.RunViewSet, basename="runs")
router.register("payroll/payslips", pay.PayslipViewSet, basename="payslips")
router.register("payroll/loans", pay.LoanViewSet, basename="loans")
router.register("payroll/simulate", pay.SimulateViewSet, basename="simulate")
# reports
router.register("reports/export-requests", rep.ExportRequestViewSet, basename="export-requests")
router.register("reports/scheduled", rep.ScheduledReportViewSet, basename="scheduled-reports")
router.register("reports/definitions", rep.ReportDefinitionViewSet, basename="report-definitions")
# integrations
router.register("integrations/api-keys", integ.ApiKeyViewSet, basename="api-keys")
router.register("integrations/webhooks", integ.WebhookViewSet, basename="webhooks")
# hospital add-on
router.register("hospital/licenses", hosp.LicenseViewSet, basename="licenses")
router.register("hospital/competency-requirements", hosp.RequirementViewSet, basename="competency-requirements")
router.register("hospital/competency-records", hosp.RecordViewSet, basename="competency-records")
router.register("hospital/credentials", hosp.CredentialViewSet, basename="credentials")
# self-service
router.register("me/change-requests", me.ChangeRequestViewSet, basename="me-change-requests")
router.register("me/emergency-contacts", me.EmergencyContactViewSet, basename="me-emergency-contacts")
router.register("me/beneficiaries", me.BeneficiaryViewSet, basename="me-beneficiaries")

urlpatterns = [
    path("organization/", ten.OrganizationView.as_view()),
    path("organization/features/", ten.FeatureToggleView.as_view()),
    path("attendance/clock/", att.ClockView.as_view()),
    path("attendance/team-today/", att.TeamTodayView.as_view()),
    path("reports/dashboard/", rep.DashboardView.as_view()),
    path("reports/analytics/", rep.AnalyticsView.as_view()),
    path("reports/catalog/", rep.ReportCatalogView.as_view()),
    path("reports/run/<str:code>/", rep.RunReportView.as_view()),
    path("reports/forecast/turnover/", rep.TurnoverForecastView.as_view()),
    path("reports/forecast/retirement/", rep.RetirementForecastView.as_view()),
    path("reports/attrition-risk/", rep.AttritionRiskView.as_view()),
    path("me/profile/", me.ProfileView.as_view()),
    path("me/summary/", me.SummaryView.as_view()),
    path("me/documents/", me.MyDocumentsView.as_view()),
    path("me/letters/", me.MyLettersView.as_view()),
    path("me/team/", me.MyTeamView.as_view()),
    path("me/data-export/", me.MyDataExportView.as_view()),
    path("compensation/total-rewards/", comp.TotalRewardsView.as_view()),
    path("recruitment/analytics/", rec.AnalyticsView.as_view()),
    path("me/vacancies/", rec.InternalVacancyView.as_view()),
    path("me/onboarding/", onb.MyOnboardingView.as_view()),
    path("learning/compliance/", lrn.ComplianceView.as_view()),
    path("relations/my/", er.MyCasesView.as_view()),
    path("relations/my/<int:pk>/withdraw/", er.WithdrawMineView.as_view()),
    path("relations/my/letter/<int:pk>/", er.MyLetterView.as_view()),
    path("relations/appeals/<int:pk>/decide/", er.AppealDecisionView.as_view()),
    path("relations/warnings/<int:employee_id>/", er.WarningsView.as_view()),
    path("relations/report/", er.ReportView.as_view()),
    path("assets/dashboard/", ast.DashboardView.as_view()),
    path("engagement/overview/", eng.OverviewView.as_view()),
    path("safety/fitness/", ohs.FitnessView.as_view()),
    path("safety/fitness/<int:employee_id>/", ohs.FitnessView.as_view()),
    path("safety/stats/", ohs.StatsView.as_view()),
    path("talent/me/", tal.MyProfileView.as_view()),
    path("talent/employees/<int:employee_id>/", tal.EmployeeTalentView.as_view()),
    path("planning/establishment/", tal.EstablishmentView.as_view()),
    path("offboarding/clearance/<int:pk>/clear/", offb.ClearView.as_view()),
    path("offboarding/analytics/", offb.AnalyticsView.as_view()),
    path("learning/needs/", lrn.NeedsView.as_view()),
    path("learning/report/", lrn.ReportView.as_view()),
    path("public/careers/<slug:org_code>/", rec.CareersView.as_view()),
    path("public/careers/<slug:org_code>/<int:pk>/", rec.CareerVacancyView.as_view()),
    path("public/careers/<slug:org_code>/<int:pk>/apply/", rec.CareerApplyView.as_view()),
    path("public/offers/<str:token>/", rec.OfferResponseView.as_view()),
    path("public/tenant/", plat.TenantInfoView.as_view()),
    path("public/signup/", plat.SignupView.as_view()),
    path("public/tls-check/", plat.TlsCheckView.as_view()),
    path("licence/", lic.LicenceView.as_view()),
    path("licence/status/", lic.LicenceStatusView.as_view()),
    path("sso/discover/", sso.DiscoverView.as_view()),
    path("sso/<int:pk>/start/", sso.StartView.as_view()),
    path("sso/callback/", sso.CallbackView.as_view()),
    path("assistant/status/", ai.StatusView.as_view()),
    path("assistant/ask/", ai.AskView.as_view()),
    path("assistant/messages/<int:pk>/feedback/", ai.FeedbackView.as_view()),
    path("assistant/settings/", ai.SettingsView.as_view()),
] + router.urls
