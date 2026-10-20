import { Button, Card, MenuItem, TextField } from "@mui/material";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { post, useInvalidate } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { ResourcePage } from "../../components/ResourcePage";
import { StatusChip, useToast } from "../../components/Feedback";
import { fmtDate, fmtMoney } from "../../utils";
import { EMPLOYMENT_TYPES, REASONS } from "./constants";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export default function Requisitions() {
  const { can } = useAuth();
  const toast = useToast();
  const inv = useInvalidate();
  const nav = useNavigate();
  const [status, setStatus] = useState("");
  const act = async (fn: () => Promise<unknown>, msg: string) => {
    try { await fn(); toast.ok(msg); inv("/recruitment/"); } catch (e) { toast.error(e); }
  };
  return (
    <ResourcePage title="Manpower requisitions" url="/recruitment/requisitions/" params={{ status }}
      subtitle="Request new or replacement staff. Requests route to the head of department, HR and finance for approval."
      createLabel="New requisition" writePerm="recruitment.requisition"
      filters={<TextField select size="small" label="Status" value={status} onChange={(e) => setStatus(e.target.value)} sx={{ minWidth: 160 }}>
        <MenuItem value="">All</MenuItem>
        {["draft", "pending", "approved", "returned", "rejected", "filled", "closed"].map((s) => <MenuItem key={s} value={s}>{s}</MenuItem>)}
      </TextField>}
      columns={[
        { key: "reference", label: "Ref", render: (r) => r.reference || "Draft" },
        { key: "job_title_name", label: "Role", render: (r) => <><b>{r.headcount} × {r.job_title_name}</b><br /><small>{r.department_name}</small></> },
        { key: "reason", label: "Reason", hideOnMobile: true, render: (r) => REASONS.find((x) => x.value === r.reason)?.label },
        { key: "salary_max", label: "Budget / month", align: "right", hideOnMobile: true, render: (r) => fmtMoney(r.salary_max) },
        { key: "requested_by_name", label: "Requested by", hideOnMobile: true },
        { key: "target_start_date", label: "Needed by", render: (r) => fmtDate(r.target_start_date) },
        { key: "status", label: "Status", render: (r) => <StatusChip value={r.status} /> },
      ]}
      rowActions={(r: R) => <>
        {["draft", "returned"].includes(r.status) && <Button size="small" variant="contained"
          onClick={() => act(() => post(`/recruitment/requisitions/${r.id}/submit/`), "Submitted for approval.")}>Submit</Button>}
        {r.status === "approved" && !r.vacancy && can("recruitment.manage") && <Button size="small" variant="contained"
          onClick={() => act(async () => { const v = await post<R>(`/recruitment/requisitions/${r.id}/create-vacancy/`); nav(`/recruitment/vacancies/${v.id}`); }, "Vacancy created.")}>Advertise</Button>}
        {r.vacancy && <Button size="small" onClick={() => nav(`/recruitment/vacancies/${r.vacancy.id}`)}>Vacancy {r.vacancy.reference}</Button>}
      </>}
      fields={[
        { name: "job_title", label: "Job title", type: "ref", ref: "/org/job-titles/", required: true, width: 6 },
        { name: "department", label: "Department", type: "ref", ref: "/org/departments/", required: true, width: 6 },
        { name: "position", label: "Establishment position (optional)", type: "ref", ref: "/org/positions/", refLabel: (o) => `${o.code} ${o.job_title_name || ""}`, width: 6 },
        { name: "grade", label: "Grade", type: "ref", ref: "/org/grades/", refLabel: (o) => `${o.code} ${o.name}`, width: 6 },
        { name: "location", label: "Location", type: "ref", ref: "/org/locations/", width: 6 },
        { name: "employment_type", label: "Employment type", type: "select", options: EMPLOYMENT_TYPES, width: 6 },
        { name: "headcount", label: "Number of staff", type: "number", required: true, width: 4 },
        { name: "reason", label: "Reason", type: "select", options: REASONS, required: true, width: 4 },
        { name: "target_start_date", label: "Needed by", type: "date", width: 4 },
        { name: "replacing", label: "Employee being replaced", type: "ref", ref: "/employees/", hidden: (v) => v.reason !== "replacement" },
        { name: "salary_min", label: "Salary range from (GHS/month)", type: "number", width: 6 },
        { name: "salary_max", label: "Budget ceiling (GHS/month)", type: "number", required: true, width: 6 },
        { name: "justification", label: "Business need / justification", type: "textarea", required: true },
        { name: "submit", label: "Submit for approval now", type: "checkbox" },
      ]}
      defaults={{ headcount: 1, reason: "replacement", employment_type: "permanent", submit: true }}
      intro={<Card variant="outlined" sx={{ p: 1.5, mb: 1, fontSize: 13 }}>Approved positions in the establishment are checked for vacancies. Finance confirms the budget.</Card>}
    />
  );
}
