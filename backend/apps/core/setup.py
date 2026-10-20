"""Initial configuration for a new organization (idempotent). Used by `manage.py setup_organization`
and the demo seeder. Statutory figures are seeded unverified and must be checked before go-live."""

import datetime as dt
from decimal import Decimal

from django.db import transaction

from apps.core.context import org_context
from apps.rbac.catalog import DEFAULT_ROLES, PERMISSIONS
from apps.rbac.models import Permission, Role
from apps.tenancy.models import Organization, OrganizationFeature

D = Decimal

MFA_ROLES = {"sys_admin", "hr_director", "hr_officer", "payroll_officer", "payroll_approver", "finance_officer",
             "internal_auditor"}


def seed_permissions():
    for code, name, sensitive in PERMISSIONS:
        Permission.objects.update_or_create(code=code, defaults={"name": name, "module": code.split(".")[0],
                                                                 "is_sensitive": sensitive})


def seed_roles(require_mfa=True):
    perms = {p.code: p for p in Permission.objects.all()}
    for code, (name, scope, codes) in DEFAULT_ROLES.items():
        role, _ = Role.objects.update_or_create(code=code, defaults={
            "name": name, "default_scope": scope, "is_system": True,
            "requires_mfa": require_mfa and code in MFA_ROLES})
        role.permissions.set([perms[c] for c in codes if c in perms])


def seed_leave():
    from apps.leave.models import LeavePolicy, LeaveType

    # Labour Act, 2003 (Act 651): minimum 15 working days annual leave; maternity at least 12 weeks.
    types = [
        dict(code="annual", name="Annual leave", is_paid=True, tracks_balance=True, notice_days=14, color="#2563eb",
             allow_during_probation=False),
        dict(code="sick", name="Sick leave", is_paid=True, tracks_balance=False, requires_attachment=True,
             attachment_after_days=2, is_confidential=True, color="#dc2626"),
        dict(code="maternity", name="Maternity leave", is_paid=True, tracks_balance=True, count_working_days=False,
             gender="female", requires_attachment=True, allow_half_day=False, color="#db2777"),
        dict(code="paternity", name="Paternity leave", is_paid=True, tracks_balance=True, gender="male",
             allow_half_day=False, color="#7c3aed"),
        dict(code="compassionate", name="Compassionate leave", is_paid=True, tracks_balance=True, color="#64748b"),
        dict(code="study", name="Study / exam leave", is_paid=True, tracks_balance=True, requires_attachment=True,
             color="#0891b2"),
        dict(code="casual", name="Casual leave", is_paid=True, tracks_balance=True, max_days_per_request=3,
             color="#ca8a04"),
        dict(code="unpaid", name="Leave without pay", is_paid=False, tracks_balance=False, color="#475569",
             notice_days=30),
    ]
    entitlements = {"annual": D("15"), "maternity": D("84"), "paternity": D("5"), "compassionate": D("5"),
                    "study": D("10"), "casual": D("5")}
    for t in types:
        lt, _ = LeaveType.objects.update_or_create(code=t["code"], defaults=t)
        if lt.code in entitlements and not lt.policies.exists():
            LeavePolicy.objects.create(leave_type=lt, name=f"{lt.name} - standard",
                                       entitlement_days=entitlements[lt.code],
                                       carryover_max_days=D("5") if lt.code == "annual" else D("0"),
                                       carryover_expiry_months=3, prorate_first_year=lt.code == "annual",
                                       service_bonus=[{"years": 5, "days": 3}, {"years": 10, "days": 6}]
                                       if lt.code == "annual" else [])


