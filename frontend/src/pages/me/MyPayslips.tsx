import { Alert, Card } from "@mui/material";
import { useState } from "react";
import { useList } from "../../api/hooks";
import { DataTable } from "../../components/DataTable";
import { PageHeader } from "../../components/PageHeader";
import { PayslipDialog } from "../../components/PayslipView";
import { fmtDate, fmtMoney } from "../../utils";

export default function MyPayslips() {
  const { items, isLoading } = useList("/payroll/payslips/", { mine: 1 });
  const [open, setOpen] = useState<number | null>(null);
  return (
    <>
      <PageHeader title="My payslips" subtitle="Payslips appear here once payroll is released." />
      <Alert severity="info" sx={{ mb: 2 }}>Downloaded PDFs may be password-protected with your staff number or date of birth (DDMMYYYY).</Alert>
      <Card>
        <DataTable loading={isLoading} rows={items} onRowClick={(r) => setOpen(r.id as number)} emptyTitle="No payslips published yet"
          columns={[
            { key: "period_name", label: "Period" },
            { key: "pay_date", label: "Pay date", render: (r) => fmtDate(r.pay_date as string) },
            { key: "gross_pay", label: "Gross", align: "right", render: (r) => fmtMoney(r.gross_pay as string) },
            { key: "total_deductions", label: "Deductions", align: "right", render: (r) => fmtMoney(r.total_deductions as string), hideOnMobile: true },
            { key: "net_pay", label: "Net pay", align: "right", render: (r) => <b>{fmtMoney(r.net_pay as string)}</b> },
          ]} />
      </Card>
      <PayslipDialog id={open} onClose={() => setOpen(null)} />
    </>
  );
}
