import { Card, Tab, Tabs } from "@mui/material";
import { useState } from "react";
import { PageHeader } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";

export default function JobTitles() {
  const [tab, setTab] = useState(0);
  return (
    <>
      <PageHeader title="Job titles & families" />
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}><Tab label="Job titles" /><Tab label="Job families" /><Tab label="Employee categories" /></Tabs>
      <Card>
        {tab === 0 && <ResourcePage embedded title="Job title" url="/org/job-titles/" createLabel="Add job title"
          columns={[{ key: "name", label: "Title" }, { key: "code", label: "Code" }, { key: "family_name", label: "Family" },
            { key: "is_clinical", label: "Clinical", render: (r) => (r.is_clinical ? `Yes (${r.required_license_type || "licence"})` : "") }]}
          fields={[{ name: "name", label: "Title", required: true, width: 8 }, { name: "code", label: "Code", width: 4 },
            { name: "family", label: "Job family", type: "ref", ref: "/org/job-families/", width: 6 },
            { name: "default_grade", label: "Default grade", type: "ref", ref: "/org/grades/", refLabel: (g) => `${g.code} — ${g.name}`, width: 6 },
            { name: "description", label: "Job description", type: "textarea" }, { name: "requirements", label: "Requirements", type: "textarea" },
            { name: "is_clinical", label: "Regulated clinical role (requires licence)", type: "checkbox" },
            { name: "required_license_type", label: "Required licence type", hidden: (v) => !v.is_clinical }]} />}
        {tab === 1 && <ResourcePage embedded title="Job family" url="/org/job-families/" canDelete
          columns={[{ key: "name", label: "Name" }, { key: "description", label: "Description" }]}
          fields={[{ name: "name", label: "Name", required: true }, { name: "description", label: "Description", type: "textarea" }]} />}
        {tab === 2 && <ResourcePage embedded title="Category" url="/employees/categories/"
          columns={[{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "description", label: "Description" }]}
          fields={[{ name: "code", label: "Code", required: true, width: 4 }, { name: "name", label: "Name", required: true, width: 8 },
            { name: "description", label: "Description", type: "textarea" }]} />}
      </Card>
    </>
  );
}
