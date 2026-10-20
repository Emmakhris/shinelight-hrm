import { ResourcePage } from "../../components/ResourcePage";
import { StatusChip } from "../../components/Feedback";
import { fmtDate, fmtMoney } from "../../utils";

export const LOAN_TYPES = [
  { value: "salary_advance", label: "Salary advance" }, { value: "staff_loan", label: "Staff loan" },
  { value: "car_loan", label: "Vehicle loan" }, { value: "housing", label: "Housing / rent advance" }, { value: "other", label: "Other" },
];

export default function MyLoans() {
  return (
    <ResourcePage title="Loans & salary advances" url="/payroll/loans/" params={{ mine: 1 }} searchable={false} canEdit={false}
      subtitle="Apply for a loan or salary advance. Approved amounts are recovered through payroll in equal instalments."
      createLabel="Apply"
      columns={[
        { key: "loan_type_label", label: "Type" },
        { key: "principal", label: "Amount", align: "right", render: (r) => fmtMoney(r.principal as string) },
        { key: "installment_amount", label: "Monthly", align: "right", render: (r) => fmtMoney(r.installment_amount as string) },
        { key: "balance", label: "Balance", align: "right", render: (r) => fmtMoney(r.balance as string) },
        { key: "start_date", label: "First deduction", render: (r) => fmtDate(r.start_date as string) },
        { key: "status", label: "Status", render: (r) => <StatusChip value={r.status as string} /> },
      ]}
      fields={[
        { name: "loan_type", label: "Type", type: "select", options: LOAN_TYPES, required: true },
        { name: "principal", label: "Amount (GHS)", type: "number", required: true, width: 6 },
        { name: "installments", label: "Number of monthly instalments", type: "number", required: true, width: 6 },
        { name: "start_date", label: "First deduction month (any date in month)", type: "date", required: true },
        { name: "purpose", label: "Purpose", type: "textarea" },
      ]} defaults={{ installments: 1 }} />
  );
}
