"""Payroll outputs: bank/MoMo payment files, GL journal, GRA PAYE schedule, SSNIT contribution report,
payroll register, variance report and payslip PDFs."""

from collections import defaultdict
from decimal import Decimal

from django.template.loader import render_to_string

from apps.core.pdf import BASE_CSS, encrypt_pdf, html_to_pdf

from .models import Payslip, PayslipLine

D0 = Decimal("0")


def bank_file_rows(run, method="bank"):
    headers = ["Staff No", "Beneficiary name", "Bank", "Bank code", "Branch / sort code", "Account / wallet no",
               "Amount (GHS)", "Narration"]
    rows = []
    for slip in run.payslips.exclude(status__in=["hold", "error"]).select_related("employee"):
        acct = slip.employee.bank_accounts.filter(is_primary=True, payment_method=method).first()
        if acct is None or slip.net_pay <= 0:
            continue
        number = acct.account_number if method == "bank" else acct.momo_number
        name = acct.account_name or slip.employee_name
        bank = acct.bank_name if method == "bank" else acct.get_momo_network_display()
        rows.append([slip.staff_number, name, bank, acct.bank_code, acct.branch_code, number, slip.net_pay,
                     f"Salary {run.period.name}"])
    return headers, rows


def payroll_register(run):
    slips = list(run.payslips.prefetch_related("lines"))
    codes = []
    seen = set()
    for s in slips:
        for ln in s.lines.all():
            key = (ln.line_type, ln.code)
            if key not in seen:
                seen.add(key)
                codes.append((ln.line_type, ln.code, ln.name))
    order = {"earning": 0, "deduction": 1, "employer": 2, "info": 3}
    codes.sort(key=lambda c: (order.get(c[0], 9), c[1] != "BASIC", c[1]))
    headers = ["Staff No", "Name", "Department", "Grade", "Days payable"] + [f"{n}" for _, _, n in codes] + [
        "Gross", "Total deductions", "Net pay", "Employer cost", "Status"]
    rows = []
    for s in slips:
        amounts = {(ln.line_type, ln.code): ln.amount for ln in s.lines.all()}
        rows.append([s.staff_number, s.employee_name, s.department, s.grade, s.days_payable]
                    + [amounts.get((t, c), D0) for t, c, _ in codes]
                    + [s.gross_pay, s.total_deductions, s.net_pay, s.employer_cost, s.get_status_display()])
    money_cols = list(range(5, len(headers) - 1))
    return headers, rows, money_cols


def paye_schedule(run):
    """Monthly PAYE schedule for GRA filing (columns follow the common GRA template; confirm current format)."""
    headers = ["S/N", "TIN / Ghana Card", "Employee name", "Position", "Basic salary", "Allowances & other income",
               "Gross income", "SSNIT (5.5%)", "Tier 3 (exempt)", "Reliefs", "Chargeable income", "PAYE",
               "Bonus tax", "Overtime tax", "Total tax"]
    rows = []
    for i, s in enumerate(run.payslips.select_related("employee").order_by("staff_number"), start=1):
        tax_id = s.tin or s.employee.ghana_card_no
        total_tax = s.paye + s.bonus_tax + s.overtime_tax
        rows.append([i, tax_id, s.employee_name, s.job_title, s.basic_pay, s.gross_pay - s.basic_pay, s.gross_pay,
                     s.ssnit_employee, s.tier3_employee, s.reliefs, s.taxable_income, s.paye, s.bonus_tax,
                     s.overtime_tax, total_tax])
    return headers, rows, list(range(4, 15))


def ssnit_report(run):
    headers = ["S/N", "SSNIT number", "Ghana Card", "Employee name", "Basic salary", "Employee 5.5%",
               "Employer 13%", "Total 18.5%", "Tier 1 (13.5%) to SSNIT", "Tier 2 (5%) to trustee"]
    rows = []
    for i, s in enumerate(run.payslips.filter(ssnit_employee__gt=0).select_related("employee")
                          .order_by("staff_number"), start=1):
        rows.append([i, s.ssnit_number, s.employee.ghana_card_no, s.employee_name, s.basic_pay, s.ssnit_employee,
                     s.ssnit_employer, s.ssnit_employee + s.ssnit_employer, s.tier1, s.tier2])
    return headers, rows, list(range(4, 10))


