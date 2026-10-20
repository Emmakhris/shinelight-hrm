import { useNavigate } from "react-router-dom";
import { StatusChip } from "../../components/Feedback";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtDate, fmtMoney } from "../../utils";

export default function Reviews() {
  const nav = useNavigate();
  return (
    <ResourcePage title="Salary reviews" url="/compensation/reviews/" writePerm="compensation.manage" createLabel="New review cycle"
      subtitle="Plan increments against a budget and grade guidelines; approved reviews are applied as effective-dated salary changes (back-dating creates arrears)."
      onRowClick={(r) => nav(`/compensation/reviews/${r.id}`)} searchable={false}
      columns={[{ key: "name", label: "Review" }, { key: "effective_date", label: "Effective", render: (r) => fmtDate(r.effective_date) },
        { key: "employees", label: "Staff", render: (r) => r.summary.employees },
        { key: "avg", label: "Avg increase", render: (r) => `${r.summary.average_percent}%` },
        { key: "annual", label: "Annual cost", align: "right", render: (r) => fmtMoney(r.summary.annual_increase) },
        { key: "budget", label: "Budget", render: (r) => (r.budget_percent > 0 ? `${Number(r.budget_percent)}% ${r.summary.within_budget ? "✓" : "— over budget"}` : "—") },
        { key: "status", label: "Status", render: (r) => <StatusChip value={r.status} /> }]}
      fields={[{ name: "name", label: "Name (e.g. 2027 annual review)", required: true },
        { name: "effective_date", label: "Effective date", type: "date", required: true, width: 4 },
        { name: "budget_percent", label: "Budget (% of payroll)", type: "number", width: 4 },
        { name: "default_increase_percent", label: "Default increase %", type: "number", width: 4 },
        { name: "departments", label: "Limit to departments (blank = all)", type: "multiref", ref: "/org/departments/" },
        { name: "guidelines", label: "Guidelines by grade level (JSON)", type: "json", helper: '[{"min_level": 1, "max_level": 3, "min": 5, "max": 10}]' },
        { name: "notes", label: "Notes", type: "textarea" }]}
      defaults={{ guidelines: "[]", departments: [], budget_percent: 0, default_increase_percent: 0 }} />
  );
}
