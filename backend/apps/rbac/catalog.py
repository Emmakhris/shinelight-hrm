"""Catalogue of permission codes and the default system roles (features.txt section 33).

Codes are `module.action`. Sensitive codes gate masked fields and confidential records.
"""

PERMISSIONS = [
    # code, name, sensitive
    ("employees.view", "View employee records", False),
    ("employees.create", "Create employees / hire", False),
    ("employees.change", "Edit employee records and personnel actions", False),
    ("employees.delete", "Delete employee records", False),
    ("employees.view_personal", "View personal data (national IDs, DOB, address)", True),
    ("employees.view_salary", "View salary and compensation", True),
    ("employees.view_bank", "View bank details", True),
    ("employees.import", "Bulk import employees", False),
    ("employees.export", "Export employee data", True),
    ("organization.view", "View organization structure", False),
    ("organization.manage", "Manage departments, grades and positions", False),
    ("documents.view", "View personnel documents", False),
    ("documents.upload", "Upload personnel documents", False),
    ("documents.manage", "Manage templates, retention and legal hold", False),
    ("documents.view_confidential", "View confidential/restricted documents", True),
    ("documents.generate", "Generate letters from templates", False),
    ("leave.view", "View leave records", False),
    ("leave.approve", "Approve leave requests", False),
    ("leave.manage", "Configure leave types/policies and adjust balances", False),
    ("attendance.view", "View attendance records", False),
    ("attendance.approve", "Approve attendance corrections and exceptions", False),
    ("attendance.manage", "Configure shifts, rosters, devices and rules", False),
    ("payroll.view", "View payroll runs and results", True),
    ("payroll.prepare", "Prepare and calculate payroll", True),
    ("payroll.approve", "Approve payroll (independent of preparer)", True),
    ("payroll.release", "Release payment files and lock payroll", True),
    ("payroll.manage", "Configure pay elements, tax tables and statutory rates", True),
    ("workflow.manage", "Configure approval workflows", False),
    ("workflow.admin", "Reassign or override any workflow task", False),
    ("notifications.manage", "Manage announcements and notification templates", False),
    ("reports.view", "View HR dashboards and reports", False),
    ("reports.export", "Export reports", True),
    ("reports.view_payroll", "View payroll cost reports", True),
    ("admin.settings", "Manage organization settings and configuration", False),
    ("admin.users", "Manage user accounts", False),
    ("admin.roles", "Manage roles and permission assignments", True),
    ("audit.view", "View audit trails", True),
    ("integrations.manage", "Manage API keys and webhooks", True),
    ("servicedesk.agent", "Work HR service desk tickets", False),
    ("servicedesk.manage", "Manage service catalogue, knowledge base and all tickets", False),
    ("servicedesk.view_confidential", "View confidential service desk tickets", True),
    ("expenses.view", "View travel requests and expense claims", False),
    ("expenses.manage", "Manage per diem rates, budgets and claims for others", False),
    ("expenses.pay", "Record advance payments and settle claims (finance)", True),
    ("compensation.view", "View salary reviews and bonus schemes", True),
    ("compensation.manage", "Prepare salary reviews and bonus awards", True),
    ("benefits.manage", "Manage benefit plans and enrolments", True),
    ("recruitment.requisition", "Raise manpower requisitions", False),
    ("recruitment.view", "View vacancies, candidates and applications", False),
    ("recruitment.manage", "Manage vacancies, pipeline, interviews and checks", False),
    ("recruitment.offer", "Prepare offers and convert hires", True),
    ("onboarding.view", "View onboarding progress and probation reviews", False),
    ("onboarding.manage", "Manage onboarding checklists, tasks and probation", False),
    ("performance.view", "View appraisals and improvement plans", True),
    ("performance.manage", "Run review cycles, templates, calibration and improvement plans", True),
    ("hospital.view", "View clinical credentials and rosters", False),
    ("hospital.manage", "Manage clinical credentials and rosters", False),
]

SCOPES = ["own", "team", "department", "branch", "organization"]

_ALL = [p[0] for p in PERMISSIONS]


