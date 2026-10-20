import { Alert, Button, Card, Stack, Tab, Tabs, TextField, Typography } from "@mui/material";
import { useState } from "react";
import { post } from "../../api/hooks";
import { PageHeader } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtDate, fmtMoney, titleCase } from "../../utils";

const opts = (xs: string[]) => xs.map((v) => ({ value: v, label: titleCase(v) }));

function PayeCalculator({ tableId }: { tableId: number }) {
  const [amount, setAmount] = useState("4725");
  const [paye, setPaye] = useState<string | null>(null);
  return (
    <Stack direction="row" spacing={1} alignItems="center" sx={{ p: 1.5 }}>
      <Typography variant="body2">PAYE check — chargeable monthly income:</Typography>
      <TextField size="small" value={amount} onChange={(e) => setAmount(e.target.value)} sx={{ width: 140 }} />
      <Button size="small" onClick={async () => setPaye((await post<{ paye: string }>(`/payroll/tax-tables/${tableId}/compute/`, { amount })).paye)}>Compute</Button>
      {paye !== null && <Typography fontWeight={650}>{fmtMoney(paye)}</Typography>}
    </Stack>
  );
}

export default function PayrollSetup() {
  const [tab, setTab] = useState(0);
  const [table, setTable] = useState<number | null>(null);
  return (
    <>
      <PageHeader title="Payroll setup & statutory rules" />
      <Alert severity="warning" sx={{ mb: 2 }}>
        Statutory tables are versioned by effective date. Seeded Ghana PAYE bands, SSNIT rates and reliefs must be verified against current
        GRA, SSNIT and NPRA guidance by a payroll professional, then marked as verified.
      </Alert>
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }} variant="scrollable">
        <Tab label="Pay elements" /><Tab label="PAYE tax tables" /><Tab label="SSNIT & statutory rates" /><Tab label="Tax reliefs" /><Tab label="Pay groups" />
      </Tabs>
      <Card>
        {tab === 0 && <ResourcePage embedded title="Pay element" url="/payroll/elements/" canDelete
          columns={[{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "element_type", label: "Type", render: (r) => titleCase(r.element_type as string) },
            { key: "calculation", label: "Calculation", render: (r) => titleCase(r.calculation as string) },
            { key: "tax_treatment", label: "Tax", render: (r) => titleCase(r.tax_treatment as string) },
            { key: "applies_to_all", label: "All staff", render: (r) => (r.applies_to_all ? "Yes" : "") },
            { key: "is_active", label: "Active", render: (r) => (r.is_active ? "Yes" : "No") }]}
          fields={[{ name: "code", label: "Code", required: true, width: 4 }, { name: "name", label: "Name", required: true, width: 8 },
            { name: "element_type", label: "Type", type: "select", required: true, width: 4, options: opts(["earning", "deduction", "employer", "info"]) },
            { name: "category", label: "Category", type: "select", width: 4, options: opts(["allowance", "overtime", "bonus", "commission", "arrears", "benefit", "leave_pay", "loan", "advance", "pension", "union", "welfare", "insurance", "other"]) },
            { name: "calculation", label: "Calculation", type: "select", width: 4, options: [{ value: "fixed", label: "Fixed amount" }, { value: "percent_basic", label: "% of basic" }, { value: "percent_gross", label: "% of gross" }, { value: "hourly", label: "Hours × hourly rate" }, { value: "daily", label: "Days × daily rate" }, { value: "formula", label: "Formula" }] },
            { name: "default_amount", label: "Default amount", type: "number", width: 4 }, { name: "default_percent", label: "Default %", type: "number", width: 4 },
            { name: "multiplier", label: "Rate multiplier", type: "number", width: 4 },
            { name: "formula", label: "Formula", helper: "Variables: basic, basic_pay, gross, factor, days_payable, days_in_period, hourly_rate, daily_rate, quantity. Functions: min, max, round", hidden: (v) => v.calculation !== "formula" },
            { name: "tax_treatment", label: "Tax treatment", type: "select", width: 6, options: [{ value: "normal", label: "Taxable (PAYE)" }, { value: "bonus", label: "Bonus (5% up to 15% of annual basic)" }, { value: "overtime", label: "Overtime (junior staff rates)" }, { value: "exempt", label: "Exempt" }, { value: "pre_tax", label: "Pre-tax deduction" }] },
            { name: "gl_account", label: "GL account", width: 6 },
            { name: "prorate", label: "Pro-rate partial months", type: "checkbox", width: 4 }, { name: "applies_to_all", label: "Applies to all staff", type: "checkbox", width: 4 },
            { name: "show_on_payslip", label: "Show on payslip", type: "checkbox", width: 4 }, { name: "is_active", label: "Active", type: "checkbox", width: 4 },
            { name: "order", label: "Display order", type: "number", width: 4 }]}
          defaults={{ element_type: "earning", calculation: "fixed", tax_treatment: "normal", prorate: true, show_on_payslip: true, is_active: true, multiplier: 1, order: 100, category: "allowance" }} />}
        {tab === 1 && <>
          <ResourcePage embedded title="Tax table" url="/payroll/tax-tables/" onRowClick={(r) => setTable(r.id as number)}
            columns={[{ key: "name", label: "Name" }, { key: "effective_from", label: "From", render: (r) => fmtDate(r.effective_from as string) },
              { key: "effective_to", label: "To", render: (r) => fmtDate(r.effective_to as string) },
              { key: "bands", label: "Bands (chargeable amount @ rate)", render: (r) => (r.bands as { width: string | null; rate: string }[]).map((b) => `${b.width ? fmtMoney(b.width, "") : "remainder"} @ ${Number(b.rate)}%`).join(" → ") },
              { key: "verified", label: "Verified", render: (r) => (r.verified ? "Yes" : "No") }]}
            fields={[{ name: "name", label: "Name", required: true }, { name: "effective_from", label: "Effective from", type: "date", required: true, width: 6 },
              { name: "effective_to", label: "Effective to", type: "date", width: 6 },
              { name: "bands", label: "Bands (JSON)", type: "json", required: true, helper: 'Monthly chargeable amount per band, ascending; width null = remainder. e.g. [{"width": 490, "rate": 0}, {"width": null, "rate": 35}]' },
              { name: "verified", label: "Verified against current GRA rates", type: "checkbox" }, { name: "source_note", label: "Source / reference", type: "textarea" }]}
            toInitial={(r) => ({ ...r, bands: (r.bands as Record<string, unknown>[]).map(({ width, rate }) => ({ width, rate })) })} />
          {table && <PayeCalculator tableId={table} />}
        </>}
        {tab === 2 && <ResourcePage embedded title="Rate set" url="/payroll/rate-sets/"
          columns={[{ key: "name", label: "Name" }, { key: "effective_from", label: "From", render: (r) => fmtDate(r.effective_from as string) },
            { key: "ssnit_employee_rate", label: "Employee %" }, { key: "ssnit_employer_rate", label: "Employer %" }, { key: "tier1_rate", label: "Tier 1 %" },
            { key: "tier2_rate", label: "Tier 2 %" }, { key: "ssnit_max_insurable_monthly", label: "Max insurable", render: (r) => fmtMoney(r.ssnit_max_insurable_monthly as string) },
            { key: "verified", label: "Verified", render: (r) => (r.verified ? "Yes" : "No") }]}
          fields={[{ name: "name", label: "Name", required: true }, { name: "effective_from", label: "From", type: "date", required: true, width: 6 }, { name: "effective_to", label: "To", type: "date", width: 6 },
            { name: "ssnit_employee_rate", label: "SSNIT employee %", type: "number", width: 3 }, { name: "ssnit_employer_rate", label: "SSNIT employer %", type: "number", width: 3 },
            { name: "tier1_rate", label: "Tier 1 %", type: "number", width: 3 }, { name: "tier2_rate", label: "Tier 2 %", type: "number", width: 3 },
            { name: "ssnit_max_insurable_monthly", label: "Max insurable earnings / month", type: "number", width: 6 },
            { name: "tier3_tax_exempt_max_percent", label: "Tier 3 tax-exempt max %", type: "number", width: 6 },
            { name: "bonus_tax_rate", label: "Bonus tax %", type: "number", width: 4 }, { name: "bonus_exempt_percent_annual_basic", label: "Bonus threshold (% annual basic)", type: "number", width: 4 },
            { name: "non_resident_rate", label: "Non-resident rate %", type: "number", width: 4 },
            { name: "overtime_qualifying_annual_income", label: "OT qualifying annual income", type: "number", width: 3 },
            { name: "overtime_threshold_percent_basic", label: "OT threshold (% basic)", type: "number", width: 3 },
            { name: "overtime_rate_low", label: "OT tax ≤ threshold %", type: "number", width: 3 }, { name: "overtime_rate_high", label: "OT tax > threshold %", type: "number", width: 3 },
            { name: "verified", label: "Verified by payroll professional", type: "checkbox" }, { name: "source_note", label: "Source / reference", type: "textarea" }]} />}
        {tab === 3 && <ResourcePage embedded title="Relief" url="/payroll/reliefs/"
          columns={[{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "annual_amount", label: "Annual amount", render: (r) => fmtMoney(r.annual_amount as string) },
            { key: "percent_of_income", label: "% of income" }, { key: "max_quantity", label: "Max qty" }, { key: "effective_from", label: "From", render: (r) => fmtDate(r.effective_from as string) }]}
          fields={[{ name: "code", label: "Code", required: true, width: 4 }, { name: "name", label: "Name", required: true, width: 8 },
            { name: "annual_amount", label: "Annual amount (GHS)", type: "number", width: 4 }, { name: "percent_of_income", label: "Or % of income", type: "number", width: 4 },
            { name: "max_quantity", label: "Max quantity", type: "number", width: 4 }, { name: "effective_from", label: "From", type: "date", required: true, width: 6 },
            { name: "effective_to", label: "To", type: "date", width: 6 }, { name: "verified", label: "Verified", type: "checkbox" }]} />}
        {tab === 4 && <ResourcePage embedded title="Pay group" url="/payroll/pay-groups/"
          columns={[{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "frequency", label: "Frequency" }, { key: "proration_method", label: "Proration" },
            { key: "ot_weekday_multiplier", label: "OT ×" }, { key: "payslip_password", label: "PDF password" }]}
          fields={[{ name: "code", label: "Code", required: true, width: 4 }, { name: "name", label: "Name", required: true, width: 8 },
            { name: "frequency", label: "Frequency", type: "select", width: 4, options: opts(["monthly", "biweekly", "weekly"]) },
            { name: "proration_method", label: "Proration", type: "select", width: 4, options: [{ value: "working", label: "Working days" }, { value: "calendar", label: "Calendar days" }, { value: "fixed30", label: "Fixed 30 days" }] },
            { name: "hours_per_month", label: "Hours per month (OT rate)", type: "number", width: 4 },
            { name: "ot_weekday_multiplier", label: "OT weekday ×", type: "number", width: 4 }, { name: "ot_weekend_multiplier", label: "OT rest-day ×", type: "number", width: 4 },
            { name: "ot_holiday_multiplier", label: "OT holiday ×", type: "number", width: 4 },
            { name: "min_net_pay_percent", label: "Warn if net < % of gross", type: "number", width: 4 }, { name: "variance_threshold_percent", label: "Variance flag %", type: "number", width: 4 },
            { name: "payslip_password", label: "Payslip PDF password", type: "select", width: 4, options: [{ value: "none", label: "None" }, { value: "staff_number", label: "Staff number" }, { value: "dob", label: "Date of birth" }] }]} />}
      </Card>
    </>
  );
}