def seed_payroll():
    from apps.payroll.models import PayElement, PayGroup, StatutoryRateSet, TaxBand, TaxRelief, TaxTable

    note = ("Seeded from published GRA/SSNIT figures for 2024. VERIFY against current Ghana Revenue Authority and "
            "SSNIT/NPRA guidance and have a payroll professional confirm before production use.")
    PayGroup.objects.get_or_create(code="monthly", defaults={"name": "Monthly payroll"})
    StatutoryRateSet.objects.get_or_create(
        name="Ghana statutory rates 2024", effective_from=dt.date(2024, 1, 1),
        defaults={"ssnit_max_insurable_monthly": D("61000"), "overtime_qualifying_annual_income": D("18000"),
                  "source_note": note})
    table, created = TaxTable.objects.get_or_create(name="GRA PAYE monthly (resident) 2024",
                                                    effective_from=dt.date(2024, 1, 1),
                                                    defaults={"source_note": note})
    if created:
        bands = [(D("490"), D("0")), (D("110"), D("5")), (D("130"), D("10")), (D("3166.67"), D("17.5")),
                 (D("16000"), D("25")), (D("30520"), D("30")), (None, D("35"))]
        for i, (w, r) in enumerate(bands, start=1):
            TaxBand.objects.create(table=table, order=i, width=w, rate=r)
    reliefs = [("marriage", "Marriage / responsibility relief", D("1200"), D("0"), 1),
               ("child_education", "Child education relief", D("600"), D("0"), 3),
               ("aged_dependant", "Aged dependant relief", D("1000"), D("0"), 2),
               ("professional_training", "Professional / training relief", D("2000"), D("0"), 1),
               ("old_age", "Old age relief (60+)", D("1500"), D("0"), 1),
               ("disability", "Disability relief", D("0"), D("25"), 1)]
    for code, name, amt, pct, qty in reliefs:
        TaxRelief.objects.get_or_create(code=code, effective_from=dt.date(2024, 1, 1),
                                        defaults={"name": name, "annual_amount": amt, "percent_of_income": pct,
                                                  "max_quantity": qty})
    elements = [
        # code, name, type, category, calc, tax, extra
        ("TRANSPORT", "Transport allowance", "earning", "allowance", "fixed", "normal", {}),
        ("HOUSING", "Housing / rent allowance", "earning", "allowance", "percent_basic", "normal",
         {"default_percent": D("0")}),
        ("RESPONSIBILITY", "Responsibility allowance", "earning", "allowance", "fixed", "normal", {}),
        ("DUTY", "Duty allowance", "earning", "allowance", "fixed", "normal", {}),
        ("NIGHT", "Night duty allowance", "earning", "allowance", "daily", "normal", {}),
        ("ON_CALL", "On-call allowance", "earning", "allowance", "daily", "normal", {}),
        ("FUEL", "Fuel allowance", "earning", "allowance", "fixed", "normal", {}),
        ("UTILITY", "Utility allowance", "earning", "allowance", "fixed", "normal", {}),
        ("BONUS", "Bonus", "earning", "bonus", "fixed", "bonus", {"is_recurring": False, "prorate": False}),
        ("COMMISSION", "Commission", "earning", "commission", "fixed", "normal", {"is_recurring": False,
                                                                               "prorate": False}),
        ("ARREARS", "Salary arrears", "earning", "arrears", "fixed", "normal", {"is_recurring": False,
                                                                             "prorate": False, "is_system": True}),
        ("OVERTIME_MANUAL", "Overtime (manual)", "earning", "overtime", "hourly", "overtime",
         {"is_recurring": False, "multiplier": D("1.5"), "prorate": False}),
        ("UNION", "Union dues", "deduction", "union", "percent_basic", "normal", {"default_percent": D("2")}),
        ("WELFARE", "Staff welfare", "deduction", "welfare", "fixed", "normal", {}),
        ("CREDIT_UNION", "Credit union", "deduction", "other", "fixed", "normal", {}),
        ("INSURANCE_EE", "Medical insurance (employee)", "deduction", "insurance", "fixed", "normal", {}),
        ("INSURANCE_ER", "Medical insurance (employer)", "employer", "insurance", "fixed", "exempt", {}),
    ]
    one_off = {"is_recurring": False, "prorate": False, "is_system": True}
    elements += [
        ("REIMBURSEMENT", "Expense reimbursement", "earning", "other", "fixed", "exempt", one_off),
        ("TRAVEL_ADVANCE", "Travel advance", "earning", "advance", "fixed", "exempt", one_off),
        ("ADVANCE_RECOVERY", "Unspent advance recovery", "deduction", "advance", "fixed", "normal", one_off),
    ]
    for i, (code, name, et, cat, calc, tax, extra) in enumerate(elements):
        PayElement.objects.get_or_create(code=code, defaults={
            "name": name, "element_type": et, "category": cat, "calculation": calc, "tax_treatment": tax,
            "order": 10 + i, **extra})


