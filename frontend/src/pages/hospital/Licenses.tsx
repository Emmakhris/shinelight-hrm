import { Button } from "@mui/material";
import dayjs from "dayjs";
import { api } from "../../api/client";
import { useInvalidate } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { StatusChip, useToast } from "../../components/Feedback";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtDate } from "../../utils";

const REGULATORS = [{ value: "mdc", label: "Medical and Dental Council" }, { value: "nmc", label: "Nursing and Midwifery Council" },
  { value: "pc", label: "Pharmacy Council" }, { value: "ahpc", label: "Allied Health Professions Council" }, { value: "other", label: "Other" }];

export default function Licenses() {
  const { can } = useAuth();
  const toast = useToast();
  const inv = useInvalidate();
  return (
    <ResourcePage title="Professional licences" url="/hospital/licenses/" writePerm="hospital.manage" createLabel="Add licence" canDelete
      subtitle="Clinical staff without an active, verified licence cannot be rostered for regulated duties."
      columns={[{ key: "employee_name", label: "Employee" }, { key: "license_type", label: "Licence" }, { key: "regulator_label", label: "Regulator" },
        { key: "registration_number", label: "Reg. no" },
        { key: "expiry_date", label: "Expires", render: (r) => {
          const days = r.expiry_date ? dayjs(r.expiry_date as string).diff(dayjs(), "day") : null;
          return days !== null && days <= 60 ? <StatusChip value={days < 0 ? "expired" : "expiring"} label={fmtDate(r.expiry_date as string)} /> : fmtDate(r.expiry_date as string);
        } },
        { key: "status", label: "Status", render: (r) => <StatusChip value={r.status as string} /> }]}
      rowActions={(r) => r.status === "pending" && can("hospital.manage") ? <Button size="small" onClick={async () => {
        const note = window.prompt("Verification note (e.g. checked on council register on …):"); if (note === null) return;
        await api.post(`/hospital/licenses/${r.id}/verify/`, { note }); toast.ok("Licence verified."); inv("/hospital/");
      }}>Verify</Button> : null}
      fields={[{ name: "employee", label: "Employee", type: "ref", ref: "/employees/", refLabel: (e) => `${e.full_name} (${e.staff_number})`, required: true },
        { name: "license_type", label: "Licence type (must match the job title requirement)", required: true },
        { name: "regulator", label: "Regulator", type: "select", options: REGULATORS, required: true, width: 6 },
        { name: "registration_number", label: "Registration number", required: true, width: 6 },
        { name: "issue_date", label: "Issued", type: "date", width: 6 }, { name: "expiry_date", label: "Expires", type: "date", width: 6 },
        { name: "status", label: "Status", type: "select", options: ["pending", "active", "expired", "suspended", "revoked"].map((v) => ({ value: v, label: v })) }]}
      defaults={{ status: "pending" }} />
  );
}