def gl_journal(run):
    """Summarised journal by cost centre and account. Expense debits; liability credits."""
    debits = defaultdict(lambda: D0)
    credits = defaultdict(lambda: D0)
    settings = run.organization.settings.get("gl_accounts", {}) if run.organization_id else {}
    acc = {"salary_expense": settings.get("salary_expense", "6000"),
           "employer_expense": settings.get("employer_expense", "6100"),
           "paye": settings.get("paye_payable", "2100"), "ssnit": settings.get("ssnit_payable", "2110"),
           "tier2": settings.get("tier2_payable", "2120"), "tier3": settings.get("tier3_payable", "2130"),
           "net": settings.get("net_salaries_payable", "2200"), "loans": settings.get("staff_loans", "1300"),
           "other": settings.get("other_deductions_payable", "2190")}
    for line in PayslipLine.objects.filter(payslip__run=run).select_related("payslip"):
        cc = line.payslip.cost_center or "UNALLOCATED"
        if line.line_type == "earning":
            debits[(cc, line.gl_account or acc["salary_expense"], line.name if line.gl_account else "Salaries & wages")] += line.amount
        elif line.line_type == "employer":
            debits[(cc, line.gl_account or acc["employer_expense"], f"Employer {line.name}")] += line.amount
            target = acc["ssnit"] if line.code == "SSNIT_ER" else acc["tier3"] if line.code == "TIER3_ER" else acc["other"]
            credits[("", target, f"{line.name} payable")] += line.amount
        elif line.line_type == "deduction":
            if line.code in ("PAYE", "BONUS_TAX", "OT_TAX"):
                credits[("", acc["paye"], "PAYE payable (GRA)")] += line.amount
            elif line.code == "SSNIT_EE":
                credits[("", acc["ssnit"], "SSNIT payable")] += line.amount
            elif line.code == "TIER3_EE":
                credits[("", acc["tier3"], "Provident fund payable")] += line.amount
            elif line.code.startswith("LOAN_"):
                credits[("", acc["loans"], "Staff loans & advances")] += line.amount
            else:
                credits[("", line.gl_account or acc["other"], f"{line.name} payable")] += line.amount
    net = sum((s.net_pay for s in run.payslips.all()), D0)
    credits[("", acc["net"], "Net salaries payable")] += net
    headers = ["Cost centre", "Account", "Description", "Debit", "Credit"]
    rows = [[cc, a, d, amt, D0] for (cc, a, d), amt in sorted(debits.items()) if amt]
    rows += [[cc, a, d, D0, amt] for (cc, a, d), amt in sorted(credits.items()) if amt]
    return headers, rows, [3, 4]


def variance_report(run):
    from .services import previous_payslips

    prev = previous_payslips(run)
    headers = ["Staff No", "Name", "Previous net", "Current net", "Change", "Change %", "Note"]
    rows = []
    current_ids = set()
    for s in run.payslips.all():
        current_ids.add(s.employee_id)
        p = prev.get(s.employee_id)
        if p is None:
            rows.append([s.staff_number, s.employee_name, D0, s.net_pay, s.net_pay, "", "New this period"])
            continue
        change = s.net_pay - p.net_pay
        pct = (change / p.net_pay * 100).quantize(Decimal("0.1")) if p.net_pay else ""
        if change:
            rows.append([s.staff_number, s.employee_name, p.net_pay, s.net_pay, change, pct, ""])
    for emp_id, p in prev.items():
        if emp_id not in current_ids:
            rows.append([p.staff_number, p.employee_name, p.net_pay, D0, -p.net_pay, "", "Not on this payroll"])
    return headers, rows, [2, 3, 4]


def payslip_pdf(slip: Payslip, encrypt=True) -> bytes:
    run = slip.run
    org = run.organization
    lines = list(slip.lines.filter(show_on_payslip=True))
    html = render_to_string("pdf/payslip.html", {
        "slip": slip, "run": run, "org": org, "css": BASE_CSS,
        "earnings": [ln for ln in lines if ln.line_type == "earning"],
        "deductions": [ln for ln in lines if ln.line_type == "deduction"],
        "employer": [ln for ln in lines if ln.line_type == "employer"],
    })
    pdf = html_to_pdf(html)
    mode = run.period.pay_group.payslip_password
    if encrypt and mode != "none":
        emp = slip.employee
        password = emp.staff_number if mode == "staff_number" else (
            emp.date_of_birth.strftime("%d%m%Y") if emp.date_of_birth else emp.staff_number)
        pdf = encrypt_pdf(pdf, password)
    return pdf
