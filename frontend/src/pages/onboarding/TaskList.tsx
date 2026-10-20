import Warning from "@mui/icons-material/WarningAmber";
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Rating, Stack, TextField, Tooltip,
  Typography } from "@mui/material";
import { useState } from "react";
import { errorMessage, openBlob } from "../../api/client";
import { post, useInvalidate } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { DataTable } from "../../components/DataTable";
import { ConfirmDialog, StatusChip, useToast } from "../../components/Feedback";
import { fmtDate } from "../../utils";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

function CompleteDialog({ task, onClose }: { task: R; onClose: () => void }) {
  const [response, setResponse] = useState<R>({});
  const [notes, setNotes] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const inv = useInvalidate();
  const toast = useToast();
  const { me } = useAuth();
  const submit = async () => {
    setErr(null);
    try {
      await post(`/onboarding/tasks/${task.id}/complete/`, { response, notes });
      toast.ok("Task completed."); inv("/onboarding/", "/me/onboarding"); onClose();
    } catch (e) { setErr(errorMessage(e)); }
  };
  const own = task.employee_id === me?.employee?.id;
  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{task.title}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          {task.description && <Typography variant="body2">{task.description}</Typography>}
          {!own && <Typography variant="body2" color="text.secondary">For {task.employee_name} (starts {fmtDate(task.start_date)}).</Typography>}
          {task.document_category_name && <Alert severity="info">A {task.document_category_name.toLowerCase()} must be on the personnel file before this task can be closed.</Alert>}
          {task.policy && <Alert severity="info" action={<Button size="small" onClick={() => openBlob(`/documents/${task.policy.id}/download/`, { inline: 1 })}>Read</Button>}>
            {own ? `Completing this task records your acknowledgment of "${task.policy.title}".` : `The employee must acknowledge "${task.policy.title}" first.`}</Alert>}
          {(task.form || []).map((f: R) => f.type === "rating" ? (
            <Stack key={f.key} direction="row" justifyContent="space-between" alignItems="center">
              <Typography variant="body2">{f.label}</Typography>
              <Rating value={response[f.key] || 0} onChange={(_, v) => setResponse({ ...response, [f.key]: v })} />
            </Stack>
          ) : <TextField key={f.key} label={f.label} required={f.required} multiline minRows={2} value={response[f.key] || ""}
            onChange={(e) => setResponse({ ...response, [f.key]: e.target.value })} />)}
          <TextField label="Notes (optional)" value={notes} onChange={(e) => setNotes(e.target.value)} multiline minRows={2} />
          {err && <Alert severity="error">{err}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions><Button onClick={onClose}>Cancel</Button><Button variant="contained" onClick={submit}>Mark done</Button></DialogActions>
    </Dialog>
  );
}

export function TaskList({ tasks, loading, showEmployee, manage }: { tasks: R[]; loading?: boolean; showEmployee?: boolean; manage?: boolean }) {
  const [completing, setCompleting] = useState<R | null>(null);
  const [waiving, setWaiving] = useState<R | null>(null);
  const inv = useInvalidate();
  const toast = useToast();
  return (
    <>
      <DataTable dense loading={loading} rows={tasks} emptyTitle="No tasks" columns={[
        { key: "due_date", label: "Due", render: (t) => <Stack direction="row" spacing={0.5} alignItems="center">
          {t.overdue && <Tooltip title={t.escalated_at ? "Overdue: escalated to HR" : "Overdue"}><Warning fontSize="small" color="warning" /></Tooltip>}
          <span>{fmtDate(t.due_date)}</span></Stack> },
        ...(showEmployee ? [{ key: "employee_name", label: "New hire", render: (t: R) => <><b>{t.employee_name}</b><br /><small>{t.department_name}</small></> }] : []),
        { key: "title", label: "Task", render: (t) => <>{t.title}{!t.is_mandatory && <small> (optional)</small>}<br /><small>{t.category_label}</small></> },
        { key: "owner_label", label: "Owner", hideOnMobile: true, render: (t) => t.assignee_name || t.role_name || t.owner_label },
        { key: "status", label: "Status", render: (t) => <Box><StatusChip value={t.status} />{t.completed_by_name && <><br /><small>{t.completed_by_name}</small></>}</Box> },
        { key: "_a", label: "", align: "right", render: (t) => <Stack direction="row" spacing={1} justifyContent="flex-end">
          {t.status === "pending" && t.can_complete && <Button size="small" variant="contained" onClick={() => setCompleting(t)}>Done</Button>}
          {manage && t.status === "pending" && <Button size="small" onClick={() => setWaiving(t)}>Waive</Button>}
          {manage && t.status !== "pending" && <Button size="small" onClick={async () => { await post(`/onboarding/tasks/${t.id}/reopen/`); toast.ok("Reopened."); inv("/onboarding/"); }}>Reopen</Button>}
        </Stack> },
      ]} />
      {completing && <CompleteDialog task={completing} onClose={() => setCompleting(null)} />}
      <ConfirmDialog open={!!waiving} title={`Waive "${waiving?.title}"?`} comment="required" confirmLabel="Waive" onClose={() => setWaiving(null)}
        onConfirm={async (reason) => { await post(`/onboarding/tasks/${waiving?.id}/waive/`, { reason }); toast.ok("Waived."); inv("/onboarding/"); }} />
    </>
  );
}
