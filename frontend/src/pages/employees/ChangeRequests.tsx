import { StatusChip } from "../../components/Feedback";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtDate, titleCase } from "../../utils";

export default function ChangeRequests() {
  return (
    <ResourcePage title="Personal data change requests" url="/employees/change-requests/"
      subtitle="Submitted through self-service. Approve or reject from the Approvals inbox." searchable={false}
      columns={[
        { key: "employee_name", label: "Employee" },
        { key: "changes", label: "Requested changes", render: (r) => Object.entries(r.changes as Record<string, string>)
          .map(([k, v]) => `${titleCase(k)}: ${(r.previous as Record<string, string>)[k] || "—"} → ${v}`).join("; ") },
        { key: "reason", label: "Reason" },
        { key: "created_at", label: "Submitted", render: (r) => fmtDate(r.created_at as string) },
        { key: "status", label: "Status", render: (r) => <StatusChip value={r.status as string} /> },
      ]} />
  );
}
