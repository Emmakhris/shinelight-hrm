import { ResourcePage } from "../../components/ResourcePage";
import { titleCase } from "../../utils";

export const UNIT_TYPES = ["directorate", "department", "unit", "team", "ward"].map((v) => ({ value: v, label: titleCase(v) }));

export default function Departments() {
  return (
    <ResourcePage title="Departments & units" url="/org/departments/" createLabel="Add unit"
      subtitle="The organization hierarchy. Minimum staffing is used to warn approvers about leave clashes."
      columns={[
        { key: "code", label: "Code" }, { key: "name", label: "Name" },
        { key: "unit_type", label: "Type", render: (r) => titleCase(r.unit_type as string) },
        { key: "parent_name", label: "Parent" }, { key: "head_name", label: "Head" },
        { key: "headcount", label: "Staff", align: "right" }, { key: "min_staffing", label: "Min. staffing", align: "right" },
        { key: "is_active", label: "Active", render: (r) => (r.is_active ? "Yes" : "No") },
      ]}
      fields={[
        { name: "code", label: "Code", required: true, width: 4 }, { name: "name", label: "Name", required: true, width: 8 },
        { name: "unit_type", label: "Type", type: "select", options: UNIT_TYPES, width: 6 },
        { name: "parent", label: "Parent unit", type: "ref", ref: "/org/departments/", width: 6 },
        { name: "branch", label: "Branch", type: "ref", ref: "/org/branches/", width: 6 },
        { name: "cost_center", label: "Cost centre", type: "ref", ref: "/org/cost-centers/", refLabel: (c) => `${c.code} — ${c.name}`, width: 6 },
        { name: "head", label: "Head of unit", type: "ref", ref: "/employees/", refLabel: (e) => `${e.full_name} (${e.staff_number})` },
        { name: "min_staffing", label: "Minimum staff on duty", type: "number", width: 6 },
        { name: "is_active", label: "Active", type: "checkbox", width: 6 },
      ]} defaults={{ unit_type: "department", is_active: true, min_staffing: 0 }} />
  );
}
