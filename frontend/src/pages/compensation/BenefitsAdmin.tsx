import { Button, Card, Tab, Tabs } from "@mui/material";
import { useState } from "react";
import { post, useApi, useInvalidate } from "../../api/hooks";
import { DataTable } from "../../components/DataTable";
import { StatusChip, useToast } from "../../components/Feedback";
import { PageHeader } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtDate, fmtMoney, titleCase } from "../../utils";

const TYPES = ["health", "life", "pension", "vehicle", "housing", "wellness", "education", "other"].map((v) => ({ value: v, label: titleCase(v) }));

export default function BenefitsAdmin() {
  const [tab, setTab] = useState(0);
  const cost = useApi<Record<string, unknown>[]>(tab === 2 ? "/benefits/plans/cost/" : null);
  const toast = useToast();
  const inv = useInvalidate();
  return (
    <>
      <PageHeader title="Benefits administration" />
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}><Tab label="Plans" /><Tab label="Enrolments" /><Tab label="Cost & forecast" /></Tabs>
      <Card>
        {tab === 0 && <ResourcePage embedded title="Plan" url="/benefits/plans/" searchable={false}
          columns={[{ key: "name", label: "Plan" }, { key: "plan_type", label: "Type", render: (r) => titleCase(r.plan_type) }, { key: "provider", label: "Provider" },
            { key: "employer_monthly_cost", label: "Employer / month", align: "right", render: (r) => fmtMoney(r.employer_monthly_cost) },
            { key: "employee_monthly_cost", label: "Employee / month", align: "right", render: (r) => fmtMoney(r.employee_monthly_cost) },
            { key: "members", label: "Members", align: "right" }]}
          rowActions={(r) => <Button size="small" onClick={async () => { const x = await post<{ enrolled: number }>(`/benefits/plans/${r.id}/auto-enroll/`); toast.ok(`${x.enrolled} eligible employee(s) enrolled.`); inv("/benefits/"); }}>Enrol all eligible</Button>}
          fields={[{ name: "code", label: "Code", required: true, width: 4 }, { name: "name", label: "Name", required: true, width: 8 },
            { name: "plan_type", label: "Type", type: "select", options: TYPES, required: true, width: 6 }, { name: "provider", label: "Provider", width: 6 },
            { name: "description", label: "Description", type: "textarea" },
            { name: "employer_monthly_cost", label: "Employer cost / month", type: "number", width: 4 },
            { name: "employee_monthly_cost", label: "Employee cost / month", type: "number", width: 4 },
            { name: "cost_per_dependant", label: "Extra per dependant", type: "number", width: 4 },
            { name: "max_dependants", label: "Max dependants", type: "number", width: 4 },
            { name: "min_grade_level", label: "Min grade level", type: "number", width: 4 }, { name: "min_service_months", label: "Min service (months)", type: "number", width: 4 },
            { name: "categories", label: "Eligible categories (blank = all)", type: "multiref", ref: "/employees/categories/" },
            { name: "employment_types", label: "Eligible employment types (JSON list, blank = all)", type: "json" },
            { name: "deduction_element", label: "Payroll deduction element (employee share)", type: "ref", ref: "/payroll/elements/", refParams: { element_type: "deduction" }, refLabel: (e) => `${e.code} — ${e.name}` },
            { name: "requires_approval", label: "HR approval required", type: "checkbox", width: 4 }, { name: "auto_enroll", label: "Auto-enrol eligible staff", type: "checkbox", width: 4 },
            { name: "is_active", label: "Active", type: "checkbox", width: 4 }]}
          defaults={{ plan_type: "health", employment_types: "[]", categories: [], requires_approval: true, is_active: true }} />}
        {tab === 1 && <ResourcePage embedded title="Enrolment" url="/benefits/enrollments/" canCreate={false}
          columns={[{ key: "employee_name", label: "Employee" }, { key: "plan_name", label: "Plan" }, { key: "start_date", label: "From", render: (r) => fmtDate(r.start_date) },
            { key: "end_date", label: "To", render: (r) => fmtDate(r.end_date) }, { key: "dependants", label: "Dependants", render: (r) => (r.dependants || []).length },
            { key: "employee_cost", label: "Employee cost", align: "right", render: (r) => fmtMoney(r.employee_cost) },
            { key: "member_number", label: "Member no." }, { key: "status", label: "Status", render: (r) => <StatusChip value={r.status} /> }]}
          fields={[{ name: "member_number", label: "Insurer member number" }]}
          rowActions={(r) => r.status === "active" ? <Button size="small" color="error" onClick={async () => {
            const end = window.prompt("End date (YYYY-MM-DD):", new Date().toISOString().slice(0, 10)); if (!end) return;
            await post(`/benefits/enrollments/${r.id}/end/`, { end_date: end }); toast.ok("Enrolment ended."); inv("/benefits/");
          }}>End</Button> : null} />}
        {tab === 2 && <DataTable dense loading={cost.isLoading} rows={(cost.data || []).map((r, i) => ({ ...r, id: i }))} columns={[
          { key: "plan", label: "Plan" }, { key: "type", label: "Type" }, { key: "members", label: "Members", align: "right" }, { key: "dependants", label: "Dependants", align: "right" },
          { key: "employer_monthly", label: "Employer / month", align: "right", render: (r) => fmtMoney(r.employer_monthly) },
          { key: "employee_monthly", label: "Employees / month", align: "right", render: (r) => fmtMoney(r.employee_monthly) },
          { key: "employer_forecast", label: "Employer 12-month forecast", align: "right", render: (r) => fmtMoney(r.employer_forecast) },
          { key: "total_forecast", label: "Total 12-month forecast", align: "right", render: (r) => fmtMoney(r.total_forecast) }]} />}
      </Card>
    </>
  );
}
