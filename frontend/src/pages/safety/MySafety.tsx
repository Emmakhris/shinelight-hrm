import { Alert, Button, Card } from "@mui/material";
import { useState } from "react";
import { useApi } from "../../api/hooks";
import { DataTable } from "../../components/DataTable";
import { StatusChip } from "../../components/Feedback";
import { PageHeader } from "../../components/PageHeader";
import { fmtDateTime } from "../../utils";
import { ReportIncidentDialog } from "./Safety";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export default function MySafety() {
  const q = useApi<R>("/safety/incidents/", { mine: 1 });
  const [open, setOpen] = useState(false);
  return (
    <>
      <PageHeader title="Report a safety incident" subtitle="Accidents, near misses, needlestick injuries, aggression, hazards."
        actions={<Button variant="contained" color="error" onClick={() => setOpen(true)}>Report now</Button>} />
      <Alert severity="info" sx={{ mb: 2 }}>Needlestick or splash exposure? Wash the area, tell your in-charge, report here and go to occupational health / the emergency unit immediately.</Alert>
      <Card>
        <DataTable loading={q.isLoading} rows={q.data?.results || []} emptyTitle="You have not reported any incidents" columns={[
          { key: "reference", label: "Ref" }, { key: "occurred_at", label: "When", render: (r) => fmtDateTime(r.occurred_at) },
          { key: "kind_label", label: "Type" }, { key: "location", label: "Where" },
          { key: "status", label: "Status", render: (r) => <StatusChip value={r.status === "closed" ? "completed" : "in_progress"} label={r.status_label} /> }]} />
      </Card>
      <ReportIncidentDialog open={open} onClose={() => setOpen(false)} />
    </>
  );
}
