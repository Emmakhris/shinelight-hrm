import { MenuItem, TextField } from "@mui/material";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { StatusChip } from "../../components/Feedback";
import type { FieldDef } from "../../components/FormDialog";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtDate } from "../../utils";
import { EMPLOYMENT_TYPES, QUALIFICATIONS, VISIBILITY } from "./constants";

export const VACANCY_FIELDS: FieldDef[] = [
  { name: "title", label: "Job title (as advertised)", required: true, width: 8 },
  { name: "openings", label: "Openings", type: "number", width: 4 },
  { name: "department", label: "Department", type: "ref", ref: "/org/departments/", required: true, width: 6 },
  { name: "location", label: "Location", type: "ref", ref: "/org/locations/", width: 6 },
  { name: "employment_type", label: "Employment type", type: "select", options: EMPLOYMENT_TYPES, width: 6 },
  { name: "visibility", label: "Open to", type: "select", options: VISIBILITY, width: 6 },
  { name: "summary", label: "Summary", type: "textarea" },
  { name: "responsibilities", label: "Key responsibilities", type: "textarea" },
  { name: "requirements", label: "Requirements", type: "textarea" },
  { name: "min_qualification", label: "Minimum qualification", type: "select", options: QUALIFICATIONS, width: 6 },
  { name: "min_experience_years", label: "Minimum years' experience", type: "number", width: 6 },
  { name: "salary_display", label: "Salary shown to applicants", placeholder: "e.g. Competitive / GHS 4,000–5,000", width: 6 },
  { name: "closing_date", label: "Closing date", type: "date", width: 6 },
  { name: "advertising_cost", label: "Advertising / agency cost (GHS)", type: "number", width: 6 },
  { name: "channels", label: "Advertised on (JSON list)", type: "json", width: 6, helper: '["career_site", "Daily Graphic", "LinkedIn"]' },
  { name: "screening_questions", label: "Screening questions (JSON)", type: "json",
    helper: 'e.g. [{"key":"licence","question":"Do you hold a valid licence?","type":"yes_no","knockout":"no"}]. Knock-out answers are flagged for review, never auto-rejected.' },
  { name: "scorecard_criteria", label: "Interview scorecard criteria (JSON, optional)", type: "json",
    helper: '[{"name":"Technical knowledge","weight":40}, …] — leave empty for the standard criteria.' },
];

export default function Vacancies() {
  const nav = useNavigate();
  const [status, setStatus] = useState("");
  return (
    <ResourcePage title="Vacancies & job postings" url="/recruitment/vacancies/" params={{ status }} writePerm="recruitment.manage"
      subtitle="Create postings from approved requisitions, publish them to the career site and internal job board, and manage each pipeline."
      createLabel="New vacancy" onRowClick={(r) => nav(`/recruitment/vacancies/${r.id}`)}
      filters={<TextField select size="small" label="Status" value={status} onChange={(e) => setStatus(e.target.value)} sx={{ minWidth: 160 }}>
        <MenuItem value="">All</MenuItem>
        {["draft", "published", "closed", "filled", "cancelled"].map((s) => <MenuItem key={s} value={s}>{s}</MenuItem>)}
      </TextField>}
      columns={[
        { key: "reference", label: "Ref", render: (r) => r.reference || "Draft" },
        { key: "title", label: "Vacancy", render: (r) => <><b>{r.title}</b><br /><small>{r.department_name}{r.requisition_reference ? ` · ${r.requisition_reference}` : ""}</small></> },
        { key: "visibility", label: "Open to", hideOnMobile: true, render: (r) => VISIBILITY.find((v) => v.value === r.visibility)?.label },
        { key: "pipeline", label: "Applications", align: "right", render: (r) => Object.values(r.pipeline || {}).reduce((a: number, b) => a + Number(b), 0) },
        { key: "closing_date", label: "Closes", render: (r) => fmtDate(r.closing_date) },
        { key: "days_open", label: "Days open", align: "right", hideOnMobile: true, render: (r) => r.days_open ?? "—" },
        { key: "status", label: "Status", render: (r) => <StatusChip value={r.status} /> },
      ]}
      fields={VACANCY_FIELDS}
      defaults={{ openings: 1, employment_type: "permanent", visibility: "both", min_qualification: "none", min_experience_years: 0, screening_questions: [], channels: [], scorecard_criteria: [] }}
    />
  );
}