def seed_workflows():
    from apps.workflow.models import WorkflowDefinition, WorkflowStep

    hr = Role.objects.get(code="hr_officer")
    approver = Role.objects.get(code="payroll_approver")
    hr_dir = Role.objects.get(code="hr_director")
    payroll = Role.objects.get(code="payroll_officer")
    defs = [
        ("leave_request", "Leave approval (standard)", 100, {}, [
            (1, "Supervisor review", "supervisor", None, 48, False),
            (2, "HR validation", "role", hr, 48, True)]),
        ("employee_change", "Personal data change", 100, {}, [(1, "HR verification", "role", hr, 72, False)]),
        ("attendance_correction", "Attendance correction", 100, {}, [
            (1, "Supervisor approval", "supervisor", None, 48, False)]),
        ("letter_request", "HR letter request", 100, {}, [(1, "HR approval", "role", hr, 48, False)]),
        ("loan_request", "Staff loan / advance", 100, {}, [
            (1, "Supervisor endorsement", "supervisor", None, 48, True),
            (2, "Payroll review", "role", payroll, 48, False),
            (3, "HR Director approval", "role", hr_dir, 72, False)]),
        ("payroll_run", "Payroll approval", 100, {}, [(1, "Payroll approver", "role", approver, 24, False)]),
        ("travel_request", "Official travel", 100, {}, [
            (1, "Supervisor approval", "supervisor", None, 48, False),
            (2, "Head of department", "dept_head", None, 48, True)]),
        ("travel_request", "International travel", 50, {"field": "destination_class", "op": "in",
                                                          "value": ["africa", "international"]}, [
            (1, "Supervisor approval", "supervisor", None, 48, False),
            (2, "Head of department", "dept_head", None, 48, True),
            (3, "HR Director approval", "role", hr_dir, 72, False)]),
        ("expense_claim", "Expense claim", 100, {}, [
            (1, "Supervisor approval", "supervisor", None, 48, False),
            (2, "Finance review", "role", Role.objects.get(code="finance_officer"), 48, False)]),
        ("salary_review", "Salary review approval", 100, {}, [(1, "HR Director approval", "role", hr_dir, 120, False)]),
        ("bonus_scheme", "Bonus approval", 100, {}, [(1, "HR Director approval", "role", hr_dir, 120, False)]),
        ("benefit_enrollment", "Benefit enrolment", 100, {}, [(1, "HR verification", "role", hr, 72, False)]),
        ("job_requisition", "Manpower requisition", 100, {}, [
            (1, "Head of department", "dept_head", None, 48, True),
            (2, "HR Director approval", "role", hr_dir, 72, False),
            (3, "Finance (budget) approval", "role", Role.objects.get(code="finance_officer"), 72, False)]),
        ("job_offer", "Offer approval", 100, {}, [(1, "HR Director approval", "role", hr_dir, 48, False)]),
        ("job_offer", "Offer above budget", 50, {"field": "above_budget", "op": "eq", "value": True}, [
            (1, "HR Director approval", "role", hr_dir, 48, False),
            (2, "Finance (budget) approval", "role", Role.objects.get(code="finance_officer"), 48, False)]),
        ("appraisal_objectives", "Objective agreement", 100, {}, [
            (1, "Supervisor agreement", "supervisor", None, 120, False)]),
        ("improvement_plan", "Performance improvement plan", 100, {}, [(1, "HR review", "role", hr, 72, False)]),
        ("probation_outcome", "Probation confirmation", 100, {}, [(1, "HR review", "role", hr, 72, False)]),
        ("probation_outcome", "Probation extension / termination", 50,
         {"field": "recommendation", "op": "in", "value": ["extend", "terminate"]}, [
            (1, "HR review", "role", hr, 72, False),
            (2, "HR Director decision", "role", hr_dir, 72, False)]),
    ]
    for rtype, name, prio, cond, steps in defs:
        d, created = WorkflowDefinition.objects.get_or_create(request_type=rtype, name=name,
                                                              defaults={"priority": prio, "conditions": cond})
        if created:
            for order, sname, atype, role, sla, skip in steps:
                WorkflowStep.objects.create(definition=d, order=order, name=sname, approver_type=atype, role=role,
                                            sla_hours=sla, skip_if_no_approver=skip,
                                            comment_rule="reject")


