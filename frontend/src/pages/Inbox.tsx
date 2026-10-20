import Check from "@mui/icons-material/Check";
import Close from "@mui/icons-material/Close";
import Undo from "@mui/icons-material/Undo";
import { Alert, Box, Button, Card, CardContent, Chip, Divider, Grid2 as Grid, List, ListItemButton, ListItemText, Stack,
  Tab, Tabs, Typography } from "@mui/material";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { post, useInvalidate, useList } from "../api/hooks";
import { ConfirmDialog, Empty, Loading, useToast } from "../components/Feedback";
import { PageHeader } from "../components/PageHeader";
import { RequestSummary } from "../components/RequestSummary";
import { fmtDateTime } from "../utils";

interface Task {
  id: number; step_name: string; status: string; due_at: string | null; delegated_from_name: string | null; is_escalation: boolean;
  instance: { id: number; title: string; request_type: string; request_type_label: string; initiator_name: string;
    subject_name: string | null; created_at: string; target_summary: Record<string, unknown> };
}

export default function Inbox() {
  const [tab, setTab] = useState("pending");
  const { items, isLoading } = useList<Task>("/workflow/inbox/", { status: tab === "pending" ? "pending" : undefined });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [action, setAction] = useState<"approve" | "reject" | "return" | null>(null);
  const inv = useInvalidate();
  const toast = useToast();
  const nav = useNavigate();
  const tasks = tab === "pending" ? items : items.filter((t) => t.status !== "pending");
  const sel = tasks.find((t) => t.id === selectedId) || tasks[0];
  const overdue = (t: Task) => t.due_at && new Date(t.due_at) < new Date();

  const act = async (comment: string) => {
    await post(`/workflow/inbox/${sel!.id}/act/`, { action, comment });
    toast.ok(action === "approve" ? "Approved." : action === "reject" ? "Rejected." : "Returned for correction.");
    setSelectedId(null);
    inv("/workflow/", "/leave/", "/me/", "/payroll/", "/notifications/");
  };

  return (
    <>
      <PageHeader title="Approvals inbox" subtitle="Requests waiting for your decision. Every action is recorded in the request history." />
      <Tabs value={tab} onChange={(_, v) => { setTab(v); setSelectedId(null); }} sx={{ mb: 2 }}>
        <Tab value="pending" label="Pending" /><Tab value="done" label="Completed by me" />
      </Tabs>
      {isLoading ? <Loading /> : tasks.length === 0 ? <Card><Empty title="Nothing waiting for you" hint="New requests will appear here." /></Card> : (
        <Grid container spacing={2}>
          <Grid size={{ xs: 12, md: 5 }}>
            <Card>
              <List disablePadding>
                {tasks.map((t) => (
                  <Box key={t.id}>
                    <ListItemButton selected={sel?.id === t.id} onClick={() => setSelectedId(t.id)}>
                      <ListItemText primary={t.instance.title}
                        secondary={<>{t.instance.request_type_label} · {t.step_name} · from {t.instance.initiator_name}
                          {t.delegated_from_name && ` · on behalf of ${t.delegated_from_name}`}</>} />
                      <Stack spacing={0.5} alignItems="flex-end">
                        {overdue(t) && t.status === "pending" && <Chip color="error" label="Overdue" />}
                        {t.is_escalation && <Chip color="warning" label="Escalated" />}
                        {t.status !== "pending" && <Chip label={t.status} variant="outlined" />}
                      </Stack>
                    </ListItemButton>
                    <Divider />
                  </Box>
                ))}
              </List>
            </Card>
          </Grid>
          <Grid size={{ xs: 12, md: 7 }}>
            {sel && (
              <Card>
                <CardContent>
                  <Typography variant="overline" color="text.secondary">{sel.instance.request_type_label}</Typography>
                  <Typography variant="h6">{sel.instance.title}</Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                    Submitted {fmtDateTime(sel.instance.created_at)} by {sel.instance.initiator_name}
                    {sel.due_at && ` · due ${fmtDateTime(sel.due_at)}`}
                  </Typography>
                  {overdue(sel) && sel.status === "pending" && <Alert severity="error" sx={{ mb: 2 }}>This request has passed its service deadline.</Alert>}
                  <RequestSummary type={sel.instance.request_type} s={sel.instance.target_summary} />
                  {sel.instance.request_type === "payroll_run" && (
                    <Button sx={{ mt: 2 }} variant="outlined" onClick={() => nav(`/payroll/runs/${sel.instance.target_summary.run_id}`)}>Open payroll run</Button>
                  )}
                  {sel.status === "pending" && (
                    <Stack direction="row" spacing={1} sx={{ mt: 3 }}>
                      <Button variant="contained" color="success" startIcon={<Check />} onClick={() => setAction("approve")}>Approve</Button>
                      <Button variant="outlined" color="warning" startIcon={<Undo />} onClick={() => setAction("return")}>Return for correction</Button>
                      <Button variant="outlined" color="error" startIcon={<Close />} onClick={() => setAction("reject")}>Reject</Button>
                    </Stack>
                  )}
                </CardContent>
              </Card>
            )}
          </Grid>
        </Grid>
      )}
      <ConfirmDialog open={!!action} onClose={() => setAction(null)} onConfirm={act}
        title={action === "approve" ? "Approve request" : action === "reject" ? "Reject request" : "Return for correction"}
        confirmLabel={action === "approve" ? "Approve" : action === "reject" ? "Reject" : "Return"}
        color={action === "approve" ? "success" : action === "reject" ? "error" : "warning"}
        comment={action === "approve" ? "optional" : "required"} message={sel?.instance.title} />
    </>
  );
}
