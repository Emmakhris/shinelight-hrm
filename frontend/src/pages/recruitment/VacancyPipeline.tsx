import ContentCopy from "@mui/icons-material/ContentCopy";
import Flag from "@mui/icons-material/Flag";
import { Alert, Box, Button, Card, Checkbox, Chip, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel,
  MenuItem, Stack, Tab, Tabs, TextField, Tooltip } from "@mui/material";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, errorMessage } from "../../api/client";
import { post, useApi, useInvalidate } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { DataTable } from "../../components/DataTable";
import { ErrorAlert, Loading, StatusChip, useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { PageHeader } from "../../components/PageHeader";
import { fmtDate } from "../../utils";
import { MANUAL_STAGES, QUALIFICATIONS, SOURCES, STAGES, STAGE_LABEL } from "./constants";
import { VACANCY_FIELDS } from "./Vacancies";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export function MoveDialog({ ids, onClose, onDone }: { ids: (number | string)[]; onClose: () => void; onDone: () => void }) {
  const [stage, setStage] = useState("screening");
  const [reason, setReason] = useState("");
  const [notify, setNotify] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const submit = async () => {
    setErr(null);
    try {
      await post("/recruitment/applications/bulk-move/", { ids, stage, reason, note: reason, notify });
      onDone(); onClose();
    } catch (e) { setErr(errorMessage(e)); }
  };
  return (
    <Dialog open={ids.length > 0} onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle>Move {ids.length} candidate(s)</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <TextField select label="New stage" value={stage} onChange={(e) => setStage(e.target.value)}>
            {MANUAL_STAGES.map((s) => <MenuItem key={s.value} value={s.value}>{s.label}</MenuItem>)}
          </TextField>
          <TextField label={stage === "rejected" ? "Reason (required, kept on file)" : "Note"} value={reason}
            onChange={(e) => setReason(e.target.value)} multiline minRows={2} />
          {["shortlisted", "rejected"].includes(stage) && <FormControlLabel control={<Checkbox checked={notify} onChange={(e) => setNotify(e.target.checked)} />}
            label={stage === "rejected" ? "Send the regret email" : "Email the candidate that they are shortlisted"} />}
          {err && <Alert severity="error">{err}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions><Button onClick={onClose}>Cancel</Button><Button variant="contained" onClick={submit}>Move</Button></DialogActions>
    </Dialog>
  );
}

export default function VacancyPipeline() {
  const { id } = useParams();
  const nav = useNavigate();
  const { can, me } = useAuth();
  const toast = useToast();
  const inv = useInvalidate();
  const vac = useApi<R>(`/recruitment/vacancies/${id}/`);
  const [stage, setStage] = useState("active");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<(string | number)[]>([]);
  const [moving, setMoving] = useState<(string | number)[]>([]);
  const [editing, setEditing] = useState(false);
  const [adding, setAdding] = useState(false);
  const params = { vacancy: id, search, page_size: 200, ordering: "-screening_score",
    ...(stage === "active" ? { active: 1 } : stage === "all" ? {} : { stage }) };
  const apps = useApi<R>("/recruitment/applications/", params);
  if (vac.isLoading) return <Loading />;
  if (!vac.data) return <ErrorAlert error={vac.error} />;
  const v = vac.data;
  const counts: Record<string, number> = v.pipeline || {};
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  const active = STAGES.slice(0, 7).reduce((a, s) => a + (counts[s.value] || 0), 0);
  const manage = can("recruitment.manage");
  const refresh = () => inv("/recruitment/");
  const act = async (fn: () => Promise<unknown>, msg: string) => {
    try { await fn(); toast.ok(msg); refresh(); } catch (e) { toast.error(e); }
  };
  const careerLink = `${window.location.origin}/careers/${me?.organization?.code || ""}/${id}`;
  return (
    <>
      <PageHeader title={v.title} subtitle={`${v.reference || "Draft"} · ${v.department_name}${v.closing_date ? ` · closes ${fmtDate(v.closing_date)}` : ""}`}
        crumbs={[{ label: "Vacancies", to: "/recruitment/vacancies" }, { label: v.reference || v.title }]}
        actions={<>
          <StatusChip value={v.status} />
          {manage && ["draft", "closed"].includes(v.status) && <Button variant="contained" onClick={() => act(() => post(`/recruitment/vacancies/${id}/publish/`), "Published to the career site and internal job board.")}>Publish</Button>}
          {manage && v.status === "published" && <Button onClick={() => act(() => post(`/recruitment/vacancies/${id}/close/`, { status: "closed" }), "Closed to new applications.")}>Close applications</Button>}
          {manage && !["filled", "cancelled"].includes(v.status) && <Button onClick={() => setEditing(true)}>Edit</Button>}
          {manage && v.status !== "draft" && <Button onClick={() => setAdding(true)}>Add candidate</Button>}
          {v.status === "published" && v.visibility !== "internal" && <Tooltip title="Copy the public careers page link">
            <Button startIcon={<ContentCopy />} onClick={() => { navigator.clipboard?.writeText(careerLink); toast.ok("Link copied."); }}>Career link</Button></Tooltip>}
        </>} />
      <Card sx={{ mb: 2 }}>
        <Tabs value={stage} onChange={(_, s) => { setStage(s); setSelected([]); }} variant="scrollable" scrollButtons="auto">
          <Tab value="active" label={`In progress (${active})`} />
          {STAGES.map((s) => <Tab key={s.value} value={s.value} label={`${s.label} (${counts[s.value] || 0})`} />)}
          <Tab value="all" label={`All (${total})`} />
        </Tabs>
      </Card>
      <Card>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ p: 1.5 }}>
          <TextField placeholder="Search candidates…" value={search} onChange={(e) => setSearch(e.target.value)} sx={{ minWidth: 260 }} />
          <Box flex={1} />
          {manage && selected.length > 0 && <Button variant="contained" onClick={() => setMoving(selected)}>Move {selected.length} selected</Button>}
        </Stack>
        <Alert severity="info" sx={{ mx: 1.5, mb: 1 }}>Screening scores and flags are advisory. A recruiter decides every move, and rejections need a recorded reason.</Alert>
        <DataTable dense loading={apps.isLoading} rows={apps.data?.results || []} selectable={manage} selected={selected} onSelect={setSelected}
          onRowClick={(r) => nav(`/recruitment/applications/${r.id}`)} emptyTitle="No candidates at this stage"
          columns={[
            { key: "candidate_name", label: "Candidate", render: (r) => <><b>{r.candidate_name}</b>{r.internal && <Chip size="small" label="Internal" sx={{ ml: 1 }} />}<br /><small>{r.candidate_email}</small></> },
            { key: "qualification", label: "Qualification", hideOnMobile: true },
            { key: "years_experience", label: "Exp. (yrs)", align: "right", hideOnMobile: true, render: (r) => Number(r.years_experience) },
            { key: "screening_score", label: "Screen", align: "right", render: (r) => <Stack direction="row" spacing={0.5} justifyContent="flex-end" alignItems="center">
              {(r.knocked_out || r.screening_flags?.length > 0) && <Tooltip title={(r.screening_flags || []).join(" ")}><Flag fontSize="small" color={r.knocked_out ? "error" : "warning"} /></Tooltip>}
              <span>{r.screening_score}</span></Stack> },
            { key: "source", label: "Source", hideOnMobile: true },
            { key: "applied_at", label: "Applied", render: (r) => fmtDate(r.applied_at) },
            { key: "stage", label: "Stage", render: (r) => <StatusChip value={r.stage} label={STAGE_LABEL[r.stage]} /> },
          ]} />
      </Card>
      <MoveDialog ids={moving} onClose={() => setMoving([])} onDone={() => { setSelected([]); toast.ok("Candidates moved."); refresh(); }} />
      <FormDialog open={editing} title="Edit vacancy" fields={VACANCY_FIELDS} initial={v} maxWidth="md" onClose={() => setEditing(false)}
        onSubmit={async (d) => { await api.patch(`/recruitment/vacancies/${id}/`, d); toast.ok("Saved."); refresh(); }} />
      <FormDialog open={adding} title="Record an application" maxWidth="md" onClose={() => setAdding(false)}
        intro={<Alert severity="info">For agency, referral and walk-in candidates. Confirm the candidate has consented to the processing of their personal data.</Alert>}
        initial={{ vacancy: Number(id), source: "agency", highest_qualification: "degree", consent: false }}
        fields={[
          { name: "first_name", label: "First name", required: true, width: 6 }, { name: "last_name", label: "Last name", required: true, width: 6 },
          { name: "email", label: "Email", type: "email", required: true, width: 6 }, { name: "phone", label: "Phone", width: 6 },
          { name: "highest_qualification", label: "Highest qualification", type: "select", options: QUALIFICATIONS, width: 6 },
          { name: "years_experience", label: "Years' experience", type: "number", width: 6 },
          { name: "current_employer", label: "Current employer", width: 6 }, { name: "current_title", label: "Current title", width: 6 },
          { name: "source", label: "Source", type: "select", options: SOURCES, width: 6 },
          { name: "referred_by", label: "Referred by (staff)", type: "ref", ref: "/directory/", width: 6, hidden: (x) => x.source !== "referral" },
          { name: "cv", label: "Attach CV (PDF/Word)", type: "file" },
          { name: "consent", label: "The candidate consented to the processing of their data", type: "checkbox" },
          { name: "talent_pool", label: "Candidate agreed to be kept in the talent pool", type: "checkbox" },
          { name: "vacancy", label: "Vacancy", type: "number", hidden: () => true },
        ]}
        onSubmit={async (d) => {
          if (d instanceof FormData) d.set("vacancy", String(id)); else (d as R).vacancy = Number(id);
          await api.post("/recruitment/applications/", d); toast.ok("Application recorded."); refresh();
        }} />
    </>
  );
}
