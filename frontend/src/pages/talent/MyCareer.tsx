import { Alert, Button, Card, CardContent, Chip, Grid2 as Grid, Stack, Typography } from "@mui/material";
import { useState } from "react";
import { api } from "../../api/client";
import { useApi, useInvalidate } from "../../api/hooks";
import { useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { DataTable } from "../../components/DataTable";
import { Field, PageHeader, Section } from "../../components/PageHeader";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export default function MyCareer() {
  const q = useApi<R>("/talent/me/");
  const paths = useApi<R[]>("/talent/career-paths/");
  const [editing, setEditing] = useState(false);
  const toast = useToast();
  const inv = useInvalidate();
  const d = q.data;
  const p = d?.profile || {};
  return (
    <>
      <PageHeader title="My career" subtitle="Your aspirations, skills and the requirements for your next role."
        actions={<Button variant="contained" onClick={() => setEditing(true)}>Update my career profile</Button>} />
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 5 }}>
          <Section title="My profile">
            <Stack spacing={1}>
              <Field label="Years in current role" value={d?.years_in_role ?? "—"} />
              <Field label="Career aspirations" value={p.aspirations || "Not filled in yet"} />
              <Field label="Skills" value={(p.skills || []).length ? <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>{p.skills.map((s: string) => <Chip key={s} size="small" label={s} />)}</Stack> : "—"} />
              <Field label="Mobility" value={`${p.willing_to_relocate ? "Willing to relocate" : "Prefers current location"} · ${p.open_to_lateral_moves ? "open to lateral moves" : "not seeking lateral moves"}`} />
            </Stack>
          </Section>
        </Grid>
        <Grid size={{ xs: 12, md: 7 }}>
          <Section title="Next steps from your role">
            {(d?.eligibility || []).length === 0 && <Typography color="text.secondary">No career paths are published from your current role yet. Speak to HR about progression.</Typography>}
            {(d?.eligibility || []).map((e: R) => (
              <Card key={e.path} variant="outlined" sx={{ mb: 1 }}><CardContent>
                <Stack direction="row" justifyContent="space-between"><Typography fontWeight={600}>{e.to}</Typography>
                  <Chip size="small" color={e.eligible ? "success" : "default"} label={e.eligible ? "Requirements met" : `${e.gaps.length} to go`} /></Stack>
                {e.gaps.map((g: string) => <Typography key={g} variant="body2">• {g}</Typography>)}
                {e.qualification_to_verify && <Typography variant="caption" color="text.secondary">Also required (verified by HR): {e.qualification_to_verify}</Typography>}
              </CardContent></Card>))}
            <Alert severity="info" sx={{ mt: 1 }}>Meeting the requirements makes you eligible to be considered; promotions also depend on approved vacancies.</Alert>
          </Section>
        </Grid>
      </Grid>
      <Section title="All published career paths" dense>
        <DataTable dense rows={paths.data || []} emptyTitle="No career paths published" columns={[
          { key: "from_title_name", label: "From" }, { key: "to_title_name", label: "To" },
          { key: "min_years_in_role", label: "Years in role", align: "right", render: (r) => Number(r.min_years_in_role) },
          { key: "min_rating", label: "Min rating", align: "right" }, { key: "required_qualification", label: "Qualification" }]} />
      </Section>
      <FormDialog open={editing} title="My career profile" onClose={() => setEditing(false)} initial={{ ...p, preferred_roles: p.preferred_roles || [] }}
        fields={[{ name: "aspirations", label: "Where would you like your career to go?", type: "textarea" },
          { name: "preferred_roles", label: "Roles that interest me", type: "multiref", ref: "/org/job-titles/" },
          { name: "skills", label: "Skills (JSON list)", type: "json", helper: '["Phlebotomy", "Excel", "Team leadership"]' },
          { name: "willing_to_relocate", label: "Willing to relocate (e.g. Kumasi branch)", type: "checkbox", width: 6 },
          { name: "open_to_lateral_moves", label: "Open to lateral moves", type: "checkbox", width: 6 }]}
        onSubmit={async (v) => { await api.patch("/talent/me/", v); toast.ok("Saved."); inv("/talent/"); }} />
    </>
  );
}
