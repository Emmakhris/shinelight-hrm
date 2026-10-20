import { Alert, Box, Button, Chip, Grid2 as Grid, Stack, TextField, Typography } from "@mui/material";
import { useEffect, useState } from "react";
import { Link as RouterLink, useParams } from "react-router-dom";
import { api } from "../../api/client";
import { post, useApi, useInvalidate } from "../../api/hooks";
import { ConfirmDialog, ErrorAlert, Loading, StatusChip, useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { DataTable } from "../../components/DataTable";
import { Field, Kpi, PageHeader, Section } from "../../components/PageHeader";
import { fmtDate } from "../../utils";
import { APPRAISAL_STATUS, PROGRESS, RatingSelect, ratingLabel } from "./common";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
type Draft = { objectives: Record<number, R>; competencies: Record<number, R>; text: R };

function emptyDraft(a: R, field: "self_rating" | "manager_rating"): Draft {
  const objectives: Record<number, R> = {};
  const competencies: Record<number, R> = {};
  (a.objectives || []).forEach((o: R) => { objectives[o.id] = { [field]: o[field], achievement: o.achievement, manager_comment: o.manager_comment }; });
  (a.competency_ratings || []).forEach((c: R) => { competencies[c.id] = { [field]: c[field], comment: c.comment }; });
  return { objectives, competencies, text: { self_comments: a.self_comments, manager_comments: a.manager_comments, development_needs: a.development_needs } };
}

export default function AppraisalDetail() {
  const { id } = useParams();
  const toast = useToast();
  const inv = useInvalidate();
  const q = useApi<R>(`/performance/appraisals/${id}/`);
  const goals = useApi<R[]>(q.data ? "/performance/goals/" : null, { cycle: q.data?.cycle });
  const fb = useApi<R>(q.data?.include_360 ? `/performance/appraisals/${id}/feedback-summary/` : null);
  const [objDialog, setObjDialog] = useState<R | null>(null);
  const [dialog, setDialog] = useState<null | "midyear" | "calibrate" | "ack" | "feedback" | "submitObj">(null);
  const a = q.data;
  const mode: null | "self" | "manager" = a?.can?.self_review ? "self" : a?.can?.manager_review ? "manager" : null;
  const field = mode === "self" ? "self_rating" : "manager_rating";
  const [draft, setDraft] = useState<Draft | null>(null);
  const [err, setErr] = useState<unknown>(null);
  useEffect(() => { if (a && mode) setDraft(emptyDraft(a, field)); }, [a, mode, field]);
  if (q.isLoading) return <Loading />;
  if (!a) return <ErrorAlert error={q.error} />;
  const scale: R[] = a.scale || [];
  const refresh = () => inv("/performance/");
  const totalWeight = (a.objectives || []).reduce((s: number, o: R) => s + Number(o.weight), 0);
  const save = async (submit: boolean) => {
    if (!draft) return;
    setErr(null);
    const body = {
      objectives: Object.entries(draft.objectives).map(([oid, v]) => ({ id: Number(oid), ...v })),
      competencies: Object.entries(draft.competencies).map(([cid, v]) => ({ id: Number(cid), ...v })),
      ...draft.text, submit,
    };
    try {
      await post(`/performance/appraisals/${id}/${mode === "self" ? "self-review" : "manager-review"}/`, body);
      toast.ok(submit ? "Submitted." : "Draft saved."); refresh();
    } catch (e) { setErr(e); }
  };
  const setObj = (oid: number, k: string, v: unknown) => setDraft((d) => d && ({ ...d, objectives: { ...d.objectives, [oid]: { ...d.objectives[oid], [k]: v } } }));
  const setComp = (cid: number, k: string, v: unknown) => setDraft((d) => d && ({ ...d, competencies: { ...d.competencies, [cid]: { ...d.competencies[cid], [k]: v } } }));
  const showManager = a.role !== "employee" || ["acknowledgement", "completed"].includes(a.status);
  const editingObjectives = a.can?.edit_objectives;
  return (
    <>
      <PageHeader title={`${a.employee_name} — ${a.cycle_name}`} subtitle={`${a.job_title || ""} · ${a.department_name || ""} · reviewer ${a.reviewer_name || "not assigned"}`}
        crumbs={[{ label: a.role === "employee" ? "My performance" : "Appraisals", to: a.role === "employee" ? "/performance/my" : a.role === "reviewer" ? "/performance/team" : `/performance/cycles/${a.cycle}` }, { label: a.employee_name }]}
        actions={<>
          <StatusChip value={a.status === "completed" ? "completed" : "pending"} label={APPRAISAL_STATUS[a.status]} />
          {a.can?.midyear && <Button onClick={() => setDialog("midyear")}>Mid-year check-in</Button>}
          {a.can?.request_feedback && <Button onClick={() => setDialog("feedback")}>Request 360 feedback</Button>}
          {a.can?.calibrate && <Button variant="contained" onClick={() => setDialog("calibrate")}>Calibrate</Button>}
          {a.can?.acknowledge && <Button variant="contained" onClick={() => setDialog("ack")}>Acknowledge</Button>}
          {a.can?.plan && a.final_rating <= 2 && <Button component={RouterLink} to={`/performance/plans?employee=${a.employee}&appraisal=${a.id}`}>Improvement plan</Button>}
        </>} />
      <ErrorAlert error={err} />
      {showManager && a.final_rating != null && (
        <Grid container spacing={2} sx={{ mb: 2 }}>
          <Grid size={{ xs: 12, md: 4 }}><Kpi label="Final rating" value={ratingLabel(scale, a.final_rating)} /></Grid>
          <Grid size={{ xs: 4, md: 2 }}><Kpi label="Overall score" value={a.overall_score ?? "—"} /></Grid>
          <Grid size={{ xs: 4, md: 2 }}><Kpi label={`Objectives (${a.objectives_weight}%)`} value={a.objectives_score ?? "—"} /></Grid>
          <Grid size={{ xs: 4, md: 2 }}><Kpi label={`Competencies (${100 - a.objectives_weight}%)`} value={a.competencies_score ?? "—"} /></Grid>
          {a.manager_rating !== a.final_rating && a.role !== "employee" && <Grid size={{ xs: 12, md: 2 }}><Kpi label="Manager's rating" value={a.manager_rating} hint={a.calibration_reason} /></Grid>}
        </Grid>
      )}
      {a.status === "objectives_returned" && <Alert severity="warning" sx={{ mb: 2 }}>Your supervisor returned the objectives. See the comment in My requests, adjust and resubmit.</Alert>}
      {a.status === "acknowledgement" && a.role === "employee" && <Alert severity="info" sx={{ mb: 2 }}>Your review is complete. Read it and acknowledge; if you disagree, say why and HR will follow up.</Alert>}

      <Section title={`Objectives (${a.objectives_weight}% of score)`} actions={editingObjectives && <>
        <Chip color={totalWeight === 100 ? "success" : "warning"} label={`Weights ${totalWeight}% / 100%`} />
        <Button size="small" onClick={() => setObjDialog({ appraisal: a.id, weight: 0 })}>Add objective</Button>
        <Button size="small" variant="contained" onClick={() => setDialog("submitObj")}>Submit objectives</Button></>}>
        {editingObjectives && <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          Set {a.min_objectives}–{a.max_objectives} SMART objectives with a measure for each; weights must total 100%. Link each to a department or organization goal where possible.</Typography>}
        <DataTable dense rows={a.objectives} emptyTitle="No objectives yet" columns={[
          { key: "title", label: "Objective", render: (o) => <><b>{o.title}</b>{o.goal_title && <><br /><small>↳ {o.goal_title}</small></>}{o.description && <><br /><small>{o.description}</small></>}</> },
          { key: "measure", label: "Measure / target", render: (o) => <small>{o.measure}{o.target && ` · target ${o.target}`}</small> },
          { key: "weight", label: "Weight", align: "right", render: (o) => `${Number(o.weight)}%` },
          { key: "midyear_status", label: "Mid-year", hideOnMobile: true, render: (o) => o.midyear_status ? <Chip size="small" label={PROGRESS.find((p) => p.value === o.midyear_status)?.label} color={o.midyear_status === "off_track" ? "error" : o.midyear_status === "at_risk" ? "warning" : "success"} variant="outlined" /> : "" },
          ...(mode ? [] : [
            { key: "self_rating", label: "Self", render: (o: R) => o.self_rating ?? "—" },
            ...(showManager ? [{ key: "manager_rating", label: "Manager", render: (o: R) => <>{o.manager_rating ?? "—"}{o.manager_comment && <><br /><small>{o.manager_comment}</small></>}</> }] : []),
          ]),
          ...(editingObjectives ? [{ key: "_e", label: "", align: "right" as const, render: (o: R) => <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button size="small" onClick={() => setObjDialog(o)}>Edit</Button>
            <Button size="small" color="error" onClick={async () => { await api.delete(`/performance/objectives/${o.id}/`); refresh(); }}>Remove</Button></Stack> }] : []),
        ]} />
      </Section>

      {mode && draft && (
        <Section title={mode === "self" ? "Your self-assessment" : "Manager review"}>
          {mode === "manager" && a.self_submitted_at == null && <Alert severity="warning" sx={{ mb: 2 }}>The self-assessment deadline has passed without a submission; you can complete the review.</Alert>}
          <Typography variant="subtitle2" sx={{ mb: 1 }}>Objectives</Typography>
          <Stack spacing={2} sx={{ mb: 3 }}>
            {a.objectives.map((o: R) => (
              <Box key={o.id} sx={{ p: 1.5, border: "1px solid #e3e8ef", borderRadius: 1 }}>
                <Typography fontWeight={600}>{o.title} <small>({Number(o.weight)}%)</small></Typography>
                <Typography variant="body2" color="text.secondary">{o.measure}{o.target && ` · target ${o.target}`}</Typography>
                {mode === "manager" && <Typography variant="body2" sx={{ mt: 0.5 }}>Employee: {o.achievement || "—"} · self-rating {o.self_rating ?? "—"}</Typography>}
                <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ mt: 1 }}>
                  <RatingSelect scale={scale} value={draft.objectives[o.id]?.[field]} onChange={(v) => setObj(o.id, field, v)} />
                  {mode === "self"
                    ? <TextField size="small" fullWidth label="What did you achieve? (evidence)" value={draft.objectives[o.id]?.achievement || ""} onChange={(e) => setObj(o.id, "achievement", e.target.value)} />
                    : <TextField size="small" fullWidth label="Comment" value={draft.objectives[o.id]?.manager_comment || ""} onChange={(e) => setObj(o.id, "manager_comment", e.target.value)} />}
                </Stack>
              </Box>
            ))}
          </Stack>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>Competencies ({100 - a.objectives_weight}% of score)</Typography>
          <Stack spacing={1.5} sx={{ mb: 3 }}>
            {a.competency_ratings.map((c: R) => (
              <Stack key={c.id} direction={{ xs: "column", sm: "row" }} spacing={1.5} alignItems={{ sm: "center" }}>
                <Box flex={1}><b>{c.name}</b> <small>· {c.category}</small><br /><small>{c.description}</small>
                  {mode === "manager" && <><br /><small>Self-rating: {c.self_rating ?? "—"}</small></>}</Box>
                <RatingSelect scale={scale} value={draft.competencies[c.id]?.[field]} onChange={(v) => setComp(c.id, field, v)} />
              </Stack>
            ))}
          </Stack>
          {mode === "self"
            ? <TextField fullWidth multiline minRows={3} label="Overall comments, challenges and support needed" value={draft.text.self_comments || ""} onChange={(e) => setDraft({ ...draft, text: { ...draft.text, self_comments: e.target.value } })} />
            : <Stack spacing={2}>
              {a.self_comments && <Field label="Employee's comments" value={a.self_comments} />}
              <TextField fullWidth multiline minRows={3} label="Overall comments" value={draft.text.manager_comments || ""} onChange={(e) => setDraft({ ...draft, text: { ...draft.text, manager_comments: e.target.value } })} />
              <TextField fullWidth multiline minRows={2} label="Development needs and training for next period" value={draft.text.development_needs || ""} onChange={(e) => setDraft({ ...draft, text: { ...draft.text, development_needs: e.target.value } })} />
            </Stack>}
          <Stack direction="row" spacing={1} sx={{ mt: 2 }}>
            <Button onClick={() => save(false)}>Save draft</Button>
            <Button variant="contained" onClick={() => save(true)}>Submit {mode === "self" ? "self-assessment" : "review"}</Button>
          </Stack>
        </Section>
      )}

      {!mode && (
        <Section title={`Competencies (${100 - a.objectives_weight}% of score)`} dense>
          <DataTable dense rows={a.competency_ratings} columns={[
            { key: "name", label: "Competency", render: (c) => <><b>{c.name}</b><br /><small>{c.category}</small></> },
            { key: "self_rating", label: "Self", render: (c) => c.self_rating ?? "—" },
            ...(showManager ? [{ key: "manager_rating", label: "Manager", render: (c: R) => c.manager_rating ?? "—" }] : []),
          ]} />
        </Section>
      )}

      {(a.self_comments || (showManager && (a.manager_comments || a.development_needs)) || a.midyear_comments || a.employee_comments) && !mode && (
        <Section title="Comments">
          <Stack spacing={1.5}>
            {a.midyear_comments && <Field label="Mid-year check-in" value={a.midyear_comments} />}
            {a.self_comments && <Field label="Employee" value={a.self_comments} />}
            {showManager && a.manager_comments && <Field label="Manager" value={a.manager_comments} />}
            {showManager && a.development_needs && <Field label="Development needs" value={a.development_needs} />}
            {a.employee_comments && <Field label={`Employee acknowledgment (${a.employee_agrees ? "agrees" : "disagrees"})`} value={a.employee_comments} />}
          </Stack>
        </Section>
      )}

      {a.include_360 && (
        <Section title="360 feedback">
          {(a.feedback_requests || []).length > 0 && <Typography variant="body2" sx={{ mb: 1 }}>
            Asked: {a.feedback_requests.map((f: R) => `${f.respondent} (${f.relationship}, ${f.status})`).join("; ")}</Typography>}
          {fb.data?.available_after_review ? <Alert severity="info">Combined feedback is shared with you when your review is released.</Alert>
            : fb.data && !fb.data.sufficient ? <Alert severity="info">{fb.data.received} of {fb.data.requested} responses. Results are shown only once at least {fb.data.threshold} people have responded, to protect anonymity.</Alert>
            : fb.data?.sufficient ? <>
              <DataTable dense rows={fb.data.competencies} rowKey={(r) => r.competency} columns={[{ key: "competency", label: "Competency" },
                { key: "average", label: "Average", align: "right" }, { key: "responses", label: "Responses", align: "right" }]} />
              {fb.data.strengths.length > 0 && <Field label="Strengths" value={<ul>{fb.data.strengths.map((s: string, i: number) => <li key={i}>{s}</li>)}</ul>} />}
              {fb.data.improvements.length > 0 && <Field label="Could improve" value={<ul>{fb.data.improvements.map((s: string, i: number) => <li key={i}>{s}</li>)}</ul>} />}
            </> : null}
        </Section>
      )}

      <FormDialog open={!!objDialog} title={objDialog?.id ? "Edit objective" : "Add objective"} onClose={() => setObjDialog(null)} initial={objDialog || undefined}
        fields={[{ name: "title", label: "Objective", required: true }, { name: "description", label: "Details", type: "textarea" },
          { name: "measure", label: "Measure / KPI", required: true, width: 8 }, { name: "target", label: "Target", width: 4 },
          { name: "weight", label: "Weight (%)", type: "number", required: true, width: 4 }, { name: "due_date", label: "Due", type: "date", width: 4 },
          { name: "goal", label: "Aligned goal", type: "select", width: 4, options: (goals.data || []).map((g) => ({ value: g.id, label: `${g.title} (${g.department_name})` })) }]}
        onSubmit={async (d) => {
          const body = { ...(d as R), appraisal: a.id };
          if (objDialog?.id) await api.patch(`/performance/objectives/${objDialog.id}/`, body); else await api.post("/performance/objectives/", body);
          toast.ok("Saved."); refresh();
        }} />
      <ConfirmDialog open={dialog === "submitObj"} title="Submit objectives?" onClose={() => setDialog(null)} confirmLabel="Submit"
        message={a.role === "reviewer" ? "As the reviewer, submitting agrees the objectives immediately." : "Your supervisor will review and agree them, or return them with comments."}
        onConfirm={async () => { await post(`/performance/appraisals/${id}/submit-objectives/`); toast.ok("Objectives submitted."); refresh(); }} />
      <FormDialog open={dialog === "midyear"} title="Mid-year check-in" onClose={() => setDialog(null)}
        initial={Object.fromEntries([...a.objectives.flatMap((o: R) => [[`s${o.id}`, o.midyear_status || "on_track"], [`c${o.id}`, o.midyear_comment]]), ["comments", a.midyear_comments]])}
        fields={[...a.objectives.flatMap((o: R) => [
          { name: `s${o.id}`, label: o.title, type: "select" as const, options: PROGRESS, width: 4 as const },
          { name: `c${o.id}`, label: "Progress note", width: 8 as const }]), { name: "comments", label: "Overall discussion notes", type: "textarea" as const }]}
        onSubmit={async (d) => {
          const v = d as R;
          await post(`/performance/appraisals/${id}/midyear/`, { comments: v.comments, objectives: a.objectives.map((o: R) => ({ id: o.id, midyear_status: v[`s${o.id}`], midyear_comment: v[`c${o.id}`] || "" })) });
          toast.ok("Check-in recorded."); refresh();
        }} />
      <FormDialog open={dialog === "calibrate"} title="Calibrate final rating" onClose={() => setDialog(null)} initial={{ rating: a.final_rating, reason: a.calibration_reason }}
        intro={<Alert severity="info">Manager's rating: {ratingLabel(scale, a.manager_rating)} (score {a.overall_score}). Changes need a reason and are audited.</Alert>}
        fields={[{ name: "rating", label: "Final rating", type: "select", required: true, options: scale.map((l) => ({ value: l.value, label: `${l.value} – ${l.label}` })) },
          { name: "reason", label: "Reason (required if changed)", type: "textarea" }]}
        onSubmit={async (d) => { await post(`/performance/appraisals/${id}/calibrate/`, d); toast.ok("Rating calibrated."); refresh(); }} />
      <FormDialog open={dialog === "ack"} title="Acknowledge your appraisal" onClose={() => setDialog(null)} initial={{ agrees: "true", comments: "" }}
        fields={[{ name: "agrees", label: "Do you agree with the review?", type: "select", required: true, options: [{ value: "true", label: "Yes, I agree" }, { value: "false", label: "No, I disagree" }] },
          { name: "comments", label: "Your comments (required if you disagree)", type: "textarea" }]}
        onSubmit={async (d) => { await post(`/performance/appraisals/${id}/acknowledge/`, { ...(d as R), agrees: (d as R).agrees === "true" }); toast.ok("Acknowledged."); refresh(); }} />
      <FormDialog open={dialog === "feedback"} title="Request 360 feedback" onClose={() => setDialog(null)} initial={{ users: [], relationship: "peer" }}
        intro={<Alert severity="info">Choose 3–8 colleagues. Individual responses are never shown; combined results appear once at least 3 have responded.</Alert>}
        fields={[{ name: "users", label: "Colleagues", type: "multiref", ref: "/users/lookup/", refLabel: (u) => String(u.full_name || u.username), required: true },
          { name: "relationship", label: "Relationship", type: "select", options: [["peer", "Peer"], ["direct_report", "Direct report"], ["internal_customer", "Internal customer"], ["other", "Other"]].map(([value, label]) => ({ value, label })) }]}
        onSubmit={async (d) => {
          const v = d as R;
          const r = await post<R>(`/performance/appraisals/${id}/request-feedback/`, { respondents: (v.users || []).map((u: number) => ({ user: u, relationship: v.relationship })) });
          toast.ok(`${r.requested} request(s) sent.`); refresh();
        }} />
      <Typography variant="caption" color="text.secondary">Template: {a.template_name} · deadlines: objectives {fmtDate(a.cycle_deadlines?.goal_setting)}, self-assessment {fmtDate(a.cycle_deadlines?.self_review)}, manager review {fmtDate(a.cycle_deadlines?.manager_review)}</Typography>
    </>
  );
}

