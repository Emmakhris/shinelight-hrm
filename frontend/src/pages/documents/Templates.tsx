import { Alert, Button } from "@mui/material";
import { api } from "../../api/client";
import { ResourcePage } from "../../components/ResourcePage";
import { titleCase } from "../../utils";

const TYPES = ["appointment", "confirmation", "promotion", "transfer", "employment_confirmation", "introduction", "warning", "salary", "exit", "reference", "other"];

export default function Templates() {
  const preview = async (id: number) => {
    const emp = window.prompt("Preview with employee ID:");
    if (!emp) return;
    const res = await api.post(`/documents/templates/${id}/preview/`, { employee: Number(emp) }, { responseType: "blob" });
    window.open(URL.createObjectURL(res.data as Blob), "_blank", "noopener");
  };
  return (
    <ResourcePage title="Letter templates" url="/documents/templates/" createLabel="New template"
      intro={<Alert severity="info">Use Django template placeholders, e.g. {"{{ employee.full_name }}"}, {"{{ employee.staff_number }}"}, {"{{ job_title.name }}"},
        {" {{ department.name }}"}, {"{{ grade.code }}"}, {"{{ salary|floatformat:2 }}"}, {"{{ employee.hire_date|date:\"jS F, Y\" }}"}, {"{{ addressed_to }}"}, {"{{ purpose }}"}, {"{{ today }}"}.
        Letterhead and date are added automatically.</Alert>}
      columns={[{ key: "name", label: "Name" }, { key: "code", label: "Code" }, { key: "letter_type", label: "Type", render: (r) => titleCase(r.letter_type as string) },
        { key: "self_service", label: "Self-service", render: (r) => (r.self_service ? "Yes" : "") },
        { key: "requires_approval", label: "Needs approval", render: (r) => (r.requires_approval ? "Yes" : "No") }]}
      rowActions={(r) => <Button size="small" onClick={() => preview(r.id as number)}>Preview</Button>}
      fields={[{ name: "name", label: "Name", required: true, width: 8 }, { name: "code", label: "Code", required: true, width: 4 },
        { name: "letter_type", label: "Type", type: "select", options: TYPES.map((v) => ({ value: v, label: titleCase(v) })), width: 6 },
        { name: "output_category", label: "File generated letters under", type: "ref", ref: "/documents/categories/", width: 6 },
        { name: "body_html", label: "Body (HTML with placeholders)", type: "textarea", required: true },
        { name: "self_service", label: "Employees can request via self-service", type: "checkbox", width: 4 },
        { name: "requires_approval", label: "HR approval required", type: "checkbox", width: 4 },
        { name: "is_active", label: "Active", type: "checkbox", width: 4 }]} defaults={{ requires_approval: true, is_active: true, letter_type: "other" }} />
  );
}