def _all_except(*prefixes):
    return [c for c in _ALL if not c.startswith(prefixes)]


# role code -> (name, default scope, permission codes)
DEFAULT_ROLES = {
    "sys_admin": (
        "System Administrator",
        "organization",
        ["admin.settings", "admin.users", "admin.roles", "organization.view", "organization.manage",
         "workflow.manage", "workflow.admin", "notifications.manage", "integrations.manage", "audit.view",
         "attendance.manage"],
    ),
    "hr_director": (
        "HR Director / HR Manager",
        "organization",
        _all_except("payroll.prepare", "payroll.release", "payroll.manage", "integrations.", "admin.roles"),
    ),
    "hr_officer": (
        "HR Officer",
        "organization",
        ["employees.view", "employees.create", "employees.change", "employees.view_personal", "employees.import",
         "organization.view", "documents.view", "documents.upload", "documents.generate", "leave.view",
         "leave.approve", "leave.manage", "attendance.view", "attendance.approve", "reports.view",
         "notifications.manage", "hospital.view", "hospital.manage", "servicedesk.agent", "servicedesk.manage",
         "expenses.view", "expenses.manage", "benefits.manage", "compensation.view", "recruitment.view",
         "recruitment.manage", "recruitment.requisition", "onboarding.view", "onboarding.manage", "performance.view",
         "performance.manage"],
    ),
    "recruitment_officer": (
        "Recruitment Officer",
        "organization",
        ["employees.view", "organization.view", "reports.view", "recruitment.view", "recruitment.manage",
         "recruitment.offer", "recruitment.requisition", "onboarding.view", "documents.generate"],
    ),
    "payroll_officer": (
        "Payroll Officer",
        "organization",
        ["employees.view", "employees.view_salary", "employees.view_bank", "organization.view", "payroll.view",
         "payroll.prepare", "payroll.manage", "leave.view", "attendance.view", "reports.view",
         "reports.view_payroll", "servicedesk.agent", "expenses.view", "expenses.pay", "compensation.view"],
    ),
    "payroll_approver": (
        "Payroll Approver",
        "organization",
        ["employees.view", "employees.view_salary", "payroll.view", "payroll.approve", "payroll.release",
         "reports.view", "reports.view_payroll"],
    ),
    "dept_head": (
        "Department Head",
        "department",
        ["employees.view", "organization.view", "leave.view", "leave.approve", "attendance.view",
         "attendance.approve", "reports.view", "documents.view", "expenses.view", "recruitment.requisition",
         "onboarding.view", "performance.view"],
    ),
    "line_manager": (
        "Line Manager",
        "team",
        ["employees.view", "organization.view", "leave.view", "leave.approve", "attendance.view",
         "attendance.approve", "expenses.view", "recruitment.requisition", "onboarding.view", "performance.view"],
    ),
    "finance_officer": (
        "Finance Officer",
        "organization",
        ["payroll.view", "reports.view", "reports.view_payroll", "reports.export", "organization.view",
         "expenses.view", "expenses.pay", "employees.view"],
    ),
    "training_officer": (
        "Training Officer",
        "organization",
        ["employees.view", "organization.view", "documents.view", "reports.view", "hospital.view",
         "performance.view"],
    ),
    "employee": (
        "Employee",
        "own",
        ["employees.view", "employees.view_personal", "employees.view_salary", "employees.view_bank",
         "leave.view", "attendance.view", "documents.view", "organization.view", "expenses.view",
         "performance.view"],
    ),
    "internal_auditor": (
        "Internal Auditor (read-only)",
        "organization",
        ["employees.view", "organization.view", "payroll.view", "leave.view", "attendance.view", "audit.view",
         "reports.view", "reports.view_payroll", "documents.view", "expenses.view", "compensation.view"],
    ),
    "it_support": (
        "IT Support (account and equipment provisioning)",
        "organization",
        ["organization.view"],
    ),
    "admin_officer": (
        "Administration / Facilities Officer",
        "organization",
        ["organization.view"],
    ),
    "oh_professional": (
        "Occupational Health Professional",
        "organization",
        ["employees.view", "documents.view", "documents.view_confidential"],
    ),
}
