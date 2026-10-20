"""Ghana gross-to-net payroll engine.

A pure function: `calculate(PayInputs, Rules) -> PayResult`. It has no database access, so every
result is reproducible from its inputs and the versioned rule set, and it is fully unit-testable.

Order of calculation
 1. Pro-rated basic salary (days payable / days in period)
 2. Earnings (fixed, % basic, hourly/daily, formula, then % of gross), attendance overtime, leave pay
 3. SSNIT on basic (employee 5.5%, employer 13%; Tier 1 13.5% to SSNIT, Tier 2 5% to trustee), capped
    at the maximum insurable earnings when configured
 4. Voluntary Tier 3 (tax-exempt up to the configured % of basic)
 5. Bonus: portion up to 15% of annual basic (less bonus already received in the year) taxed at 5%,
    the excess is added to taxable income
 6. Overtime: for qualifying (junior) staff, OT up to 50% of monthly basic taxed at 5%, excess at 10%;
    otherwise OT is added to taxable income
 7. Chargeable income = taxable earnings - SSNIT employee - exempt Tier 3 - pre-tax deductions - reliefs
 8. PAYE on graduated monthly bands (resident) or a flat rate (non-resident)
 9. Other deductions and loan instalments, net pay, employer contributions and cost

All statutory parameters come from `Rules`, built from effective-dated configuration.
"""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from .formula import evaluate

D0 = Decimal("0")
HUNDRED = Decimal("100")


def q(x) -> Decimal:
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def pct(base, rate) -> Decimal:
    return Decimal(base) * Decimal(rate) / HUNDRED


@dataclass
class ElementInput:
    code: str
    name: str
    element_type: str  # earning | deduction | employer | info
    category: str = "other"
    calculation: str = "fixed"
    amount: Decimal = D0
    percent: Decimal = D0
    quantity: Decimal | None = None
    multiplier: Decimal = Decimal("1")
    formula: str = ""
    tax_treatment: str = "normal"
    prorate: bool = True
    gl_account: str = ""
    order: int = 100
    show: bool = True
    element_id: int | None = None
    reference: str = ""


@dataclass
class LoanInput:
    loan_id: int
    name: str
    installment: Decimal
    balance: Decimal
    category: str = "loan"


@dataclass
class Rules:
    bands: list  # [(width or None, rate%)] ascending
    ssnit_employee_rate: Decimal = Decimal("5.5")
    ssnit_employer_rate: Decimal = Decimal("13")
    tier1_rate: Decimal = Decimal("13.5")
    tier2_rate: Decimal = Decimal("5")
    ssnit_cap: Decimal = D0
    tier3_exempt_percent: Decimal = Decimal("16.5")
    bonus_rate: Decimal = Decimal("5")
    bonus_exempt_percent: Decimal = Decimal("15")
    ot_qualifying_income: Decimal = D0
    ot_rate_low: Decimal = Decimal("5")
    ot_rate_high: Decimal = Decimal("10")
    ot_threshold_percent: Decimal = Decimal("50")
    non_resident_rate: Decimal = Decimal("25")


@dataclass
class PayInputs:
    monthly_basic: Decimal
    days_in_period: Decimal
    days_payable: Decimal
    is_resident: bool = True
    paye_exempt: bool = False
    ssnit_applicable: bool = True
    tier3_employee_percent: Decimal = D0
    tier3_employer_percent: Decimal = D0
    hours_per_month: Decimal = Decimal("176")
    ot_hours_normal: Decimal = D0
    ot_hours_weekend: Decimal = D0
    ot_hours_holiday: Decimal = D0
    ot_weekday_multiplier: Decimal = Decimal("1.5")
    ot_weekend_multiplier: Decimal = Decimal("2")
    ot_holiday_multiplier: Decimal = Decimal("2")
    elements: list = field(default_factory=list)
    loans: list = field(default_factory=list)
    annual_reliefs: Decimal = D0
    ytd_bonus: Decimal = D0
    recover_full_loans: bool = False
    leave_encashment_days: Decimal = D0
    min_net_percent: Decimal = Decimal("0")