def seed_servicedesk():
    from apps.servicedesk.models import KnowledgeArticle, ServiceCategory, ServiceType

    hr = Role.objects.get(code="hr_officer")
    payroll = Role.objects.get(code="payroll_officer")
    catalogue = {
        ("records", "Records & letters", 1): [
            ("Employment confirmation letter", "Letter confirming your employment (bank, embassy, landlord).", 8, 48, hr,
             "employment_confirmation", [{"name": "addressed_to", "label": "Addressed to", "required": True},
                                         {"name": "purpose", "label": "Purpose"}]),
            ("Update personal records", "Name change, marital status, ID numbers (attach evidence).", 8, 72, hr, None, []),
            ("Introduction letter", "Letter introducing you to an external institution.", 8, 48, hr, "introduction",
             [{"name": "addressed_to", "label": "Addressed to", "required": True}]),
        ],
        ("payroll", "Payroll & tax", 2): [
            ("Payslip / salary query", "Questions about deductions, net pay or a missing payment.", 4, 48, payroll, None,
             [{"name": "period", "label": "Payroll month", "required": True}]),
            ("Change bank account", "Provide a bank letter or MoMo statement in your name.", 8, 72, payroll, None,
             [{"name": "bank", "label": "New bank / network", "required": True}]),
            ("SSNIT / tax relief query", "SSNIT records, tax relief claims, P9/annual tax certificate.", 8, 120, payroll,
             None, []),
        ],
        ("leave", "Leave & attendance", 3): [
            ("Leave balance correction", "Your leave balance looks wrong.", 8, 72, hr, None, []),
            ("Attendance / biometric issue", "Fingerprint not recognised, missing clock records.", 4, 48, hr, None, []),
        ],
        ("benefits", "Benefits & welfare", 4): [
            ("Medical / insurance claim support", "Help with health insurance cards, claims or dependants.", 8, 72, hr,
             None, []),
            ("Staff welfare request", "Bereavement, wedding or other welfare support.", 8, 72, hr, None, []),
        ],
        ("relations", "Employee relations", 5): [
            ("Raise a grievance", "Confidential. Only the assigned HR officer will see this.", 4, 240, hr, None, []),
        ],
        ("general", "General HR enquiry", 6): [("General question", "Anything else for HR.", 8, 72, hr, None, [])],
    }
    from apps.documents.models import LetterTemplate

    for (code, name, order), services in catalogue.items():
        cat, _ = ServiceCategory.objects.get_or_create(code=code, defaults={"name": name, "order": order})
        for sname, desc, resp, res, role, tpl, form in services:
            ServiceType.objects.get_or_create(category=cat, name=sname, defaults={
                "description": desc, "response_sla_hours": resp, "resolution_sla_hours": res, "team_role": role,
                "letter_template": LetterTemplate.objects.filter(code=tpl).first() if tpl else None,
                "form_fields": form, "is_confidential": code == "relations",
                "default_priority": "high" if code == "relations" else "normal"})
    articles = [
        ("payroll", "How is my PAYE calculated?",
         "PAYE is charged on your chargeable income: taxable earnings minus your 5.5% SSNIT contribution, exempt "
         "provident fund contributions and approved reliefs. The GRA graduated monthly bands are applied to that "
         "amount. Bonuses up to 15% of annual basic are taxed separately at 5%.", "tax,paye,salary,deduction"),
        ("payroll", "When are payslips available?",
         "Payslips are published in My payslips as soon as payroll is released, normally a few days before pay day. "
         "PDF payslips may be protected with your staff number or date of birth (DDMMYYYY).", "payslip,pdf,password"),
        ("leave", "How many days of annual leave do I get?",
         "Your entitlement depends on your category and years of service (minimum 15 working days under the Labour "
         "Act). Weekends and public holidays are not counted. See My leave for your live balance.", "annual,leave,balance"),
        ("records", "How do I get a confirmation of employment letter?",
         "Go to Help desk, choose Employment confirmation letter and fill in who it should be addressed to. HR will "
         "issue it, normally within 2 working days; download it from My documents.", "letter,bank,embassy"),
        ("benefits", "How do I add dependants to my medical insurance?",
         "Open Benefits, select your health plan and update your enrolment with your dependants' details. HR will "
         "verify and update the insurer.", "medical,insurance,dependants"),
    ]
    for code, title, body, tags in articles:
        KnowledgeArticle.objects.get_or_create(title=title, defaults={
            "body": body, "tags": tags, "category": ServiceCategory.objects.filter(code=code).first()})


