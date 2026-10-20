import { Card, Tab, Tabs } from "@mui/material";
import { useState } from "react";
import { PageHeader } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";

const CATS = [["core", "Core / values"], ["leadership", "Leadership"], ["technical", "Technical / functional"], ["clinical", "Clinical"]]
  .map(([value, label]) => ({ value, label }));

export default function PerformanceSetup() {
  const [tab, setTab] = useState(0);
  return (
    <>
      <PageHeader title="Performance setup" subtitle="Appraisal forms by role, the competency library and rating scales." />
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}><Tab label="Appraisal forms" /><Tab label="Competencies" /><Tab label="Rating scales" /></Tabs>
      <Card>
        {tab === 0 && <ResourcePage embedded title="Form" url="/performance/templates/" writePerm="performance.manage" canDelete searchable={false} createLabel="New form"
          columns={[{ key: "name", label: "Form", render: (r) => <><b>{r.name}</b><br /><small>{[r.job_family_name, r.category_name, r.clinical_only && "clinical staff"].filter(Boolean).join(" · ") || "Everyone else"}</small></> },
            { key: "weights", label: "Objectives / competencies", render: (r) => `${r.objectives_weight}% / ${r.competencies_weight}%` },
            { key: "competencies", label: "Competencies", align: "right", render: (r) => r.competencies.length },
            { key: "include_360", label: "360", render: (r) => (r.include_360 ? "Yes" : "No") },
            { key: "is_active", label: "Active", render: (r) => (r.is_active ? "Yes" : "No") }]}
          fields={[{ name: "name", label: "Name", required: true }, { name: "rating_scale", label: "Rating scale", type: "ref", ref: "/performance/scales/", required: true, width: 6 },
            { name: "objectives_weight", label: "Objectives weight (%) — competencies get the rest", type: "number", width: 6 },
            { name: "job_family", label: "Only for job family", type: "ref", ref: "/org/job-families/", width: 4 },
            { name: "category", label: "Only for staff category", type: "ref", ref: "/employees/categories/", width: 4 },
            { name: "clinical_only", label: "Clinical roles only", type: "checkbox", width: 4 },
            { name: "competencies", label: "Competencies", type: "multiref", ref: "/performance/competencies/" },
            { name: "min_objectives", label: "Min objectives", type: "number", width: 4 }, { name: "max_objectives", label: "Max objectives", type: "number", width: 4 },
            { name: "include_360", label: "Include 360 feedback", type: "checkbox", width: 4 }, { name: "is_active", label: "Active", type: "checkbox" }]}
          defaults={{ objectives_weight: 70, min_objectives: 3, max_objectives: 8, is_active: true, competencies: [] }} />}
        {tab === 1 && <ResourcePage embedded title="Competency" url="/performance/competencies/" writePerm="performance.manage" searchable={false} createLabel="Add competency"
          columns={[{ key: "name", label: "Competency", render: (r) => <><b>{r.name}</b><br /><small>{r.description}</small></> },
            { key: "category", label: "Category", render: (r) => CATS.find((c) => c.value === r.category)?.label }, { key: "is_active", label: "Active", render: (r) => (r.is_active ? "Yes" : "No") }]}
          fields={[{ name: "name", label: "Name", required: true, width: 8 }, { name: "category", label: "Category", type: "select", options: CATS, width: 4 },
            { name: "description", label: "Description", type: "textarea" }, { name: "behaviours", label: "Observable behaviours", type: "textarea" },
            { name: "is_active", label: "Active", type: "checkbox" }]} defaults={{ category: "core", is_active: true }} />}
        {tab === 2 && <ResourcePage embedded title="Scale" url="/performance/scales/" writePerm="performance.manage" searchable={false} createLabel="Add scale"
          columns={[{ key: "name", label: "Scale" }, { key: "levels", label: "Levels", render: (r) => r.levels.map((l: { value: number; label: string }) => `${l.value} ${l.label}`).join(" · ") },
            { key: "is_default", label: "Default", render: (r) => (r.is_default ? "Yes" : "") }]}
          fields={[{ name: "name", label: "Name", required: true }, { name: "levels", label: "Levels (JSON)", type: "json", required: true, helper: '[{"value": 4, "label": "Exceeds", "description": "…"}, …] — whole numbers, highest = best' },
            { name: "is_default", label: "Default scale", type: "checkbox" }]} />}
      </Card>
    </>
  );
}
