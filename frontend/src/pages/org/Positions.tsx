import { Card, Tab, Tabs } from "@mui/material";
import { useState } from "react";
import { useApi } from "../../api/hooks";
import { DataTable } from "../../components/DataTable";
import { StatusChip } from "../../components/Feedback";
import { PageHeader } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";
import { EMPLOYMENT_TYPES } from "../employees/fields";
import { fmtMoney } from "../../utils";

export default function Positions() {
  const [tab, setTab] = useState(0);
  const est = useApi<Record<string, unknown>[]>(tab === 1 ? "/org/positions/establishment/" : null);
  return (
    <>
      <PageHeader title="Positions & establishment" subtitle="Approved posts are separate from the people who hold them — vacancies, frozen posts and budgets are tracked per post." />
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}><Tab label="Positions" /><Tab label="Establishment summary" /></Tabs>
      {tab === 0 && (
        <Card><ResourcePage embedded title="Position" url="/org/positions/" createLabel="Add position"
          columns={[
            { key: "code", label: "Code" }, { key: "job_title_name", label: "Job title" }, { key: "department_name", label: "Department" },
            { key: "grade_code", label: "Grade" }, { key: "headcount", label: "Approved", align: "right" },
            { key: "occupied", label: "Filled", align: "right" }, { key: "vacancies", label: "Vacant", align: "right" },
            { key: "incumbents", label: "Incumbents", render: (r) => (r.incumbents as { name: string }[]).map((i) => i.name).join(", ") || "—", hideOnMobile: true },
            { key: "status", label: "Status", render: (r) => <StatusChip value={r.status as string} /> },
            { key: "is_critical", label: "Critical", render: (r) => (r.is_critical ? "Yes" : "") },
          ]}
          fields={[
            { name: "code", label: "Position code", required: true, width: 4 },
            { name: "job_title", label: "Job title", type: "ref", ref: "/org/job-titles/", required: true, width: 8 },
            { name: "department", label: "Department", type: "ref", ref: "/org/departments/", required: true, width: 6 },
            { name: "grade", label: "Grade", type: "ref", ref: "/org/grades/", refLabel: (g) => `${g.code} — ${g.name}`, width: 6 },
            { name: "branch", label: "Branch", type: "ref", ref: "/org/branches/", width: 6 },
            { name: "location", label: "Location", type: "ref", ref: "/org/locations/", width: 6 },
            { name: "reports_to", label: "Reports to (position)", type: "ref", ref: "/org/positions/", refLabel: (p) => `${p.code} — ${p.job_title_name}` },
            { name: "status", label: "Status", type: "select", width: 6, options: [{ value: "proposed", label: "Proposed" }, { value: "approved", label: "Approved" }, { value: "frozen", label: "Frozen" }, { value: "abolished", label: "Abolished" }] },
            { name: "employment_type", label: "Employment type", type: "select", options: EMPLOYMENT_TYPES, width: 6 },
            { name: "headcount", label: "Approved headcount", type: "number", width: 6 },
            { name: "budgeted_annual_cost", label: "Budgeted annual cost (GHS)", type: "number", width: 6 },
            { name: "is_critical", label: "Critical role (succession)", type: "checkbox" },
          ]} defaults={{ status: "approved", employment_type: "permanent", headcount: 1 }} /></Card>
      )}
      {tab === 1 && (
        <Card>
          <DataTable dense loading={est.isLoading} rows={(est.data || []).map((r, i) => ({ ...r, id: i }))} columns={[
            { key: "department", label: "Department" }, { key: "approved", label: "Approved posts", align: "right" },
            { key: "occupied", label: "Filled", align: "right" }, { key: "vacant", label: "Vacant", align: "right" },
            { key: "frozen", label: "Frozen", align: "right" },
            { key: "budget", label: "Budget (annual)", align: "right", render: (r) => fmtMoney(r.budget as number) },
          ]} />
        </Card>
      )}
    </>
  );
}