@dataclass
class Line:
    code: str
    name: str
    line_type: str
    amount: Decimal
    category: str = ""
    quantity: Decimal | None = None
    rate: Decimal | None = None
    taxable: bool = True
    tax_treatment: str = "normal"
    gl_account: str = ""
    element_id: int | None = None
    reference: str = ""
    order: int = 100
    show: bool = True


@dataclass
class PayResult:
    lines: list
    basic_pay: Decimal
    gross: Decimal
    taxable_income: Decimal
    paye: Decimal
    bonus_tax: Decimal
    overtime_tax: Decimal
    ssnit_employee: Decimal
    ssnit_employer: Decimal
    tier1: Decimal
    tier2: Decimal
    tier3_employee: Decimal
    tier3_employer: Decimal
    reliefs: Decimal
    total_deductions: Decimal
    net: Decimal
    employer_cost: Decimal
    messages: list
    status: str
    loan_deductions: dict


def graduated_tax(chargeable: Decimal, bands) -> Decimal:
    remaining = Decimal(chargeable)
    tax = D0
    for width, rate in bands:
        if remaining <= 0:
            break
        portion = remaining if width is None else min(remaining, Decimal(width))
        tax += pct(portion, rate)
        remaining -= portion
    return q(tax)


def _element_amount(el: ElementInput, ctx: dict) -> tuple[Decimal, Decimal | None, Decimal | None]:
    """Returns (amount, quantity, rate)."""
    factor = ctx["factor"] if el.prorate else Decimal("1")
    if el.calculation == "fixed":
        return q(el.amount * factor), None, None
    if el.calculation == "percent_basic":
        return q(pct(ctx["basic"], el.percent) * factor), None, el.percent
    if el.calculation == "percent_gross":
        return q(pct(ctx["gross"], el.percent)), None, el.percent
    if el.calculation == "hourly":
        qty = el.quantity or D0
        rate = ctx["hourly_rate"] * el.multiplier
        return q(qty * rate), qty, q(rate)
    if el.calculation == "daily":
        qty = el.quantity or D0
        rate = ctx["daily_rate"] * el.multiplier
        return q(qty * rate), qty, q(rate)
    if el.calculation == "formula":
        variables = dict(ctx)
        variables["quantity"] = el.quantity or D0
        variables["amount"] = el.amount
        variables["percent"] = el.percent
        return q(evaluate(el.formula, variables)), el.quantity, None
    return D0, None, None