def seed_expenses_and_benefits():
    from apps.compensation.models import BenefitPlan
    from apps.expenses.models import PerDiemRate
    from apps.payroll.models import PayElement

    start = dt.date(dt.date.today().year, 1, 1)
    rates = [("local", 0, 3, "GHS", 150, 300), ("local", 4, 99, "GHS", 250, 500),
             ("national", 0, 3, "GHS", 250, 450), ("national", 4, 99, "GHS", 400, 800),
             ("africa", 0, 99, "USD", 120, 180), ("international", 0, 99, "USD", 200, 280)]
    for dest, lo, hi, cur, daily, accom in rates:
        PerDiemRate.objects.get_or_create(destination_class=dest, min_grade_level=lo, max_grade_level=hi,
                                          effective_from=start, defaults={"currency": cur, "daily_allowance": daily,
                                                                          "accommodation_cap": accom})
    ins = PayElement.objects.filter(code="INSURANCE_EE").first()
    BenefitPlan.objects.get_or_create(code="medical", defaults={
        "name": "Staff medical insurance", "plan_type": "health", "provider": "Private health insurer",
        "employer_monthly_cost": 250, "employee_monthly_cost": 50, "cost_per_dependant": 40, "max_dependants": 4,
        "min_service_months": 0, "deduction_element": ins, "requires_approval": True})
    BenefitPlan.objects.get_or_create(code="group_life", defaults={
        "name": "Group life assurance", "plan_type": "life", "provider": "Life assurer",
        "employer_monthly_cost": 35, "employee_monthly_cost": 0, "auto_enroll": True, "requires_approval": False})


