import { useNavigate } from "react-router-dom";
import { StatusChip } from "../../components/Feedback";
import type { FieldDef } from "../../components/FormDialog";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtDate } from "../../utils";
import { CYCLE_STATUS } from "./common";

export const CYCLE_FIELDS: FieldDef[] = [
  { name: "name", label: "Name", required: true, width: 8 },
  { name: "cycle_type", label: "Type", type: "select", width: 4, options: [{ value: "annual", label: "Annual" }, { value: "semiannual", label: "Half-year" }, { value: "quarterly", label: "Quarterly" }] },
  { name: "period_start", label: "Period start", type: "date", required: true, width: 6 },
  { name: "period_end", label: "Period end", type: "date", required: true, width: 6 },
  { name: "goal_setting_deadline", label: "Objectives agreed by", type: "date", width: 6 },
  { name: "midyear_date", label: "Mid-year check-in by", type: "date", width: 6 },
  { name: "self_review_deadline", label: "Self-assessment by", type: "date", width: 6 },
  { name: "manager_review_deadline", label: "Manager review by", type: "date", width: 6 },
  { name: "min_service_days", label: "Minimum service (days) to be included", type: "number", width: 6 },
  { name: "departments", label: "Limit to departments (blank = all)", type: "multiref", ref: "/org/departments/", width: 6 },
  { name: "include_probation", label: "Include staff on probation", type: "checkbox", width: 6 },
  { name: "use_calibration", label: "Calibrate ratings before release", type: "checkbox", width: 6 },
  { name: "target_distribution", label: "Target rating distribution % (JSON, guide only)", type: "json", helper: '{"5": 10, "4": 20, "3": 50, "2": 15, "1": 5}' },
];

export default function Cycles() {
  const nav = useNavigate();
  return (
    <ResourcePage title="Review cycles" url="/performance/cycles/" writePerm="performance.manage" canDelete createLabel="New cycle"
      subtitle="Launch a cycle to create appraisals for eligible staff, then move it through objective setting, mid-year, year-end review and calibration."
      onRowClick={(r) => nav(`/performance/cycles/${r.id}`)}
      columns={[
        { key: "name", label: "Cycle", render: (r) => <b>{r.name}</b> },
        { key: "period", label: "Period", render: (r) => `${fmtDate(r.period_start)} – ${fmtDate(r.period_end)}` },
        { key: "counts", label: "Appraisals", align: "right", render: (r) => `${r.counts.completed}/${r.counts.appraisals} complete` },
        { key: "status", label: "Phase", render: (r) => <StatusChip value={r.status === "closed" ? "completed" : r.status === "draft" ? "draft" : "in_progress"} label={CYCLE_STATUS[r.status]} /> },
      ]}
      fields={CYCLE_FIELDS}
      defaults={{ cycle_type: "annual", min_service_days: 90, use_calibration: true, include_probation: false, departments: [], target_distribution: { 5: 10, 4: 20, 3: 50, 2: 15, 1: 5 } }}
    />
  );
}
