import { Alert, Card, Chip, Tab, Tabs } from "@mui/material";
import { useState } from "react";
import { useApi } from "../../api/hooks";
import { DataTable } from "../../components/DataTable";
import { PageHeader } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtDate } from "../../utils";

type Row = { employee: number; name: string; job_title: string; department: string; credential_issues: string[]; competencies: Record<string, string> };

export default function Matrix() {
  const [tab, setTab] = useState(0);
  const { data, isLoading } = useApi<Row[]>(tab === 0 ? "/hospital/credentials/" : null);
  const reqs = Array.from(new Set((data || []).flatMap((r) => Object.keys(r.competencies))));
  return (
    <>
      <PageHeader title="Training & competency matrix" subtitle="Whether required credentials and mandatory clinical training are current for each clinical role" />
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}><Tab label="Matrix" /><Tab label="Requirements" /><Tab label="Completion records" /></Tabs>
      {tab === 0 && <>
        {(data || []).some((r) => r.credential_issues.length) && <Alert severity="error" sx={{ mb: 2 }}>Some clinical staff have credential problems and cannot be rostered.</Alert>}
        <Card><DataTable dense loading={isLoading} rows={(data || []).map((r) => ({ ...r, id: r.employee }))} columns={[
          { key: "name", label: "Employee" }, { key: "job_title", label: "Role" }, { key: "department", label: "Unit" },
          { key: "credential_issues", label: "Licence", render: (r) => (r.credential_issues as string[]).length ? <Chip color="error" variant="outlined" label="Problem" title={(r.credential_issues as string[]).join(" ")} /> : <Chip color="success" variant="outlined" label="OK" /> },
          ...reqs.map((q) => ({ key: q, label: q, render: (r: Record<string, unknown>) => {
            const v = (r.competencies as Record<string, string>)[q];
            return v ? <Chip variant="outlined" label={v} color={v === "current" ? "success" : v === "expiring" ? "warning" : "error"} /> : "n/a";
          } })),
        ]} /></Card>
      </>}
      {tab === 1 && <Card><ResourcePage embedded title="Requirement" url="/hospital/competency-requirements/" writePerm="hospital.manage" canDelete
        columns={[{ key: "name", label: "Requirement" }, { key: "refresh_months", label: "Refresh (months)" }, { key: "blocks_rostering", label: "Blocks roster", render: (r) => (r.blocks_rostering ? "Yes" : "") }]}
        fields={[{ name: "name", label: "Name (e.g. Basic Life Support)", required: true },
          { name: "job_titles", label: "Required for job titles", type: "multiref", ref: "/org/job-titles/", refParams: { is_clinical: "true" } },
          { name: "refresh_months", label: "Refresh every (months)", type: "number", width: 6 },
          { name: "blocks_rostering", label: "Block rostering when expired", type: "checkbox", width: 6 }]} defaults={{ refresh_months: 24, job_titles: [] }} /></Card>}
      {tab === 2 && <Card><ResourcePage embedded title="Record" url="/hospital/competency-records/" writePerm="hospital.manage" canDelete
        columns={[{ key: "employee_name", label: "Employee" }, { key: "requirement_name", label: "Requirement" },
          { key: "completed_on", label: "Completed", render: (r) => fmtDate(r.completed_on as string) }, { key: "expires_on", label: "Expires", render: (r) => fmtDate(r.expires_on as string) },
          { key: "assessor", label: "Assessor" }]}
        fields={[{ name: "employee", label: "Employee", type: "ref", ref: "/employees/", refLabel: (e) => `${e.full_name} (${e.staff_number})`, required: true },
          { name: "requirement", label: "Requirement", type: "ref", ref: "/hospital/competency-requirements/", required: true },
          { name: "completed_on", label: "Completed on", type: "date", required: true, width: 6 }, { name: "expires_on", label: "Expires on", type: "date", width: 6 },
          { name: "assessor", label: "Assessor", width: 6 }, { name: "score", label: "Score / result", width: 6 }]} /></Card>}
    </>
  );
}