def seed_documents():
    from apps.documents.models import DocumentCategory, LetterTemplate

    cats = [("contract", "Employment contract", "confidential", False, True),
            ("appointment", "Appointment letter", "confidential", False, True),
            ("certificate", "Academic certificate", "confidential", False, True),
            ("ghana_card", "Ghana Card copy", "confidential", True, True),
            ("license", "Professional licence", "confidential", True, False),
            ("medical", "Medical / fitness record", "restricted", False, False),
            ("disciplinary", "Disciplinary record", "restricted", False, False),
            ("appraisal", "Performance appraisal", "confidential", False, False),
            ("letters", "HR letters", "confidential", False, False),
            ("policy", "Policy / handbook", "internal", False, False),
            ("cv", "CV / application", "confidential", False, False),
            ("other", "Other", "confidential", False, False)]
    for code, name, conf, expiry, mandatory in cats:
        DocumentCategory.objects.get_or_create(code=code, defaults={"name": name, "default_confidentiality": conf,
                                                                    "requires_expiry": expiry,
                                                                    "is_mandatory": mandatory,
                                                                    "visible_to_employee": conf != "restricted"})
    letters_cat = DocumentCategory.objects.get(code="letters")
    templates = {
        "employment_confirmation": ("Confirmation of employment", "employment_confirmation", True, """
<p>{% if addressed_to %}{{ addressed_to }}{% else %}TO WHOM IT MAY CONCERN{% endif %}</p>
<h3>CONFIRMATION OF EMPLOYMENT</h3>
<p>This is to confirm that <b>{{ employee.full_name }}</b> (Staff No. {{ employee.staff_number }}) is a
{{ employee.get_employment_type_display|lower }} employee of {{ organization.name }}, employed since
{{ employee.hire_date|date:"jS F, Y" }}. {% if job_title %}{{ employee.first_name }} currently holds the position of
<b>{{ job_title.name }}</b>{% if department %} in the {{ department.name }}{% endif %}.{% endif %}</p>
{% if purpose %}<p>This letter is issued at the request of the employee for the purpose of {{ purpose }}.</p>{% endif %}
<p>Please do not hesitate to contact us should you require further information.</p>
<br><p>Yours faithfully,</p><br><br><p><b>Head, Human Resource</b><br>{{ organization.name }}</p>"""),
        "appointment": ("Letter of appointment", "appointment", False, """
<p>{{ employee.get_title_display }} {{ employee.full_name }}<br>{{ employee.residential_address|linebreaksbr }}</p>
<p>Dear {{ employee.first_name }},</p>
<h3>OFFER OF APPOINTMENT{% if job_title %} - {{ job_title.name|upper }}{% endif %}</h3>
<p>We are pleased to offer you appointment as <b>{{ job_title.name }}</b>{% if department %} in the
{{ department.name }}{% endif %} with effect from {{ employee.hire_date|date:"jS F, Y" }}.</p>
<p>Your appointment is on grade {{ grade.code }} with a monthly basic salary of GHS {{ salary|floatformat:2 }},
subject to statutory deductions.{% if employee.probation_end_date %} You will serve a probationary period ending
{{ employee.probation_end_date|date:"jS F, Y" }}.{% endif %}</p>
<p>Other terms and conditions are as contained in the conditions of service. Kindly sign and return a copy of this
letter to signify your acceptance.</p>
<br><p>Yours faithfully,</p><br><br><p><b>Head, Human Resource</b></p>"""),
        "confirmation": ("Confirmation of appointment", "confirmation", False, """
<p>Dear {{ employee.first_name }},</p><h3>CONFIRMATION OF APPOINTMENT</h3>
<p>Following the satisfactory completion of your probationary period, we are pleased to confirm your appointment
as {{ job_title.name }} with effect from {{ employee.confirmation_date|default:today|date:"jS F, Y" }}.</p>
<p>Congratulations, and we look forward to your continued contribution.</p>
<br><p>Yours sincerely,</p><br><br><p><b>Head, Human Resource</b></p>"""),
        "offer_letter": ("Offer of employment (candidate)", "appointment", False, """
<p>{{ candidate.full_name }}<br>{{ candidate.email }}</p>
<p>Dear {{ candidate.first_name }},</p>
<h3>OFFER OF EMPLOYMENT - {{ offer.job_title.name|upper }}</h3>
<p>Following your recent interview, we are pleased to offer you employment as <b>{{ offer.job_title.name }}</b>
in the {{ offer.department.name }} of {{ organization.name }} on a {{ offer.get_employment_type_display|lower }}
basis, with effect from <b>{{ offer.start_date|date:"jS F, Y" }}</b>.</p>
<p><b>Remuneration.</b> Your monthly basic salary will be GHS {{ offer.basic_salary|floatformat:2 }}{% if offer.grade %}
(grade {{ offer.grade.code }}{% if offer.grade_step %}, step {{ offer.grade_step.step }}{% endif %}){% endif %}.
{% if allowances %}You will also receive the following monthly allowances:</p><ul>{% for a in allowances %}
<li>{{ a.name }}: GHS {{ a.amount|floatformat:2 }}</li>{% endfor %}</ul><p>{% endif %}
All pay is subject to PAYE income tax, SSNIT and other statutory deductions.</p>
{% if offer.probation_months %}<p><b>Probation.</b> You will serve a probationary period of {{ offer.probation_months }}
month(s){% if probation_end %}, ending on {{ probation_end|date:"jS F, Y" }}{% endif %}, after which your appointment
may be confirmed subject to satisfactory performance.</p>{% endif %}
{% if offer.contract_end_date %}<p><b>Duration.</b> This is a fixed-term engagement ending on
{{ offer.contract_end_date|date:"jS F, Y" }}.</p>{% endif %}
{% if offer.terms %}<p>{{ offer.terms|linebreaksbr }}</p>{% endif %}
<p>This offer is conditional on satisfactory references, verification of your academic and professional
certificates, a pre-employment medical examination and presentation of your Ghana Card and SSNIT number.</p>
<p>Kindly confirm your acceptance by <b>{{ offer.expiry_date|date:"jS F, Y" }}</b> using the secure link sent to you.
This offer lapses if not accepted by that date.</p>
<br><p>Yours faithfully,</p><br><br><p><b>Head, Human Resource</b><br>{{ organization.name }}</p>"""),
        "introduction": ("Letter of introduction", "introduction", True, """
<p>{% if addressed_to %}{{ addressed_to }}{% else %}TO WHOM IT MAY CONCERN{% endif %}</p><h3>LETTER OF INTRODUCTION</h3>
<p>We write to introduce <b>{{ employee.full_name }}</b>, {{ job_title.name }} of {{ organization.name }}.
{% if purpose %}{{ purpose }}{% endif %}</p><p>We would be grateful for any assistance offered.</p>
<br><p>Yours faithfully,</p><br><br><p><b>Head, Human Resource</b></p>"""),
    }
    for code, (name, ltype, ess, body) in templates.items():
        LetterTemplate.objects.get_or_create(code=code, defaults={"name": name, "letter_type": ltype,
                                                                  "body_html": body.strip(), "self_service": ess,
                                                                  "output_category": letters_cat})


