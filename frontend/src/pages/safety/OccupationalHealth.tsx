import { Alert, Card } from "@mui/material";
import { StatusChip } from "../../components/Feedback";
import { PageHeader } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtDate } from "../../utils";

const opts = (p: string[][]) => p.map(([value, label]) => ({ value, label }));
const KINDS = opts([["pre_employment", "Pre-employment medical"], ["fitness", "Fitness-for-duty assessment"], ["injury_care", "Work injury treatment"],
  ["exposure", "Exposure follow-up (e.g. PEP)"], ["vaccination", "Vaccination (e.g. Hepatitis B)"], ["return_to_work", "Return-to-work assessment"], ["surveillance", "Health surveillance"]]);
const FITNESS = opts([["fit", "Fit for duty"], ["fit_restricted", "Fit with restrictions"], ["unfit", "Temporarily unfit"], ["pending", "Assessment pending"]]);

export default function OccupationalHealth() {
  return (
    <>
      <PageHeader title="Occupational health records" subtitle="Restricted to occupational health professionals. Every record opened is audited." />
      <Alert severity="warning" sx={{ mb: 2 }}>Clinical notes stay here. HR, managers and rostering only see the fitness outcome and any work restrictions you record.</Alert>
      <Card>
        <ResourcePage embedded title="OH record" url="/safety/oh-records/" writePerm="ohs.medical" createLabel="Add record" canEdit={false}
          columns={[{ key: "date", label: "Date", render: (r) => fmtDate(r.date) }, { key: "employee_name", label: "Employee" }, { key: "kind_label", label: "Type" },
            { key: "fitness", label: "Fitness", render: (r) => (r.fitness ? <StatusChip value={r.fitness === "fit" ? "active" : r.fitness === "unfit" ? "error" : "warning"} label={r.fitness_label} /> : "—") },
            { key: "restrictions", label: "Restrictions", hideOnMobile: true }, { key: "review_date", label: "Review", render: (r) => fmtDate(r.review_date) },
            { key: "clinical_notes", label: "Notes", hideOnMobile: true, render: (r) => <small>{r.clinical_notes}</small> }]}
          fields={[{ name: "employee", label: "Employee", type: "ref", ref: "/employees/", required: true, width: 8 }, { name: "date", label: "Date", type: "date", required: true, width: 4 },
            { name: "kind", label: "Type", type: "select", options: KINDS, required: true, width: 6 },
            { name: "incident", label: "Related incident", type: "ref", ref: "/safety/incidents/", refLabel: (i) => `${i.reference} ${i.kind_label}`, width: 6 },
            { name: "clinical_notes", label: "Clinical notes (confidential)", type: "textarea" },
            { name: "fitness", label: "Fitness outcome", type: "select", options: FITNESS, width: 6 },
            { name: "restrictions", label: "Work restrictions (non-clinical wording)", width: 6 },
            { name: "valid_until", label: "Outcome valid until", type: "date", width: 6 }, { name: "review_date", label: "Review date", type: "date", width: 6 }]}
          defaults={{ date: new Date().toISOString().slice(0, 10), kind: "fitness" }} />
      </Card>
    </>
  );
}
