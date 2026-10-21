import { Alert, Button, Card } from "@mui/material";
import { useState } from "react";
import { post, useApi, useInvalidate } from "../../api/hooks";
import { DataTable } from "../../components/DataTable";
import { StatusChip, useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { PageHeader } from "../../components/PageHeader";
import { fmtDate } from "../../utils";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export default function MyAssets() {
  const q = useApi<R>("/assets/assignments/", { mine: 1, page_size: 100 });
  const [report, setReport] = useState<R | null>(null);
  const toast = useToast();
  const inv = useInvalidate();
  const rows = q.data?.results || [];
  return (
    <>
      <PageHeader title="My equipment" subtitle="Items issued to you. Please acknowledge receipt and report anything lost or damaged straight away." />
      {rows.some((r: R) => !r.acknowledged_at && !r.returned_on) && <Alert severity="info" sx={{ mb: 2 }}>Some items are waiting for your acknowledgment.</Alert>}
      <Card>
        <DataTable loading={q.isLoading} rows={rows} emptyTitle="No equipment issued to you" columns={[
          { key: "item", label: "Item", render: (r) => <><b>{r.item}</b>{r.quantity > 1 && ` × ${r.quantity}`}<br /><small>{r.tag ? `${r.tag} · S/N ${r.serial_number || "—"}` : r.category_name}</small></> },
          { key: "issued_on", label: "Issued", render: (r) => fmtDate(r.issued_on) },
          { key: "status", label: "Status", render: (r) => r.returned_on ? <StatusChip value="completed" label={`Returned ${fmtDate(r.returned_on)}`} />
            : r.incident_report ? <StatusChip value="warning" label="Reported" /> : r.acknowledged_at ? <StatusChip value="active" label="With you" /> : <StatusChip value="pending" label="Please acknowledge" /> },
          { key: "_a", label: "", align: "right", render: (r) => !r.returned_on && <>
            {!r.acknowledged_at && <Button size="small" variant="contained" onClick={async () => { await post(`/assets/assignments/${r.id}/acknowledge/`); toast.ok("Thank you."); inv("/assets/"); }}>Acknowledge</Button>}
            {r.returnable && !r.incident_report && <Button size="small" color="error" onClick={() => setReport(r)}>Report lost / damaged</Button>}</> },
        ]} />
      </Card>
      <FormDialog open={!!report} title={`Report: ${report?.item}`} onClose={() => setReport(null)} initial={{ kind: "damaged" }}
        intro={<Alert severity="warning">You may be asked to contribute to the cost of a replacement under the asset policy.</Alert>}
        fields={[{ name: "kind", label: "What happened?", type: "select", required: true, options: [{ value: "damaged", label: "Damaged" }, { value: "lost", label: "Lost / stolen" }] },
          { name: "description", label: "Details (when, where; police report number if stolen)", type: "textarea", required: true }]}
        onSubmit={async (v) => { await post(`/assets/assignments/${report?.id}/report/`, v); toast.ok("Reported."); inv("/assets/"); }} />
    </>
  );
}