def seed_onboarding():
    from apps.documents.models import DocumentCategory
    from apps.onboarding.models import ChecklistTemplate, ChecklistTemplateTask

    tpl, created = ChecklistTemplate.objects.get_or_create(
        name="Standard new-hire onboarding", defaults={"description": "Default checklist for all new employees."})
    if not created:
        return
    cat = {c.code: c for c in DocumentCategory.objects.all()}
    survey = [{"key": "welcome", "label": "How welcome did you feel in your first weeks?", "type": "rating"},
              {"key": "clarity", "label": "How clear are your role and expectations?", "type": "rating"},
              {"key": "tools", "label": "Did you have the tools and access you needed on day one?", "type": "rating"},
              {"key": "comments", "label": "What could we improve for future new hires?", "type": "text"}]
    tasks = [
        # (offset, title, category, owner, doc category, description, form)
        (-10, "Verify academic and professional certificates", "pre_employment", "hr", None, "", []),
        (-7, "Collect Ghana Card, SSNIT number and TIN", "documents", "hr", "ghana_card", "", []),
        (-7, "Collect bank / mobile money details for payroll", "documents", "hr", None, "", []),
        (-5, "Pre-employment medical examination", "pre_employment", "hr", None, "", []),
        (-5, "Sign the employment contract", "documents", "hr", "contract", "", []),
        (-3, "Create network, email and HRMS user account", "access", "it", None,
         "Create accounts and grant application access approved for the role.", []),
        (-3, "Issue laptop / desktop and phone extension", "equipment", "it", None, "", []),
        (-2, "Prepare workstation, ID / access card and uniform", "equipment", "admin", None, "", []),
        (-2, "Add to payroll with grade, bank details and statutory numbers", "access", "finance", None, "", []),
        (0, "Welcome on day one and introduce the team and buddy", "induction", "manager", None, "", []),
        (1, "Organization induction (history, structure, values, conditions of service)", "induction", "hr", None,
         "", []),
        (3, "Departmental induction and role briefing", "induction", "manager", None, "", []),
        (5, "Read and acknowledge the staff handbook and code of conduct", "policy", "employee", None, "", []),
        (5, "Confirm personal details, emergency contacts and beneficiaries in self-service", "documents",
         "employee", None, "", []),
        (7, "Agree probation objectives with the new employee", "probation", "manager", None, "", []),
        (14, "Complete mandatory training (health & safety, data protection)", "training", "employee", None, "", []),
        (30, "New-hire feedback survey", "survey", "employee", None, "", survey),
    ]
    for i, (offset, title, category, owner, doc, desc, form) in enumerate(tasks):
        ChecklistTemplateTask.objects.create(template=tpl, order=i, title=title, category=category, owner_type=owner,
                                             due_offset_days=offset, document_category=cat.get(doc) if doc else None,
                                             description=desc, form=form, is_mandatory=category != "survey")


