import { Box, Button, Card, Dialog, DialogContent, DialogTitle, Stack, Step, StepLabel, Stepper, Typography } from "@mui/material";
import { useState } from "react";
import { post, useApi, useInvalidate, useList } from "../api/hooks";
import { DataTable } from "../components/DataTable";
import { StatusChip, useToast } from "../components/Feedback";
import { PageHeader } from "../components/PageHeader";
import { RequestSummary } from "../components/RequestSummary";
import { fmtDateTime, titleCase } from "../utils";

interface Inst { id: number; title: string; request_type: string; request_type_label: string; status: string;
  created_at: string; waiting_on: string[]; target_summary: Record<string, unknown> }
interface Detail extends Inst {
  history: { id: number; action: string; comment: string; actor_name: string; created_at: string }[];
  tasks: { id: number; step_name: string; assignee_name: string; status: string; acted_at: string | null; comment: string }[];
}

export function RequestDialog({ id, onClose }: { id: number | null; onClose: () => void }) {
  const { data } = useApi<Detail>(id ? `/workflow/requests/${id}/` : null);
  const inv = useInvalidate();
  const toast = useToast();
  return (
    <Dialog open={!!id} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>{data?.title}</DialogTitle>
      <DialogContent dividers>
        {data && (
          <Stack spacing={2}>
            <StatusChip value={data.status} />
            <RequestSummary type={data.request_type} s={data.target_summary} />
            <Typography variant="subtitle2">Approval history</Typography>
            <Stepper orientation="vertical" activeStep={data.history.length}>
              {data.history.map((h) => (
                <Step key={h.id} completed>
                  <StepLabel optional={<Typography variant="caption">{fmtDateTime(h.created_at)} · {h.actor_name}{h.comment && ` — “${h.comment}”`}</Typography>}>
                    {titleCase(h.action)}
                  </StepLabel>
                </Step>
              ))}
            </Stepper>
            {data.status === "in_progress" && <Typography variant="body2">Waiting on: <b>{data.waiting_on.join(", ") || "—"}</b></Typography>}
            <Box>
              {["in_progress", "returned"].includes(data.status) && (
                <Button color="error" onClick={async () => { await post(`/workflow/requests/${data.id}/cancel/`); toast.ok("Request cancelled."); inv("/workflow/", "/leave/", "/me/"); onClose(); }}>
                  Withdraw request
                </Button>
              )}
              {data.status === "returned" && (
                <Button onClick={async () => { await post(`/workflow/requests/${data.id}/resubmit/`); toast.ok("Resubmitted."); inv("/workflow/", "/me/"); onClose(); }}>
                  Resubmit unchanged
                </Button>
              )}
            </Box>
          </Stack>
        )}
      </DialogContent>
    </Dialog>
  );
}

export default function MyRequests() {
  const { items, isLoading } = useList<Inst>("/workflow/requests/", { mine: 1 });
  const [open, setOpen] = useState<number | null>(null);
  return (
    <>
      <PageHeader title="My requests" subtitle="Track every request you've submitted and see who must act next." />
      <Card>
        <DataTable loading={isLoading} rows={items as unknown as Record<string, unknown>[]} onRowClick={(r) => setOpen(r.id as number)} columns={[
          { key: "title", label: "Request" },
          { key: "request_type_label", label: "Type", hideOnMobile: true },
          { key: "status", label: "Status", render: (r) => <StatusChip value={r.status as string} /> },
          { key: "waiting_on", label: "Waiting on", render: (r) => r.status === "in_progress" ? (r.waiting_on as string[]).join(", ") : "—" },
          { key: "created_at", label: "Submitted", render: (r) => fmtDateTime(r.created_at as string), hideOnMobile: true },
        ]} />
      </Card>
      <RequestDialog id={open} onClose={() => setOpen(null)} />
    </>
  );
}
