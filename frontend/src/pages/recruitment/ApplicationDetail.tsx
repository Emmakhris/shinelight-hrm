import { Alert, Box, Button, Chip, Grid2 as Grid, List, ListItem, ListItemText, Rating, Stack, Typography } from "@mui/material";
import { useState } from "react";
import { Link as RouterLink, useNavigate, useParams } from "react-router-dom";
import { api, openBlob } from "../../api/client";
import { post, useApi, useInvalidate } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { DataTable } from "../../components/DataTable";
import { ConfirmDialog, ErrorAlert, Loading, StatusChip, useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { Field, Kpi, PageHeader, Section } from "../../components/PageHeader";
import { fmtDate, fmtDateTime, fmtMoney } from "../../utils";
import { CHECK_TYPES, EMPLOYMENT_TYPES, RECOMMENDATIONS, STAGE_LABEL } from "./constants";
import { MoveDialog } from "./VacancyPipeline";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
const recLabel = (v: string) => RECOMMENDATIONS.find((r) => r.value === v)?.label || v;

export default function ApplicationDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const { can } = useAuth();
  const toast = useToast();
  const inv = useInvalidate();
  const q = useApi<R>(`/recruitment/applications/${id}/`);
  const [moving, setMoving] = useState(false);
  const [dialog, setDialog] = useState<null | "interview" | "check" | "offer" | "note">(null);
  const [checkEdit, setCheckEdit] = useState<R | null>(null);
  const [revise, setRevise] = useState<R | null>(null);
  const [confirm, setConfirm] = useState<null | { title: string; message?: string; url: string; body?: R; comment?: "required"; ok: string; key?: string }>(null);
  if (q.isLoading) return <Loading />;
  if (!q.data) return <ErrorAlert error={q.error} />;
  const a = q.data;
  const c = a.candidate;
  const manage = can("recruitment.manage");
  const offerPerm = can("recruitment.offer");
  const refresh = () => inv("/recruitment/");
  const act = async (fn: () => Promise<unknown>, msg: string) => {
    try { await fn(); toast.ok(msg); refresh(); } catch (e) { toast.error(e); }
  };
  const closed = ["hired", "rejected", "withdrawn"].includes(a.stage);
  const latestOffer: R | undefined = (a.offers || []).find((o: R) => !["superseded"].includes(o.status));
  const offerFields = [
    { name: "job_title", label: "Job title", type: "ref" as const, ref: "/org/job-titles/", required: true, width: 6 as const },
    { name: "department", label: "Department", type: "ref" as const, ref: "/org/departments/", required: true, width: 6 as const },
    { name: "grade_step", label: "Grade step", type: "ref" as const, ref: "/org/grade-steps/", refLabel: (o: R) => `${o.grade_code || o.grade} step ${o.step} — GHS ${o.basic_salary}`, width: 6 as const },
    { name: "basic_salary", label: "Basic salary (GHS/month)", type: "number" as const, required: true, width: 6 as const },
    { name: "allowances", label: "Monthly allowances (JSON)", type: "json" as const, helper: '[{"name":"Transport","amount":300}]' },
    { name: "employment_type", label: "Employment type", type: "select" as const, options: EMPLOYMENT_TYPES, width: 6 as const },
    { name: "supervisor", label: "Reports to", type: "ref" as const, ref: "/directory/", width: 6 as const },
    { name: "start_date", label: "Start date", type: "date" as const, required: true, width: 4 as const },
    { name: "probation_months", label: "Probation (months)", type: "number" as const, width: 4 as const },
    { name: "expiry_date", label: "Respond by", type: "date" as const, required: true, width: 4 as const },
    { name: "contract_end_date", label: "Contract end (fixed-term only)", type: "date" as const, width: 6 as const },
    { name: "terms", label: "Additional terms", type: "textarea" as const },
    { name: "submit", label: "Submit for approval now", type: "checkbox" as const },
  ];
  return (
    <>
      <PageHeader title={c.full_name} subtitle={<>{a.reference} · <RouterLink to={`/recruitment/vacancies/${a.vacancy}`}>{a.vacancy_title}</RouterLink> · applied {fmtDate(a.applied_at)}</>}
        crumbs={[{ label: "Vacancies", to: "/recruitment/vacancies" }, { label: a.vacancy_reference || "Vacancy", to: `/recruitment/vacancies/${a.vacancy}` }, { label: c.full_name }]}
        actions={<>
          <StatusChip value={a.stage} label={STAGE_LABEL[a.stage]} />
          {a.has_cv && <Button onClick={() => openBlob(`/recruitment/applications/${id}/cv/`)}>View CV</Button>}
          {manage && !closed && <Button variant="contained" onClick={() => setMoving(true)}>Move stage</Button>}
          {manage && <Button onClick={() => setDialog("note")}>Add note</Button>}
        </>} />
      {a.stage === "hired" && <Alert severity="success" sx={{ mb: 2 }}>Hired. <RouterLink to={`/employees/${a.hired_employee}`}>Open employee record</RouterLink></Alert>}
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 4 }}>
          <Section title="Candidate">
            <Stack spacing={1}>
              <Field label="Email" value={c.email} /><Field label="Phone" value={c.phone || "—"} />
              <Field label="Qualification" value={`${a.qualification}${c.field_of_study ? `, ${c.field_of_study}` : ""}`} />
              <Field label="Experience" value={`${Number(c.years_experience)} years`} />
              <Field label="Current role" value={[c.current_title, c.current_employer].filter(Boolean).join(", ") || "—"} />
              <Field label="Location" value={c.location || "—"} />
              <Field label="Source" value={<>{a.source}{a.internal && <Chip size="small" label="Internal" sx={{ ml: 1 }} />}</>} />
              <Field label="Talent pool" value={c.talent_pool ? `Yes, until ${fmtDate(c.retain_until)}` : `No (data kept until ${fmtDate(c.retain_until)})`} />
              {c.applications?.length > 1 && <Field label="Other applications" value={c.applications.filter((x: R) => x.id !== a.id).map((x: R) =>
                <div key={x.id}><RouterLink to={`/recruitment/applications/${x.id}`}>{x.vacancy}</RouterLink> — {STAGE_LABEL[x.stage]}</div>)} />}
            </Stack>
          </Section>
          <Section title="Screening">
            <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 1 }}>
              <Kpi label="Screening score" value={`${a.screening_score}/100`} color={a.knocked_out ? "#b91c1c" : undefined} />
            </Stack>
            {(a.screening_flags || []).map((f: string) => <Alert key={f} severity={f.startsWith("Knock-out") ? "error" : "warning"} sx={{ mb: 0.5, py: 0 }}>{f}</Alert>)}
            {(a.questions || []).map((qn: R) => <Field key={qn.key} label={qn.question} value={String(a.answers?.[qn.key] ?? "—")} />)}
            <Box sx={{ mt: 1 }}>
              <Typography variant="caption" color="text.secondary">Recruiter rating</Typography><br />
              <Rating value={a.rating || 0} readOnly={!manage} onChange={(_, val) => act(() => api.patch(`/recruitment/applications/${id}/`, { rating: val }), "Rating saved.")} />
            </Box>
            {a.cover_letter && <><Typography variant="caption" color="text.secondary">Cover letter</Typography>
              <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>{a.cover_letter}</Typography></>}
          </Section>
        </Grid>
        <Grid size={{ xs: 12, md: 8 }}>
          <Section title="Interviews" actions={manage && !closed && <Button size="small" onClick={() => setDialog("interview")}>Schedule interview</Button>}>
            {a.summary?.scorecards > 0 && <Alert severity="info" sx={{ mb: 1 }}>
              {a.summary.scorecards} scorecard(s), average {a.summary.average_score}/100 ·{" "}
              {Object.entries(a.summary.recommendations || {}).map(([k, n]) => `${recLabel(k)}: ${n}`).join(", ")}</Alert>}
            {(a.interviews || []).length === 0 && <Typography color="text.secondary">No interviews scheduled.</Typography>}
            {(a.interviews || []).map((iv: R) => (
              <Box key={iv.id} sx={{ borderTop: "1px solid #eef0f3", py: 1 }}>
                <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap">
                  <Box><b>{iv.round_name}</b> · {fmtDateTime(iv.scheduled_at)} · {iv.mode.replace("_", " ")}{iv.venue && ` · ${iv.venue}`}<br />
                    <small>Panel: {iv.panel_names.join(", ")}</small></Box>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <StatusChip value={iv.status} />
                    {manage && iv.status === "scheduled" && <>
                      <Button size="small" onClick={() => act(() => post(`/recruitment/interviews/${iv.id}/mark/`, { status: "no_show" }), "Marked as no-show.")}>No-show</Button>
                      <Button size="small" color="error" onClick={() => act(() => post(`/recruitment/interviews/${iv.id}/cancel/`), "Interview cancelled; candidate notified.")}>Cancel</Button></>}
                  </Stack>
                </Stack>
                {iv.scorecards.length > 0 && <DataTable dense rows={iv.scorecards} columns={[
                  { key: "panelist_name", label: "Panelist" },
                  { key: "overall_score", label: "Score", align: "right", render: (s) => `${Number(s.overall_score)}` },
                  { key: "recommendation", label: "Recommendation", render: (s) => recLabel(s.recommendation) },
                  { key: "strengths", label: "Strengths / concerns", render: (s) => <small>{s.strengths}{s.concerns && <><br /><i>{s.concerns}</i></>}{s.conflict_of_interest && <><br /><b>Declared conflict of interest (excluded)</b></>}</small> },
                ]} />}
              </Box>
            ))}
          </Section>
          <Section title="Reference & background checks" actions={manage && !closed && <Button size="small" onClick={() => setDialog("check")}>Add check</Button>}>
            <DataTable dense rows={a.checks || []} emptyTitle="No checks recorded" columns={[
              { key: "check_type", label: "Type", render: (k) => CHECK_TYPES.find((x) => x.value === k.check_type)?.label },
              { key: "referee_name", label: "Referee / source", render: (k) => <>{k.referee_name}<br /><small>{[k.referee_organization, k.referee_contact].filter(Boolean).join(" · ")}</small></> },
              { key: "consent_obtained", label: "Consent", render: (k) => (k.consent_obtained ? "Yes" : "No") },
              { key: "status", label: "Status", render: (k) => <StatusChip value={k.status} /> },
              { key: "outcome_notes", label: "Outcome", render: (k) => <small>{k.outcome_notes}</small> },
              { key: "_a", label: "", render: (k) => manage && <Button size="small" onClick={() => setCheckEdit(k)}>Update</Button> },
            ]} />
          </Section>
          {offerPerm && <Section title="Offer" actions={!closed && ["interview", "assessment", "reference_check", "offer"].includes(a.stage) &&
            (!latestOffer || ["declined", "withdrawn", "expired", "rejected", "negotiating"].includes(latestOffer.status)) &&
            <Button size="small" variant="contained" onClick={() => { setRevise(latestOffer && latestOffer.status === "negotiating" ? latestOffer : null); setDialog("offer"); }}>
              {latestOffer?.status === "negotiating" ? "Revise offer" : "Make offer"}</Button>}>
            {(a.offers || []).length === 0 && <Typography color="text.secondary">No offer yet.</Typography>}
            {(a.offers || []).map((o: R) => (
              <Box key={o.id} sx={{ borderTop: "1px solid #eef0f3", py: 1, opacity: o.status === "superseded" ? 0.6 : 1 }}>
                <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" spacing={1}>
                  <Box><b>{o.reference} rev {o.revision}</b> · {o.job_title_name} · {fmtMoney(o.basic_salary)}/month · starts {fmtDate(o.start_date)} · respond by {fmtDate(o.expiry_date)}
                    {o.response_note && <><br /><small>Candidate: {o.response_note}</small></>}</Box>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <StatusChip value={o.status} />
                    <Button size="small" onClick={() => openBlob(`/recruitment/offers/${o.id}/letter/`)}>Letter</Button>
                    {["draft", "returned"].includes(o.status) && <Button size="small" variant="contained" onClick={() => act(() => post(`/recruitment/offers/${o.id}/submit/`), "Submitted for approval.")}>Submit</Button>}
                    {o.status === "approved" && <Button size="small" variant="contained" onClick={() => setConfirm({ title: "Send the offer to the candidate?", message: `The candidate receives an email with a secure link to view and accept the offer by ${fmtDate(o.expiry_date)}.`, url: `/recruitment/offers/${o.id}/send/`, ok: "Send offer" })}>Send</Button>}
                    {["draft", "pending", "approved", "returned", "sent", "negotiating"].includes(o.status) && <Button size="small" color="error" onClick={() => setConfirm({ title: "Withdraw this offer?", url: `/recruitment/offers/${o.id}/withdraw/`, comment: "required", ok: "Withdraw", key: "reason" })}>Withdraw</Button>}
                    {o.status === "accepted" && a.stage !== "hired" && <Button size="small" variant="contained" color="success" onClick={() => setConfirm({ title: `Hire ${c.full_name}?`, message: "Creates the employee record (effective-dated appointment), files the CV and offer letter in the personnel file, and starts onboarding and probation reviews.", url: `/recruitment/offers/${o.id}/hire/`, ok: "Create employee" })}>Hire</Button>}
                  </Stack>
                </Stack>
                {o.status !== "superseded" && (o.warnings || []).map((w: string) => <Alert key={w} severity="warning" sx={{ mt: 0.5, py: 0 }}>{w}</Alert>)}
              </Box>
            ))}
          </Section>}
          <Section title="Timeline">
            <List dense>
              {[...(a.events || [])].reverse().map((e: R) => (
                <ListItem key={e.id} disableGutters>
                  <ListItemText primary={e.kind === "stage" ? `${e.from_stage ? STAGE_LABEL[e.from_stage] + " → " : ""}${STAGE_LABEL[e.to_stage] || e.to_stage}${e.note ? `: ${e.note}` : ""}`
                    : e.kind === "message" ? `Email sent: ${e.note}` : e.note}
                    secondary={`${fmtDateTime(e.created_at)}${e.actor_name ? ` · ${e.actor_name}` : ""}`} />
                </ListItem>))}
            </List>
          </Section>
        </Grid>
      </Grid>
      {moving && <MoveDialog ids={[a.id]} onClose={() => setMoving(false)} onDone={() => { toast.ok("Moved."); refresh(); }} />}
      <FormDialog open={dialog === "note"} title="Add a note" onClose={() => setDialog(null)} fields={[{ name: "note", label: "Note", type: "textarea", required: true }]}
        onSubmit={async (d) => { await post(`/recruitment/applications/${id}/note/`, d); toast.ok("Saved."); refresh(); }} />
      <FormDialog open={dialog === "interview"} title="Schedule interview" onClose={() => setDialog(null)}
        initial={{ round_name: "Panel interview", duration_minutes: 45, mode: "in_person", notify_candidate: true, panel: [] }}
        fields={[
          { name: "round_name", label: "Round", required: true, width: 8 }, { name: "duration_minutes", label: "Minutes", type: "number", width: 4 },
          { name: "scheduled_at", label: "Date and time", type: "datetime", required: true, width: 6 },
          { name: "mode", label: "Format", type: "select", options: [{ value: "in_person", label: "In person" }, { value: "phone", label: "Phone" }, { value: "video", label: "Video call" }], width: 6 },
          { name: "venue", label: "Venue / meeting link" },
          { name: "panel", label: "Panel members", type: "multiref", ref: "/users/lookup/", refLabel: (u) => String(u.full_name || u.username), required: true },
          { name: "notify_candidate", label: "Email the invitation to the candidate", type: "checkbox" },
        ]}
        onSubmit={async (d) => {
          const body = { ...(d as R), application: Number(id), scheduled_at: new Date((d as R).scheduled_at).toISOString() };
          await api.post("/recruitment/interviews/", body); toast.ok("Interview scheduled; panel notified."); refresh();
        }} />
      <FormDialog open={dialog === "check"} title="Add verification" onClose={() => setDialog(null)} initial={{ check_type: "reference", consent_obtained: false }}
        fields={[
          { name: "check_type", label: "Type", type: "select", options: CHECK_TYPES, required: true },
          { name: "referee_name", label: "Referee / institution", width: 6 }, { name: "referee_organization", label: "Organization", width: 6 },
          { name: "referee_relationship", label: "Relationship", width: 6 }, { name: "referee_contact", label: "Phone / email", width: 6 },
          { name: "consent_obtained", label: "The candidate authorised this verification", type: "checkbox" },
        ]}
        onSubmit={async (d) => { await api.post("/recruitment/checks/", { ...(d as R), application: Number(id) }); toast.ok("Added."); refresh(); }} />
      <FormDialog open={!!checkEdit} title="Update verification" onClose={() => setCheckEdit(null)} initial={checkEdit || undefined}
        fields={[
          { name: "consent_obtained", label: "The candidate authorised this verification", type: "checkbox" },
          { name: "status", label: "Status", type: "select", required: true, options: [["pending", "Pending"], ["in_progress", "In progress"], ["verified", "Verified"], ["concerns", "Verified with concerns"], ["failed", "Failed / could not verify"]].map(([value, label]) => ({ value, label })) },
          { name: "outcome_notes", label: "Outcome notes", type: "textarea" },
        ]}
        onSubmit={async (d) => { await post(`/recruitment/checks/${checkEdit?.id}/set-status/`, d); toast.ok("Updated."); refresh(); }} />
      <FormDialog open={dialog === "offer"} maxWidth="md" title={revise ? `Revise offer ${revise.reference}` : "Make an offer"} onClose={() => setDialog(null)}
        intro={<Alert severity="info">The offer is approved by the HR Director (and finance if above the requisition budget) before it can be sent.</Alert>}
        initial={revise ? { ...revise, submit: false } : { probation_months: 6, employment_type: "permanent", allowances: [], submit: true }}
        fields={offerFields}
        onSubmit={async (d) => { await api.post("/recruitment/offers/", { ...(d as R), application: Number(id), revise: !!revise }); toast.ok(revise ? "Revision created." : "Offer created."); refresh(); }} />
      <ConfirmDialog open={!!confirm} title={confirm?.title || ""} message={confirm?.message} confirmLabel={confirm?.ok} comment={confirm?.comment || "none"}
        onClose={() => setConfirm(null)}
        onConfirm={async (text) => {
          const r = await post<R>(confirm!.url, confirm!.key ? { [confirm!.key]: text } : confirm!.body);
          toast.ok(r?.detail || "Done."); refresh();
          if (r?.employee) nav(`/employees/${r.employee}`);
        }} />
    </>
  );
}

