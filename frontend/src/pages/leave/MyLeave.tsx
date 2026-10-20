import Add from "@mui/icons-material/Add";
import { Button, Card, CardContent, Grid2 as Grid, LinearProgress, Typography } from "@mui/material";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { post, useApi, useInvalidate, useList } from "../../api/hooks";
import { DataTable } from "../../components/DataTable";
import { ConfirmDialog, StatusChip, useToast } from "../../components/Feedback";
import { PageHeader, Section } from "../../components/PageHeader";
import { useAuth } from "../../auth/AuthContext";
import { fmtDate } from "../../utils";
import { RequestDialog } from "../MyRequests";
import ApplyLeaveDialog from "./ApplyLeaveDialog";

type B = { leave_type: number; leave_type_name: string; tracks_balance: boolean; opening: string; entitlement: string; taken: string;
  pending: string; balance: string; available: string; color: string; adjustments: string };

export default function MyLeave() {
  const { me } = useAuth();
  const [params] = useSearchParams();
  const [applying, setApplying] = useState(params.get("apply") === "1");
  const [cancelling, setCancelling] = useState<Record<string, unknown> | null>(null);
  const [viewing, setViewing] = useState<number | null>(null);
  const year = new Date().getFullYear();
  const balances = useApi<B[]>("/leave/requests/balances/", { year });
  const requests = useList("/leave/requests/", { employee: me?.employee?.id });
  const toast = useToast();
  const inv = useInvalidate();
  return (
    <>
      <PageHeader title="My leave" subtitle={`Leave year ${year}`}
        actions={<Button variant="contained" startIcon={<Add />} onClick={() => setApplying(true)}>Apply for leave</Button>} />
      <Grid container spacing={2} sx={{ mb: 2 }}>
        {(balances.data || []).filter((b) => b.tracks_balance).map((b) => {
          const total = Number(b.opening) + Number(b.entitlement) + Number(b.adjustments);
          return (
            <Grid key={b.leave_type} size={{ xs: 12, sm: 6, md: 3 }}>
              <Card sx={{ borderTop: `3px solid ${b.color}` }}><CardContent>
                <Typography variant="body2" color="text.secondary">{b.leave_type_name}</Typography>
                <Typography variant="h5">{Number(b.available)} <Typography component="span" variant="body2">days available</Typography></Typography>
                <LinearProgress variant="determinate" value={total ? Math.min(100, (Number(b.taken) / total) * 100) : 0} sx={{ my: 1, height: 6, borderRadius: 3 }} />
                <Typography variant="caption" color="text.secondary">
                  Entitled {Number(b.entitlement)}{Number(b.opening) ? ` + ${Number(b.opening)} carried` : ""} · Taken {Number(b.taken)} · Pending {Number(b.pending)}
                </Typography>
              </CardContent></Card>
            </Grid>
          );
        })}
      </Grid>
      <Section title="My leave requests" dense>
        <DataTable loading={requests.isLoading} rows={requests.items} onRowClick={(r) => r.workflow_instance && setViewing(r.workflow_instance as number)}
          columns={[
            { key: "leave_type_name", label: "Type" },
            { key: "start_date", label: "From", render: (r) => fmtDate(r.start_date as string) },
            { key: "end_date", label: "To", render: (r) => fmtDate(r.end_date as string) },
            { key: "days", label: "Days", align: "right", render: (r) => Number(r.days) },
            { key: "expected_return_date", label: "Return", render: (r) => fmtDate(r.expected_return_date as string), hideOnMobile: true },
            { key: "status", label: "Status", render: (r) => <StatusChip value={r.status as string} /> },
            { key: "_a", label: "", align: "right", render: (r) => ["pending", "returned"].includes(r.status as string)
              || (r.status === "approved" && (r.start_date as string) > new Date().toISOString().slice(0, 10))
              ? <Button size="small" color="error" onClick={(e) => { e.stopPropagation(); setCancelling(r); }}>Cancel</Button> : null },
          ]} />
      </Section>
      <ApplyLeaveDialog open={applying} onClose={() => setApplying(false)} />
      <RequestDialog id={viewing} onClose={() => setViewing(null)} />
      <ConfirmDialog open={!!cancelling} onClose={() => setCancelling(null)} title="Cancel leave request?" color="error" confirmLabel="Cancel request"
        comment="optional" onConfirm={async (c) => { await post(`/leave/requests/${cancelling!.id}/cancel/`, { reason: c }); toast.ok("Leave cancelled."); inv("/leave/", "/me/"); }} />
    </>
  );
}
