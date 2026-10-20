import Draw from "@mui/icons-material/Draw";
import { Alert, Button, Card, Checkbox, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, Stack, TextField,
  Typography } from "@mui/material";
import { useState } from "react";
import { api, errorMessage, openBlob } from "../../api/client";
import { useApi, useInvalidate } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { DataTable } from "../../components/DataTable";
import { ConfirmDialog, StatusChip, useToast } from "../../components/Feedback";
import { PageHeader } from "../../components/PageHeader";
import { fmtDate, fmtDateTime } from "../../utils";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export default function MySignatures() {
  const { me } = useAuth();
  const tasks = useApi<R[]>("/documents/signatures/my-tasks/");
  const [signing, setSigning] = useState<R | null>(null);
  const [declining, setDeclining] = useState<R | null>(null);
  const [name, setName] = useState("");
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inv = useInvalidate();
  const toast = useToast();
  const sign = async () => {
    setError(null);
    try {
      await api.post(`/documents/signatures/sign/${signing!.signer_id}/`, { typed_name: name, consent });
      toast.ok("Signed. A copy is filed with the document.");
      setSigning(null); setName(""); setConsent(false); inv("/documents/");
    } catch (e) { setError(errorMessage(e)); }
  };
  return (
    <>
      <PageHeader title="Documents to sign" subtitle="Contracts, letters and policies sent to you for electronic signature." />
      <Card>
        <DataTable loading={tasks.isLoading} rows={(tasks.data || []).map((t) => ({ ...t, id: t.signer_id }))} emptyTitle="Nothing to sign"
          columns={[{ key: "document_title", label: "Document" }, { key: "role_label", label: "Signing as" },
            { key: "due_date", label: "Due", render: (r) => fmtDate(r.due_date) },
            { key: "status", label: "Status", render: (r) => <StatusChip value={r.status === "waiting" ? "pending" : r.status} label={r.status === "waiting" ? "Waiting for others" : undefined} /> },
            { key: "signed_at", label: "Signed", render: (r) => fmtDateTime(r.signed_at) },
            { key: "_a", label: "", align: "right", render: (r) => <Stack direction="row" spacing={1} justifyContent="flex-end">
              <Button size="small" onClick={() => openBlob(`/documents/signatures/preview/${r.signer_id}/`)}>{r.request_status === "completed" ? "Signed copy" : "Read"}</Button>
              {r.status === "pending" && <Button size="small" variant="contained" startIcon={<Draw />} onClick={() => setSigning(r)}>Sign</Button>}
              {r.status === "pending" && <Button size="small" color="error" onClick={() => setDeclining(r)}>Decline</Button>}
            </Stack> }]} />
      </Card>
      <Dialog open={!!signing} onClose={() => setSigning(null)} fullWidth maxWidth="sm">
        <DialogTitle>Sign “{signing?.document_title}”</DialogTitle>
        <DialogContent dividers>
          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
          {signing?.message && <Alert severity="info" sx={{ mb: 2 }}>{signing.message}</Alert>}
          <Button onClick={() => openBlob(`/documents/signatures/preview/${signing!.signer_id}/`)} sx={{ mb: 2 }}>Open the document first</Button>
          <TextField fullWidth label={`Type your full name: ${me?.full_name}`} value={name} onChange={(e) => setName(e.target.value)}
            InputProps={{ sx: { fontFamily: "'Brush Script MT', cursive", fontSize: 22 } }} />
          <FormControlLabel sx={{ mt: 2 }} control={<Checkbox checked={consent} onChange={(e) => setConsent(e.target.checked)} />}
            label={<Typography variant="body2">I have read this document and agree to sign it electronically. I understand my typed name, the time and my IP address are recorded as my signature.</Typography>} />
        </DialogContent>
        <DialogActions><Button onClick={() => setSigning(null)}>Cancel</Button><Button variant="contained" disabled={!consent || !name} onClick={sign}>Sign document</Button></DialogActions>
      </Dialog>
      <ConfirmDialog open={!!declining} onClose={() => setDeclining(null)} title="Decline to sign" color="error" confirmLabel="Decline" comment="required"
        onConfirm={async (c) => { await api.post(`/documents/signatures/decline/${declining!.signer_id}/`, { reason: c }); toast.ok("Declined. HR has been notified."); inv("/documents/"); }} />
    </>
  );
}