def calculate(inp: PayInputs, rules: Rules) -> PayResult:
    messages: list[str] = []
    lines: list[Line] = []
    basic = Decimal(inp.monthly_basic)
    days_in_period = Decimal(inp.days_in_period) or Decimal("1")
    factor = max(min(Decimal(inp.days_payable) / days_in_period, Decimal("1")), D0)
    basic_pay = q(basic * factor)
    hourly_rate = basic / Decimal(inp.hours_per_month or 1)
    daily_rate = basic / days_in_period
    ctx = {"basic": basic, "basic_pay": basic_pay, "factor": factor, "days_payable": inp.days_payable,
           "days_in_period": days_in_period, "hourly_rate": hourly_rate, "daily_rate": daily_rate, "gross": D0}

    if factor < 1:
        messages.append(f"Pro-rated: {inp.days_payable} of {days_in_period} days payable.")
    lines.append(Line("BASIC", "Basic salary", "earning", basic_pay, category="basic", order=0,
                      quantity=Decimal(inp.days_payable), rate=q(daily_rate)))

    # earnings, two passes (percent_gross last)
    earnings = [e for e in inp.elements if e.element_type == "earning"]
    for el in [e for e in earnings if e.calculation != "percent_gross"]:
        amount, qty, rate = _element_amount(el, ctx)
        if amount:
            lines.append(Line(el.code, el.name, "earning", amount, el.category, qty, rate,
                              el.tax_treatment != "exempt", el.tax_treatment, el.gl_account, el.element_id,
                              el.reference, el.order, el.show))
    ot_specs = [("OT_NORMAL", "Overtime (weekday)", inp.ot_hours_normal, inp.ot_weekday_multiplier),
                ("OT_WEEKEND", "Overtime (rest day)", inp.ot_hours_weekend, inp.ot_weekend_multiplier),
                ("OT_HOLIDAY", "Overtime (public holiday)", inp.ot_hours_holiday, inp.ot_holiday_multiplier)]
    for code, name, hours, mult in ot_specs:
        if hours and hours > 0:
            rate = q(hourly_rate * Decimal(mult))
            lines.append(Line(code, name, "earning", q(Decimal(hours) * rate), "overtime", Decimal(hours), rate,
                              True, "overtime", order=50))
    if inp.leave_encashment_days and inp.leave_encashment_days > 0:
        lines.append(Line("LEAVE_PAY", "Leave encashment", "earning", q(inp.leave_encashment_days * daily_rate),
                          "leave_pay", inp.leave_encashment_days, q(daily_rate), True, "normal", order=60))
    ctx["gross"] = sum((ln.amount for ln in lines if ln.line_type == "earning"), D0)
    for el in [e for e in earnings if e.calculation == "percent_gross"]:
        amount, qty, rate = _element_amount(el, ctx)
        if amount:
            lines.append(Line(el.code, el.name, "earning", amount, el.category, qty, rate,
                              el.tax_treatment != "exempt", el.tax_treatment, el.gl_account, el.element_id,
                              el.reference, el.order, el.show))
    gross = q(sum((ln.amount for ln in lines if ln.line_type == "earning"), D0))
    ctx["gross"] = gross

    # SSNIT (on basic actually paid)
    ssnit_ee = ssnit_er = tier1 = tier2 = D0
    if inp.ssnit_applicable:
        base = min(basic_pay, rules.ssnit_cap) if rules.ssnit_cap and rules.ssnit_cap > 0 else basic_pay
        if rules.ssnit_cap and basic_pay > rules.ssnit_cap:
            messages.append("SSNIT capped at maximum insurable earnings.")
        ssnit_ee = q(pct(base, rules.ssnit_employee_rate))
        ssnit_er = q(pct(base, rules.ssnit_employer_rate))
        tier1 = q(pct(base, rules.tier1_rate))
        tier2 = q(ssnit_ee + ssnit_er - tier1)

    # Tier 3
    tier3_ee = q(pct(basic_pay, inp.tier3_employee_percent))
    tier3_er = q(pct(basic_pay, inp.tier3_employer_percent))
    exempt_cap = q(pct(basic_pay, rules.tier3_exempt_percent))
    exempt_ee = min(tier3_ee, max(exempt_cap - tier3_er, D0))
    taxable_er_excess = max(tier3_er - exempt_cap, D0)

    annual_basic = basic * 12
    by_treatment = {}
    for ln in lines:
        if ln.line_type == "earning":
            by_treatment[ln.tax_treatment] = by_treatment.get(ln.tax_treatment, D0) + ln.amount

    bonus_total = by_treatment.get("bonus", D0)
    ot_total = by_treatment.get("overtime", D0)
    normal_taxable = by_treatment.get("normal", D0)
    bonus_tax = overtime_tax = D0
    resident = inp.is_resident

    if resident:
        allowance_left = max(pct(annual_basic, rules.bonus_exempt_percent) - inp.ytd_bonus, D0)
        bonus_flat = min(bonus_total, allowance_left)
        bonus_excess = bonus_total - bonus_flat
        bonus_tax = q(pct(bonus_flat, rules.bonus_rate))
        normal_taxable += bonus_excess
        if bonus_excess:
            messages.append(f"Bonus above {rules.bonus_exempt_percent}% of annual basic ({q(bonus_excess)}) taxed as income.")
        qualifies = rules.ot_qualifying_income and annual_basic <= rules.ot_qualifying_income
        if ot_total and qualifies:
            threshold = pct(basic, rules.ot_threshold_percent)
            low = min(ot_total, threshold)
            high = max(ot_total - threshold, D0)
            overtime_tax = q(pct(low, rules.ot_rate_low) + pct(high, rules.ot_rate_high))
        else:
            normal_taxable += ot_total
    else:
        normal_taxable += bonus_total + ot_total
    normal_taxable += taxable_er_excess

    # deductions (excluding statutory) - pre-tax first
    deductions = [e for e in inp.elements if e.element_type == "deduction"]
    pre_tax_total = D0
    other_lines: list[Line] = []
    for el in deductions:
        amount, qty, rate = _element_amount(el, ctx)
        if not amount:
            continue
        ln = Line(el.code, el.name, "deduction", amount, el.category, qty, rate, False, el.tax_treatment,
                  el.gl_account, el.element_id, el.reference, el.order + 100, el.show)
        other_lines.append(ln)
        if el.tax_treatment == "pre_tax":
            pre_tax_total += amount

    reliefs = q(Decimal(inp.annual_reliefs) / 12) if resident else D0
    taxable_income = q(max(normal_taxable - ssnit_ee - exempt_ee - pre_tax_total - reliefs, D0))
    if inp.paye_exempt:
        paye = bonus_tax = overtime_tax = D0
        messages.append("Employee is PAYE exempt.")
    elif resident:
        paye = graduated_tax(taxable_income, rules.bands)
    else:
        paye = q(pct(taxable_income, rules.non_resident_rate))

    statutory = [("PAYE", "Income tax (PAYE)", paye, "statutory", 1),
                 ("BONUS_TAX", "Tax on bonus", bonus_tax, "statutory", 2),
                 ("OT_TAX", "Tax on overtime", overtime_tax, "statutory", 3),
                 ("SSNIT_EE", f"SSNIT employee ({rules.ssnit_employee_rate}%)", ssnit_ee, "statutory", 4),
                 ("TIER3_EE", "Provident fund (Tier 3)", tier3_ee, "pension", 5)]
    for code, name, amount, cat, order in statutory:
        if amount:
            lines.append(Line(code, name, "deduction", amount, cat, taxable=False, order=order))
    lines.extend(other_lines)

    # loans
    loan_deductions = {}
    for loan in inp.loans:
        amount = loan.balance if inp.recover_full_loans else min(loan.installment, loan.balance)
        amount = q(max(amount, D0))
        if amount:
            loan_deductions[loan.loan_id] = amount
            lines.append(Line(f"LOAN_{loan.loan_id}", loan.name, "deduction", amount, loan.category, taxable=False,
                              reference=str(loan.loan_id), order=150))

    total_deductions = q(sum((ln.amount for ln in lines if ln.line_type == "deduction"), D0))
    net = q(gross - total_deductions)

    # employer contributions
    employer_lines = []
    if ssnit_er:
        employer_lines.append(Line("SSNIT_ER", f"SSNIT employer ({rules.ssnit_employer_rate}%)", "employer", ssnit_er,
                                   "statutory", taxable=False, order=1))
    if tier3_er:
        employer_lines.append(Line("TIER3_ER", "Provident fund employer (Tier 3)", "employer", tier3_er, "pension",
                                   taxable=False, order=2))
    for el in [e for e in inp.elements if e.element_type in ("employer", "info")]:
        amount, qty, rate = _element_amount(el, ctx)
        if amount:
            employer_lines.append(Line(el.code, el.name, el.element_type, amount, el.category, qty, rate, False,
                                       el.tax_treatment, el.gl_account, el.element_id, el.reference, el.order,
                                       el.show))
    lines.extend(employer_lines)
    employer_cost = q(gross + sum((ln.amount for ln in employer_lines if ln.line_type == "employer"), D0))

    status = "ok"
    if net < 0:
        status = "error"
        messages.append("Net pay is negative - review deductions and loans.")
    elif gross > 0 and inp.min_net_percent and net < pct(gross, inp.min_net_percent):
        status = "warning"
        messages.append(f"Net pay is below {inp.min_net_percent}% of gross.")
    if basic <= 0:
        status = "error"
        messages.append("No basic salary.")

    return PayResult(lines=lines, basic_pay=basic_pay, gross=gross, taxable_income=taxable_income, paye=paye,
                     bonus_tax=bonus_tax, overtime_tax=overtime_tax, ssnit_employee=ssnit_ee, ssnit_employer=ssnit_er,
                     tier1=tier1, tier2=tier2, tier3_employee=tier3_ee, tier3_employer=tier3_er, reliefs=reliefs,
                     total_deductions=total_deductions, net=net, employer_cost=employer_cost, messages=messages,
                     status=status, loan_deductions=loan_deductions)
