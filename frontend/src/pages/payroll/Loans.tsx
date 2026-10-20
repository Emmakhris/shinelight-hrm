import { Button } from "@mui/material";
import { api } from "../../api/client";
import { useInvalidate } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { StatusChip, useToast } from "../../components/Feedback";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtDate, fmtMoney } from "../../utils";
import { LOAN_TYPES } from "../me/MyLoans";

export default function Loans() {
  const { can } = useAuth();
  const toast = useToast();
  const inv = useInvalidate();
  return (
    <ResourcePage title="Staff loans & salary advances" url="/payroll/loans/" canEdit={false} writePerm="payroll.prepare" createLabel="Record loan"
      subtitle="Approved loans are deducted automatically each payroll until the balance is cleared."
      columns={[
        { key: "employee_name", label: "Employee" }, { key: "loan_type_label", label: "Type" },
        { key: "principal", label: "Principal", align: "right", render: (r) => fmtMoney(r.principal as string) },
        { key: "installment_amount", label: "Instalment", align: "right", render: (r) => fmtMoney(r.installment_amount as string) },
        { key: "repaid", label: "Repaid", align: "right", render: (r) => fmtMoney(r.repaid as string) },
        { key: "balance", label: "Balance", align: "right", render: (r) => fmtMoney(r.balance as string) },
        { key: "start_date", label: "Starts", render: (r) => fmtDate(r.start_date as string) },
        { key: "status", label: "Status", render: (r) => <StatusChip value={r.status as string} /> },
      ]}
      rowActions={(r) => r.status === "active" && can("payroll.approve") ? (
        <Button size="small" color="error" onClick={async () => {
          const reason = window.prompt("Reason for write-off:"); if (!reason) return;
          await api.post(`/payroll/loans/${r.id}/write-off/`, { reason }); toast.ok("Loan written off."); inv("/payroll/loans/");
        }}>Write off</Button>) : null}
      fields={[
        { name: "employee", label: "Employee", type: "ref", ref: "/employees/", refLabel: (e) => `${e.full_name} (${e.staff_number})`, required: true },
        { name: "loan_type", label: "Type", type: "select", options: LOAN_TYPES, required: true },
        { name: "principal", label: "Amount (GHS)", type: "number", required: true, width: 4 },
        { name: "installments", label: "Instalments", type: "number", required: true, width: 4 },
        { name: "interest_rate", label: "Flat annual interest %", type: "number", width: 4 },
        { name: "start_date", label: "First deduction (any date in month)", type: "date", required: true },
        { name: "purpose", label: "Purpose", type: "textarea" },
      ]} defaults={{ installments: 6, interest_rate: 0 }} />
  );
}
