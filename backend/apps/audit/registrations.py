"""Central list of audited models (loaded once all apps are ready)."""

from django.apps import apps

from .registry import register

AUDITED = {
    "tenancy.Organization": {},
    "tenancy.OrganizationFeature": {},
    "accounts.User": {"exclude": ["failed_login_count", "locked_until", "preferences"]},
    "rbac.Role": {},
    "rbac.RoleAssignment": {},
    "organization.Department": {},
    "organization.Position": {},
    "organization.Grade": {},
    "organization.GradeStep": {"sensitive": ["basic_salary"]},
    "employees.Employee": {"sensitive": ["basic_salary", "ghana_card_no", "ssnit_number", "tin", "passport_no",
                                         "date_of_birth"]},
    "employees.EmploymentRecord": {"sensitive": ["basic_salary"]},
    "employees.Contract": {},
    "employees.BankAccount": {"sensitive": ["account_number", "momo_number"]},
    "employees.ChangeRequest": {"sensitive": ["changes", "previous"]},
    "documents.Document": {},
    "documents.LetterTemplate": {},
    "workflow.WorkflowDefinition": {},
    "workflow.WorkflowStep": {},
    "workflow.Delegation": {},
    "leave.LeaveType": {},
    "leave.LeavePolicy": {},
    "leave.LeaveRequest": {},
    "leave.LeaveLedgerEntry": {},
    "attendance.AttendancePolicy": {},
    "attendance.AttendanceCorrection": {},
    "attendance.Shift": {},
    "payroll.PayElement": {},
    "payroll.EmployeePayElement": {"sensitive": ["amount"]},
    "payroll.TaxTable": {},
    "payroll.TaxBand": {},
    "payroll.StatutoryRateSet": {},
    "payroll.PayrollRun": {},
    "payroll.Loan": {"sensitive": ["principal"]},
    "integrations.ApiKey": {"exclude": ["key_hash"]},
    "integrations.Webhook": {"exclude": ["secret"]},
    "hospital.ProfessionalLicense": {},
}


def register_all():
    for label, cfg in AUDITED.items():
        try:
            model = apps.get_model(label)
        except LookupError:
            continue
        register(model, **cfg)
