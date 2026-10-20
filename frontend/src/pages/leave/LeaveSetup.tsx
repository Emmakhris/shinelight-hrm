import { Box, Card, Tab, Tabs } from "@mui/material";
import { useState } from "react";
import { PageHeader } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";

export default function LeaveSetup() {
  const [tab, setTab] = useState(0);
  return (
    <>
      <PageHeader title="Leave types & policies" subtitle="Defaults follow the Labour Act, 2003 (Act 651) minimums — adjust to your conditions of service." />
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}><Tab label="Leave types" /><Tab label="Entitlement policies" /></Tabs>
      <Card>
        {tab === 0 && <ResourcePage embedded title="Leave type" url="/leave/types/"
          columns={[{ key: "name", label: "Name" }, { key: "code", label: "Code" },
            { key: "is_paid", label: "Paid", render: (r) => (r.is_paid ? "Yes" : "No") },
            { key: "tracks_balance", label: "Balance", render: (r) => (r.tracks_balance ? "Yes" : "No") },
            { key: "count_working_days", label: "Counts", render: (r) => (r.count_working_days ? "Working days" : "Calendar days") },
            { key: "color", label: "", render: (r) => <Box sx={{ width: 16, height: 16, borderRadius: 1, bgcolor: r.color as string }} /> }]}
          fields={[{ name: "name", label: "Name", required: true, width: 8 }, { name: "code", label: "Code", required: true, width: 4 },
            { name: "is_paid", label: "Paid leave", type: "checkbox", width: 6 }, { name: "tracks_balance", label: "Limited by balance", type: "checkbox", width: 6 },
            { name: "count_working_days", label: "Count working days only", type: "checkbox", width: 6 }, { name: "allow_half_day", label: "Allow half days", type: "checkbox", width: 6 },
            { name: "allow_negative_balance", label: "Allow negative balance", type: "checkbox", width: 6 }, { name: "allow_during_probation", label: "Allowed on probation", type: "checkbox", width: 6 },
            { name: "requires_attachment", label: "Requires supporting document", type: "checkbox", width: 6 },
            { name: "attachment_after_days", label: "…when more than (days)", type: "number", width: 6 },
            { name: "is_confidential", label: "Confidential (hide reason from managers)", type: "checkbox" },
            { name: "gender", label: "Gender restriction", type: "select", width: 6, options: [{ value: "female", label: "Female only" }, { value: "male", label: "Male only" }] },
            { name: "min_service_months", label: "Minimum service (months)", type: "number", width: 6 },
            { name: "notice_days", label: "Notice required (days)", type: "number", width: 6 }, { name: "max_days_per_request", label: "Max days per request (0 = none)", type: "number", width: 6 },
            { name: "color", label: "Calendar colour", type: "color", width: 6 }, { name: "is_active", label: "Active", type: "checkbox", width: 6 },
            { name: "description", label: "Description / policy notes", type: "textarea" }]}
          defaults={{ is_paid: true, tracks_balance: true, count_working_days: true, allow_half_day: true, allow_during_probation: true, is_active: true, color: "#2563eb" }} />}
        {tab === 1 && <ResourcePage embedded title="Policy" url="/leave/policies/" canDelete
          columns={[{ key: "name", label: "Policy" }, { key: "leave_type_name", label: "Leave type" }, { key: "category_name", label: "Category" },
            { key: "entitlement_days", label: "Days/yr", align: "right" }, { key: "accrual_method", label: "Accrual" },
            { key: "carryover_max_days", label: "Max carry-over", align: "right" }, { key: "priority", label: "Priority", align: "right" }]}
          fields={[{ name: "name", label: "Policy name", required: true }, { name: "leave_type", label: "Leave type", type: "ref", ref: "/leave/types/", required: true, width: 6 },
            { name: "category", label: "Employee category (blank = all)", type: "ref", ref: "/employees/categories/", width: 6 },
            { name: "min_grade_level", label: "Min grade level", type: "number", width: 4 }, { name: "max_grade_level", label: "Max grade level", type: "number", width: 4 },
            { name: "employment_type", label: "Employment type (blank = all)", width: 4 },
            { name: "entitlement_days", label: "Entitlement (days per year)", type: "number", required: true, width: 6 },
            { name: "accrual_method", label: "Accrual", type: "select", width: 6, options: [{ value: "upfront", label: "Full at start of year" }, { value: "monthly", label: "Monthly accrual" }, { value: "none", label: "None (event-based)" }] },
            { name: "prorate_first_year", label: "Pro-rate in year of hire", type: "checkbox" },
            { name: "carryover_max_days", label: "Max carry-over days", type: "number", width: 6 }, { name: "carryover_expiry_months", label: "Carried days expire after (months, 0 = never)", type: "number", width: 6 },
            { name: "service_bonus", label: "Extra days by service (JSON)", type: "json", helper: 'e.g. [{"years": 5, "days": 3}]' },
            { name: "priority", label: "Priority (lower wins)", type: "number", width: 6 }, { name: "is_active", label: "Active", type: "checkbox", width: 6 }]}
          defaults={{ accrual_method: "upfront", prorate_first_year: true, priority: 100, is_active: true, service_bonus: "[]", carryover_expiry_months: 3 }} />}
      </Card>
    </>
  );
}
