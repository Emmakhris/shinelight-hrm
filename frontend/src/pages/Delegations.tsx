import { ResourcePage } from "../components/ResourcePage";
import { fmtDate } from "../utils";

const REQUEST_TYPES = [
  { value: "leave_request", label: "Leave" }, { value: "attendance_correction", label: "Attendance corrections" },
  { value: "employee_change", label: "Profile changes" }, { value: "loan_request", label: "Loans" },
  { value: "letter_request", label: "Letters" }, { value: "payroll_run", label: "Payroll" },
];

export default function Delegations() {
  return (
    <ResourcePage title="Delegation of authority" url="/workflow/delegations/" searchable={false} canDelete
      subtitle="While you are away, approvals assigned to you go to your delegate. Leave request types empty to delegate everything."
      createLabel="New delegation"
      columns={[
        { key: "delegator_name", label: "From" }, { key: "delegate_name", label: "Delegate" },
        { key: "start_date", label: "Start", render: (r) => fmtDate(r.start_date as string) },
        { key: "end_date", label: "End", render: (r) => fmtDate(r.end_date as string) },
        { key: "request_types", label: "Covers", render: (r) => ((r.request_types as string[]) || []).join(", ") || "All requests" },
        { key: "reason", label: "Reason" },
      ]}
      fields={[
        { name: "delegate", label: "Delegate to", type: "ref", ref: "/users/lookup/", refLabel: (u) => `${u.full_name} (${u.username})`, required: true },
        { name: "start_date", label: "Start date", type: "date", required: true, width: 6 },
        { name: "end_date", label: "End date", type: "date", required: true, width: 6 },
        { name: "request_types", label: "Request types (JSON list, e.g. [\"leave_request\"])", type: "json", helper: REQUEST_TYPES.map((t) => t.value).join(", ") },
        { name: "reason", label: "Reason" },
        { name: "is_active", label: "Active", type: "checkbox" },
      ]}
      defaults={{ request_types: "[]", is_active: true }} />
  );
}
