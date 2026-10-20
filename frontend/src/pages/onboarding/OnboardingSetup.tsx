import { Button, Card, Grid2 as Grid } from "@mui/material";
import { useState } from "react";
import { post, useInvalidate } from "../../api/hooks";
import { useToast } from "../../components/Feedback";
import { PageHeader } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";
import { EMPLOYMENT_TYPES, OWNER_TYPES, TASK_CATEGORIES } from "../recruitment/constants";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
const label = (list: { value: string; label: string }[], v: string) => list.find((x) => x.value === v)?.label || v;

export default function OnboardingSetup() {
  const [tpl, setTpl] = useState<R | null>(null);
  const toast = useToast();
  const inv = useInvalidate();
  return (
    <>
      <PageHeader title="Onboarding checklists" subtitle="The most specific active checklist (department and employment type) is used when a new employee is registered." />
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 5 }}>
          <Card>
            <ResourcePage embedded title="Checklist" url="/onboarding/templates/" writePerm="onboarding.manage" searchable={false} canDelete
              createLabel="New checklist" onRowClick={setTpl}
              columns={[{ key: "name", label: "Checklist", render: (r) => <><b>{r.name}</b><br /><small>{r.department_name}{r.employment_type ? ` · ${label(EMPLOYMENT_TYPES, r.employment_type)}` : ""}</small></> },
                { key: "task_count", label: "Tasks", align: "right" }, { key: "is_active", label: "Active", render: (r) => (r.is_active ? "Yes" : "No") }]}
              rowActions={(r) => <Button size="small" onClick={async () => { await post(`/onboarding/templates/${r.id}/duplicate/`); toast.ok("Copied."); inv("/onboarding/"); }}>Copy</Button>}
              fields={[{ name: "name", label: "Name", required: true }, { name: "department", label: "Department (blank = all)", type: "ref", ref: "/org/departments/", width: 6 },
                { name: "employment_type", label: "Employment type (blank = all)", type: "select", options: EMPLOYMENT_TYPES, width: 6 },
                { name: "description", label: "Description", type: "textarea" }, { name: "is_active", label: "Active", type: "checkbox" }]}
              defaults={{ is_active: true }} />
          </Card>
        </Grid>
        <Grid size={{ xs: 12, md: 7 }}>
          {tpl ? <Card>
            <ResourcePage embedded title={`Tasks — ${tpl.name}`} url="/onboarding/template-tasks/" params={{ template: tpl.id }} writePerm="onboarding.manage"
              searchable={false} canDelete createLabel="Add task" defaults={{ template: tpl.id, owner_type: "hr", category: "other", due_offset_days: 0, is_mandatory: true, form: [] }}
              columns={[{ key: "due_offset_days", label: "Due", render: (r) => (r.due_offset_days === 0 ? "Day 1" : r.due_offset_days < 0 ? `${-r.due_offset_days}d before` : `+${r.due_offset_days}d`) },
                { key: "title", label: "Task", render: (r) => <>{r.title}<br /><small>{label(TASK_CATEGORIES, r.category)}</small></> },
                { key: "owner_type", label: "Owner", render: (r) => r.role_name || label(OWNER_TYPES, r.owner_type) },
                { key: "req", label: "Requires", hideOnMobile: true, render: (r) => [r.document_category_name && `Document: ${r.document_category_name}`, r.policy_document_name && `Ack: ${r.policy_document_name}`, r.form?.length && "Form"].filter(Boolean).join(", ") }]}
              fields={[{ name: "template", label: "Checklist", type: "ref", ref: "/onboarding/templates/", disabled: true },
                { name: "title", label: "Task", required: true, width: 8 }, { name: "order", label: "Order", type: "number", width: 4 },
                { name: "description", label: "Instructions", type: "textarea" },
                { name: "category", label: "Category", type: "select", options: TASK_CATEGORIES, width: 6 },
                { name: "owner_type", label: "Owner", type: "select", options: OWNER_TYPES, width: 6 },
                { name: "role", label: "Role (when owner is a specific role)", type: "ref", ref: "/admin/roles/", width: 6, hidden: (v) => v.owner_type !== "role" },
                { name: "due_offset_days", label: "Due (days from start; negative = before)", type: "number", width: 6 },
                { name: "document_category", label: "Requires document on file", type: "ref", ref: "/documents/categories/", width: 6 },
                { name: "policy_document", label: "Policy to acknowledge", type: "ref", ref: "/documents/", refParams: { is_policy: "true" }, refLabel: (d) => String(d.title), width: 6 },
                { name: "form", label: "Form fields (JSON)", type: "json", helper: '[{"key":"rating","label":"How was your first week?","type":"rating"}]' },
                { name: "is_mandatory", label: "Mandatory", type: "checkbox" }]}
              toInitial={(r) => r} />
          </Card> : <Card sx={{ p: 3, color: "text.secondary" }}>Select a checklist to see and edit its tasks.</Card>}
        </Grid>
      </Grid>
    </>
  );
}