def seed_performance():
    from apps.performance.models import DEFAULT_LEVELS, AppraisalTemplate, Competency, RatingScale

    scale, _ = RatingScale.objects.get_or_create(name="5-point scale", defaults={"levels": DEFAULT_LEVELS,
                                                                                 "is_default": True})
    comps = [
        ("core", "Integrity and professionalism", "Acts honestly, keeps confidences, follows the code of conduct."),
        ("core", "Customer and patient focus", "Treats clients and patients with respect; responds promptly."),
        ("core", "Teamwork and collaboration", "Shares information, supports colleagues, resolves conflict."),
        ("core", "Communication", "Communicates clearly and respectfully, verbally and in writing."),
        ("core", "Accountability and reliability", "Meets commitments, punctual, owns mistakes and fixes them."),
        ("technical", "Job knowledge and skills", "Applies the knowledge, tools and procedures the role requires."),
        ("technical", "Quality and accuracy of work", "Produces complete, accurate work that needs little rework."),
        ("leadership", "Leading and developing people", "Sets direction, coaches, gives feedback, develops staff."),
        ("leadership", "Planning and decision making", "Plans resources, prioritises and makes sound decisions."),
        ("clinical", "Patient safety and infection control", "Follows safety protocols, IPC and medication safety."),
        ("clinical", "Clinical documentation", "Keeps accurate, timely and complete patient records."),
        ("clinical", "Clinical competence", "Delivers evidence-based care within scope of practice."),
    ]
    by_name = {}
    for cat, name, desc in comps:
        by_name[name], _ = Competency.objects.get_or_create(name=name, defaults={"category": cat, "description": desc})
    core = [c for c in by_name.values() if c.category == "core"]
    tpl, created = AppraisalTemplate.objects.get_or_create(name="Standard staff appraisal", defaults={
        "rating_scale": scale, "objectives_weight": 70})
    if created:
        tpl.competencies.set(core + [by_name["Job knowledge and skills"], by_name["Quality and accuracy of work"]])
    tpl, created = AppraisalTemplate.objects.get_or_create(name="Clinical staff appraisal", defaults={
        "rating_scale": scale, "objectives_weight": 60, "clinical_only": True})
    if created:
        tpl.competencies.set(core + [c for c in by_name.values() if c.category == "clinical"])


def seed_attendance():
    from apps.attendance.models import AttendancePolicy, Shift

    day, _ = Shift.objects.get_or_create(code="day", defaults={"name": "Day (08:00-17:00)", "start_time": dt.time(8),
                                                               "end_time": dt.time(17), "break_minutes": 60})
    Shift.objects.get_or_create(code="morning", defaults={"name": "Morning (07:00-15:00)", "start_time": dt.time(7),
                                                          "end_time": dt.time(15), "break_minutes": 30,
                                                          "color": "#22c55e"})
    Shift.objects.get_or_create(code="afternoon", defaults={"name": "Afternoon (14:00-21:00)",
                                                            "start_time": dt.time(14), "end_time": dt.time(21),
                                                            "break_minutes": 30, "color": "#f59e0b"})
    Shift.objects.get_or_create(code="night", defaults={"name": "Night (21:00-07:00)", "start_time": dt.time(21),
                                                        "end_time": dt.time(7), "break_minutes": 30, "is_night": True,
                                                        "color": "#6366f1"})
    AttendancePolicy.objects.get_or_create(name="Standard office policy", defaults={
        "default_shift": day, "weekend_days": [5, 6], "priority": 1000})


@transaction.atomic
def setup_organization(name, code, admin_username=None, admin_password=None, admin_email="", features=None,
                       require_mfa=True):
    from django.contrib.auth import get_user_model

    from apps.core.ghana import seed_public_holidays
    from apps.rbac.models import RoleAssignment

    org, _ = Organization.objects.get_or_create(code=code, defaults={"name": name, "legal_name": name})
    with org_context(org):
        seed_permissions()
        seed_roles(require_mfa=require_mfa)
        for f in features or ["payroll"]:
            OrganizationFeature.objects.update_or_create(organization=org, code=f, defaults={"enabled": True})
        seed_leave()
        seed_payroll()
        seed_workflows()
        seed_documents()
        seed_attendance()
        seed_servicedesk()
        seed_expenses_and_benefits()
        seed_onboarding()
        seed_performance()
        year = dt.date.today().year
        seed_public_holidays(year)
        seed_public_holidays(year + 1)
        admin = None
        if admin_username:
            User = get_user_model()
            admin = User.objects.filter(username=admin_username).first()
            if admin is None:
                admin = User.objects.create_user(admin_username, admin_email, admin_password, organization=org,
                                                 is_staff=True, first_name="System", last_name="Administrator")
            for rc in ("sys_admin", "hr_director"):
                RoleAssignment.objects.get_or_create(user=admin, role=Role.objects.get(code=rc))
    return org, admin
