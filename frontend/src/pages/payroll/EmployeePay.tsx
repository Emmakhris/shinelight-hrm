import { Button, Card, Grid2 as Grid, Tab, Tabs, Typography } from "@mui/material";
import { useState } from "react";
import { post, useInvalidate, useList } from "../../api/hooks";
import { useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { Field, PageHeader, Section } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtDate, fmtMoney } from "../../utils";

interface Sim { gross: string; taxable_income: string; paye: string; ssnit_employee: string; net: string; employer_cost: string; messages: string[];
  lines: { code: string; name: string; type: string; amount: string }[] }

export default function EmployeePay() {
  const [tab, setTab] = useState(0);
  const [simOpen, setSimOpen] = useState(false);
  const [sim, setSim] = useState<Sim | null>(null);
  const periods = useList<{ id: number; name: string }>(simOpen ? "/payroll/periods/" : null);
  const toast = useToast();
  const inv = useInvalidate();
  const groups = useList<{ id: number; name: string }>("/payroll/pay-groups/");
  const empLabel = (e: Record<string, unknown>) => `${e.full_name} (${e.staff_number})`;
  return (
    <>
      <PageHeader title="Employee pay" subtitle="Pay profiles, recurring elements and tax relief claims"
        actions={<>
          <Button onClick={() => setSimOpen(true)}>Payslip simulator</Button>
          {groups.items[0] && <Button onClick={async () => { const r = await post<{ created: number }>("/payroll/profiles/bulk-assign/", { pay_group: groups.items[0].id }); toast.ok(`${r.created} pay profiles created.`); inv("/payroll/"); }}>
            Create missing pay profiles</Button>}
        </>} />
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}><Tab label="Pay profiles" /><Tab label="Recurring elements" /><Tab label="Tax relief claims" /></Tabs>
      <Card>
        {tab === 0 && <ResourcePage embedded title="Pay profile" url="/payroll/profiles/"
          columns={[{ key: "employee_name", label: "Employee" }, { key: "pay_group_name", label: "Pay group" },
            { key: "is_tax_resident", label: "Resident", render: (r) => (r.is_tax_resident ? "Yes" : "No") },
            { key: "ssnit_applicable", label: "SSNIT", render: (r) => (r.ssnit_applicable ? "Yes" : "No") },
            { key: "tier3_employee_percent", label: "Tier 3 %", align: "right" },
            { key: "payment_hold", label: "Hold", render: (r) => (r.payment_hold ? `Yes — ${r.hold_reason}` : "") }]}
          fields={[{ name: "employee", label: "Employee", type: "ref", ref: "/employees/", refLabel: empLabel, required: true },
            { name: "pay_group", label: "Pay group", type: "ref", ref: "/payroll/pay-groups/", required: true },
            { name: "is_tax_resident", label: "Tax resident", type: "checkbox", width: 4 }, { name: "paye_exempt", label: "PAYE exempt", type: "checkbox", width: 4 },
            { name: "ssnit_applicable", label: "SSNIT applies", type: "checkbox", width: 4 },
            { name: "tier3_employee_percent", label: "Tier 3 employee %", type: "number", width: 6 }, { name: "tier3_employer_percent", label: "Tier 3 employer %", type: "number", width: 6 },
            { name: "payment_hold", label: "Hold salary payment", type: "checkbox", width: 6 }, { name: "hold_reason", label: "Hold reason", width: 6 }]}
          defaults={{ is_tax_resident: true, ssnit_applicable: true }} />}
        {tab === 1 && <ResourcePage embedded title="Element" url="/payroll/employee-elements/" canDelete
          columns={[{ key: "employee_name", label: "Employee" }, { key: "element_name", label: "Element" },
            { key: "amount", label: "Amount", align: "right", render: (r) => r.amount === null ? (r.percent ? `${r.percent}%` : "default") : fmtMoney(r.amount as string) },
            { key: "start_date", label: "From", render: (r) => fmtDate(r.start_date as string) }, { key: "end_date", label: "To", render: (r) => fmtDate(r.end_date as string) }]}
          fields={[{ name: "employee", label: "Employee", type: "ref", ref: "/employees/", refLabel: empLabel, required: true },
            { name: "element", label: "Element", type: "ref", ref: "/payroll/elements/", refLabel: (e) => `${e.code} — ${e.name}`, required: true },
            { name: "amount", label: "Amount", type: "number", width: 4 }, { name: "percent", label: "Percent", type: "number", width: 4 }, { name: "quantity", label: "Quantity", type: "number", width: 4 },
            { name: "start_date", label: "Start", type: "date", required: true, width: 6 }, { name: "end_date", label: "End", type: "date", width: 6 }, { name: "note", label: "Note" }]} />}
        {tab === 2 && <ResourcePage embedded title="Relief claim" url="/payroll/relief-claims/" canDelete
          columns={[{ key: "employee", label: "Employee ID" }, { key: "relief_name", label: "Relief" }, { key: "quantity", label: "Qty" },
            { key: "start_date", label: "From", render: (r) => fmtDate(r.start_date as string) }, { key: "approved", label: "Approved", render: (r) => (r.approved ? "Yes" : "No") }]}
          fields={[{ name: "employee", label: "Employee", type: "ref", ref: "/employees/", refLabel: empLabel, required: true },
            { name: "relief", label: "Relief", type: "ref", ref: "/payroll/reliefs/", required: true }, { name: "quantity", label: "Quantity (children/dependants)", type: "number", width: 4 },
            { name: "start_date", label: "From", type: "date", required: true, width: 4 }, { name: "end_date", label: "To", type: "date", width: 4 },
            { name: "approved", label: "Evidence verified / approved", type: "checkbox" }]} defaults={{ quantity: 1 }} />}
      </Card>
      <FormDialog open={simOpen} onClose={() => setSimOpen(false)} title="Payslip simulator (nothing is saved)" submitLabel="Simulate"
        fields={[{ name: "employee", label: "Employee", type: "ref", ref: "/employees/", refLabel: empLabel, required: true },
          { name: "period", label: "Period", type: "select", required: true, options: periods.items.map((p) => ({ value: p.id, label: p.name })) },
          { name: "basic_salary", label: "What-if basic salary (optional)", type: "number" }]}
        onSubmit={async (d) => { setSim(await post<Sim>("/payroll/simulate/", d)); }} />
      {sim && (
        <Section title="Simulation result" actions={<Button size="small" onClick={() => setSim(null)}>Clear</Button>}>
          <Grid container spacing={2}>
            {[["Gross", sim.gross], ["Chargeable income", sim.taxable_income], ["PAYE", sim.paye], ["SSNIT (5.5%)", sim.ssnit_employee], ["Net", sim.net], ["Employer cost", sim.employer_cost]]
              .map(([l, v]) => <Grid key={l} size={{ xs: 6, md: 2 }}><Field label={l} value={fmtMoney(v)} /></Grid>)}
          </Grid>
          <Typography variant="body2" sx={{ mt: 2 }}>{sim.lines.map((l) => `${l.name}: ${fmtMoney(l.amount, "")}`).join(" · ")}</Typography>
          {sim.messages.length > 0 && <Typography variant="caption" color="text.secondary">{sim.messages.join(" • ")}</Typography>}
        </Section>
      )}
    </>
  );
}
