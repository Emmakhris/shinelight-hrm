import { Card, Tab, Tabs } from "@mui/material";
import { useState } from "react";
import { StatusChip } from "../../components/Feedback";
import { PageHeader } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtDateTime } from "../../utils";

const EVENTS = ["workflow.task_assigned", "workflow.reminder", "workflow.escalated", "workflow.approved", "workflow.rejected", "workflow.returned",
  "leave.recalled", "payroll.payslip_ready", "expiry.contract", "expiry.probation", "expiry.document", "expiry.license", "attendance.missing_punch",
  "announcement.published", "celebration.birthday", "celebration.anniversary"];

export default function NotificationsAdmin() {
  const [tab, setTab] = useState(0);
  return (
    <>
      <PageHeader title="Notifications & announcements" />
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}><Tab label="Announcements" /><Tab label="Message templates" /><Tab label="Email / SMS delivery log" /></Tabs>
      <Card>
        {tab === 0 && <ResourcePage embedded title="Announcement" url="/announcements/" params={{ manage: 1 }} canDelete createLabel="New announcement"
          columns={[{ key: "title", label: "Title" }, { key: "audience", label: "Audience" }, { key: "publish_at", label: "Publish", render: (r) => fmtDateTime(r.publish_at as string) },
            { key: "requires_acknowledgment", label: "Ack.", render: (r) => (r.requires_acknowledgment ? `${r.ack_count} acknowledged` : "") },
            { key: "is_pinned", label: "Pinned", render: (r) => (r.is_pinned ? "Yes" : "") }]}
          fields={[{ name: "title", label: "Title", required: true }, { name: "body", label: "Message", type: "textarea", required: true },
            { name: "audience", label: "Audience", type: "select", width: 6, options: [{ value: "all", label: "All staff" }, { value: "department", label: "Departments" }, { value: "branch", label: "Branches" }] },
            { name: "departments", label: "Departments", type: "multiref", ref: "/org/departments/", hidden: (v) => v.audience !== "department" },
            { name: "branches", label: "Branches", type: "multiref", ref: "/org/branches/", hidden: (v) => v.audience !== "branch" },
            { name: "publish_at", label: "Publish at", type: "datetime", required: true, width: 6 }, { name: "expires_at", label: "Expires at", type: "datetime", width: 6 },
            { name: "is_pinned", label: "Pin to top", type: "checkbox", width: 6 }, { name: "requires_acknowledgment", label: "Require acknowledgment", type: "checkbox", width: 6 }]}
          defaults={{ audience: "all", publish_at: new Date().toISOString().slice(0, 16), departments: [], branches: [] }} />}
        {tab === 1 && <ResourcePage embedded title="Template" url="/notifications/templates/" canDelete
          intro="Override the built-in wording for any event and channel. Use Django template syntax, e.g. {{ title }}, {{ period }}. Keep SMS free of confidential details."
          columns={[{ key: "event_code", label: "Event" }, { key: "channel", label: "Channel" }, { key: "subject", label: "Subject" },
            { key: "is_active", label: "Active", render: (r) => (r.is_active ? "Yes" : "No") }]}
          fields={[{ name: "event_code", label: "Event", type: "select", required: true, options: EVENTS.map((e) => ({ value: e, label: e })), width: 6 },
            { name: "channel", label: "Channel", type: "select", required: true, width: 6, options: [{ value: "in_app", label: "In-app" }, { value: "email", label: "Email" }, { value: "sms", label: "SMS" }] },
            { name: "department", label: "Only for department (optional)", type: "ref", ref: "/org/departments/" },
            { name: "subject", label: "Subject / title" }, { name: "body", label: "Body", type: "textarea", required: true }, { name: "is_active", label: "Active", type: "checkbox" }]}
          defaults={{ is_active: true, channel: "email" }} />}
        {tab === 2 && <ResourcePage embedded title="Delivery" url="/notifications/deliveries/" searchable={false}
          columns={[{ key: "created_at", label: "When", render: (r) => fmtDateTime(r.created_at as string) }, { key: "channel", label: "Channel" },
            { key: "recipient", label: "Recipient" }, { key: "event_code", label: "Event" }, { key: "status", label: "Status", render: (r) => <StatusChip value={r.status as string} /> },
            { key: "error", label: "Error" }]} />}
      </Card>
    </>
  );
}
