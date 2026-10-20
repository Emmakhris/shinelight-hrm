import { Button, Card, Grid2 as Grid } from "@mui/material";
import { useState } from "react";
import { post, useInvalidate, useList } from "../../api/hooks";
import { StatusChip, useToast } from "../../components/Feedback";
import { PageHeader, Section } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtMoney } from "../../utils";

export default function Bonuses() {
  const [scheme, setScheme] = useState<Record<string, any> | null>(null); // eslint-disable-line @typescript-eslint/no-explicit-any
  const periods = useList<{ id: number; name: string }>("/payroll/periods/");
  const toast = useToast();
  const inv = useInvalidate();
  const editable = scheme && ["draft", "open", "returned"].includes(scheme.status);
  return (
    <>
      <PageHeader title="Bonuses & incentives" subtitle="Approved awards are added to the chosen payroll period with Ghana bonus-tax treatment." />
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 5 }}>
          <Card><ResourcePage embedded title="Bonus scheme" url="/compensation/bonus-schemes/" searchable={false} onRowClick={setScheme} writePerm="compensation.manage"
            createLabel="New scheme"
            columns={[{ key: "name", label: "Scheme" }, { key: "period_name", label: "Paid in" }, { key: "award_count", label: "Awards" },
              { key: "total", label: "Total", align: "right", render: (r) => fmtMoney(r.total) }, { key: "status", label: "Status", render: (r) => <StatusChip value={r.status} /> }]}
            fields={[{ name: "name", label: "Name (e.g. 2026 performance bonus)", required: true },
              { name: "basis", label: "Basis", type: "select", width: 6, options: [{ value: "fixed", label: "Fixed amount" }, { value: "percent_basic", label: "% of monthly basic" }, { value: "months_basic", label: "Months of basic" }] },
              { name: "default_value", label: "Default value", type: "number", width: 6 },
              { name: "pay_period", label: "Pay in payroll period", type: "select", options: periods.items.map((p) => ({ value: p.id, label: p.name })) },
              { name: "description", label: "Description / criteria", type: "textarea" }]} defaults={{ basis: "fixed", default_value: 0 }} /></Card>
        </Grid>
        <Grid size={{ xs: 12, md: 7 }}>
          {scheme ? (
            <Section title={`Awards — ${scheme.name}`} actions={editable ? <>
              <Button size="small" onClick={async () => { const r = await post<{ added: number }>(`/compensation/bonus-schemes/${scheme.id}/populate/`); toast.ok(`${r.added} award(s) added.`); inv("/compensation/"); }}>Add all staff</Button>
              <Button size="small" variant="contained" onClick={async () => { await post(`/compensation/bonus-schemes/${scheme.id}/submit/`); toast.ok("Submitted for approval."); inv("/compensation/"); setScheme(null); }}>Submit</Button>
            </> : <StatusChip value={scheme.status} />}>
              <ResourcePage embedded title="Award" url="/compensation/bonus-awards/" params={{ scheme: scheme.id }} searchable={false} canDelete={!!editable}
                canEdit={!!editable} canCreate={!!editable} writePerm="compensation.manage"
                columns={[{ key: "employee_name", label: "Employee" }, { key: "amount", label: "Amount", align: "right", render: (r) => fmtMoney(r.amount) },
                  { key: "justification", label: "Justification" }, { key: "payroll_adjustment", label: "In payroll", render: (r) => (r.payroll_adjustment ? "Yes" : "") }]}
                fields={[{ name: "employee", label: "Employee", type: "ref", ref: "/employees/", refLabel: (e) => `${e.full_name} (${e.staff_number})`, required: true },
                  { name: "amount", label: "Amount (GHS)", type: "number", required: true, width: 6 }, { name: "justification", label: "Justification", width: 6 },
                  { name: "scheme", label: "", hidden: () => true }]} defaults={{ scheme: scheme.id }} />
            </Section>
          ) : <Section title="Awards">Select a scheme.</Section>}
        </Grid>
      </Grid>
    </>
  );
}
