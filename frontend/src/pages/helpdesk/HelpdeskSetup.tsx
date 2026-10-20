import { Card, Tab, Tabs } from "@mui/material";
import { useState } from "react";
import { PageHeader } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";

const PRIORITIES = ["low", "normal", "high", "urgent"].map((v) => ({ value: v, label: v }));

export default function HelpdeskSetup() {
  const [tab, setTab] = useState(0);
  return (
    <>
      <PageHeader title="Service catalogue & knowledge base" subtitle="Each service has its own routing, SLA and request form." />
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}><Tab label="Services" /><Tab label="Categories" /><Tab label="Knowledge articles" /></Tabs>
      <Card>
        {tab === 0 && <ResourcePage embedded title="Service" url="/helpdesk/services/" createLabel="Add service"
          columns={[{ key: "name", label: "Service" }, { key: "category_name", label: "Category" }, { key: "team_role_name", label: "Routed to" },
            { key: "response_sla_hours", label: "Response SLA (h)" }, { key: "resolution_sla_hours", label: "Resolution SLA (h)" },
            { key: "is_confidential", label: "Confidential", render: (r) => (r.is_confidential ? "Yes" : "") },
            { key: "is_active", label: "Active", render: (r) => (r.is_active ? "Yes" : "No") }]}
          fields={[{ name: "name", label: "Service name", required: true, width: 8 },
            { name: "category", label: "Category", type: "ref", ref: "/helpdesk/categories/", required: true, width: 4 },
            { name: "description", label: "Description shown to employees", type: "textarea" },
            { name: "team_role", label: "Route to role (least-loaded agent)", type: "ref", ref: "/admin/roles/", width: 6 },
            { name: "default_assignee", label: "Or always assign to", type: "ref", ref: "/users/lookup/", refLabel: (u) => String(u.full_name), width: 6 },
            { name: "default_priority", label: "Default priority", type: "select", options: PRIORITIES, width: 4 },
            { name: "response_sla_hours", label: "First response SLA (hours)", type: "number", width: 4 },
            { name: "resolution_sla_hours", label: "Resolution SLA (hours)", type: "number", width: 4 },
            { name: "letter_template", label: "One-click letter template", type: "ref", ref: "/documents/templates/", width: 6 },
            { name: "form_fields", label: "Request form fields (JSON)", type: "json", width: 6, helper: '[{"name": "period", "label": "Payroll month", "required": true}]' },
            { name: "is_confidential", label: "Confidential", type: "checkbox", width: 4 },
            { name: "self_service", label: "Visible in self-service", type: "checkbox", width: 4 },
            { name: "is_active", label: "Active", type: "checkbox", width: 4 }]}
          defaults={{ default_priority: "normal", response_sla_hours: 8, resolution_sla_hours: 72, form_fields: "[]", self_service: true, is_active: true }} />}
        {tab === 1 && <ResourcePage embedded title="Category" url="/helpdesk/categories/"
          columns={[{ key: "name", label: "Name" }, { key: "code", label: "Code" }, { key: "order", label: "Order" }, { key: "service_count", label: "Services" }]}
          fields={[{ name: "name", label: "Name", required: true, width: 8 }, { name: "code", label: "Code", required: true, width: 4 },
            { name: "order", label: "Display order", type: "number" }]} defaults={{ order: 100 }} />}
        {tab === 2 && <ResourcePage embedded title="Article" url="/helpdesk/articles/" canDelete
          columns={[{ key: "title", label: "Title" }, { key: "category_name", label: "Category" }, { key: "views", label: "Views" },
            { key: "helpful_yes", label: "👍" }, { key: "helpful_no", label: "👎" }, { key: "is_published", label: "Published", render: (r) => (r.is_published ? "Yes" : "No") }]}
          fields={[{ name: "title", label: "Title", required: true }, { name: "category", label: "Category", type: "ref", ref: "/helpdesk/categories/", width: 6 },
            { name: "tags", label: "Search tags (comma separated)", width: 6 }, { name: "body", label: "Answer", type: "textarea", required: true },
            { name: "is_published", label: "Published", type: "checkbox" }]} defaults={{ is_published: true }} />}
      </Card>
    </>
  );
}
