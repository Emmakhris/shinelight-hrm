import FlightTakeoff from "@mui/icons-material/FlightTakeoff";
import ReceiptLong from "@mui/icons-material/ReceiptLong";
import { Alert, Button } from "@mui/material";
import { useState } from "react";
import { useList } from "../../api/hooks";
import { DataTable } from "../../components/DataTable";
import { StatusChip } from "../../components/Feedback";
import { PageHeader, Section } from "../../components/PageHeader";
import { fmtDate, fmtMoney } from "../../utils";
import ClaimDialog from "./ClaimDialog";
import TravelDialog from "./TravelDialog";

export default function MyExpenses() {
  const [travel, setTravel] = useState(false);
  const [claim, setClaim] = useState(false);
  const trips = useList("/expenses/travel/", { mine: 1 });
  const claims = useList("/expenses/claims/", { mine: 1 });
  const overdue = trips.items.filter((t) => Number(t.advance_paid) > 0 && !t.claim_status && t.retirement_due && t.retirement_due < new Date().toISOString().slice(0, 10));
  return (
    <>
      <PageHeader title="Travel & expenses" subtitle="Request official travel, collect advances and claim reimbursements."
        actions={<>
          <Button startIcon={<FlightTakeoff />} onClick={() => setTravel(true)}>Request travel</Button>
          <Button variant="contained" startIcon={<ReceiptLong />} onClick={() => setClaim(true)}>New expense claim</Button>
        </>} />
      {overdue.length > 0 && <Alert severity="warning" sx={{ mb: 2 }}>You have {overdue.length} travel advance(s) overdue for retirement. Submit an expense claim linked to the trip.</Alert>}
      <Section title="My travel" dense>
        <DataTable dense loading={trips.isLoading} rows={trips.items} emptyTitle="No travel requests" columns={[
          { key: "reference", label: "Ref" }, { key: "destination", label: "Destination" },
          { key: "departure_date", label: "Dates", render: (r) => `${fmtDate(r.departure_date)} – ${fmtDate(r.return_date)}` },
          { key: "total_estimate", label: "Estimate", align: "right", render: (r) => fmtMoney(r.total_estimate, r.currency) },
          { key: "advance_paid", label: "Advance paid", align: "right", render: (r) => Number(r.advance_paid) ? fmtMoney(r.advance_paid, r.currency) : "—" },
          { key: "retirement_due", label: "Retire by", render: (r) => fmtDate(r.retirement_due) },
          { key: "status", label: "Status", render: (r) => <StatusChip value={r.status} /> }]} />
      </Section>
      <Section title="My expense claims" dense>
        <DataTable dense loading={claims.isLoading} rows={claims.items} emptyTitle="No claims" columns={[
          { key: "reference", label: "Ref" }, { key: "title", label: "Title" }, { key: "travel_reference", label: "Trip" },
          { key: "total", label: "Total", align: "right", render: (r) => fmtMoney(r.total) },
          { key: "net_payable", label: "Net", align: "right", render: (r) => fmtMoney(r.net_payable) },
          { key: "payment_method", label: "Paid via" },
          { key: "status", label: "Status", render: (r) => <StatusChip value={r.status} /> }]} />
      </Section>
      <TravelDialog open={travel} onClose={() => setTravel(false)} />
      <ClaimDialog open={claim} onClose={() => setClaim(false)} />
    </>
  );
}
