import Download from "@mui/icons-material/Download";
import Edit from "@mui/icons-material/Edit";
import { Avatar, Button, Card, CardContent, Grid2 as Grid, Stack, Tab, Tabs, Typography } from "@mui/material";
import { useState } from "react";
import { download } from "../../api/client";
import { post, useApi, useInvalidate } from "../../api/hooks";
import { ErrorAlert, Loading, StatusChip, useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { Field, PageHeader, Section } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtDate, titleCase } from "../../utils";

type P = Record<string, unknown> & { editable_fields: string[] };

export default function Profile() {
  const { data, isLoading, error } = useApi<P>("/me/profile/");
  const [tab, setTab] = useState(0);
  const [editing, setEditing] = useState(false);
  const toast = useToast();
  const inv = useInvalidate();
  if (isLoading) return <Loading />;
  if (error || !data) return <ErrorAlert error={error} />;
  const p = data;
  const str = (k: string) => (p[k] as string) || "";
  return (
    <>
      <PageHeader title="My profile" subtitle="Your employment record. Corrections to personal details are reviewed by HR before they take effect."
        actions={<>
          <Button startIcon={<Edit />} variant="contained" onClick={() => setEditing(true)}>Request a correction</Button>
          <Button startIcon={<Download />} onClick={() => download("/me/data-export/")}>Download my data</Button>
        </>} />
      <Card sx={{ mb: 2 }}>
        <CardContent>
          <Stack direction="row" spacing={2} alignItems="center">
            <Avatar src={str("photo") || undefined} sx={{ width: 64, height: 64, bgcolor: "primary.main" }}>{str("first_name")[0]}</Avatar>
            <Stack>
              <Typography variant="h6">{str("full_name")}</Typography>
              <Typography color="text.secondary">{str("job_title_name")} · {str("department_name")} · {str("staff_number")}</Typography>
              <Stack direction="row" spacing={1} mt={0.5}><StatusChip value={str("status")} /><Typography variant="body2">{String(p.years_of_service)} years of service</Typography></Stack>
            </Stack>
          </Stack>
        </CardContent>
      </Card>
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }} variant="scrollable">
        <Tab label="Personal & employment" /><Tab label="Emergency contacts" /><Tab label="Beneficiaries / next of kin" />
        <Tab label="Change requests" />
      </Tabs>
      {tab === 0 && (
        <Grid container spacing={2}>
          <Grid size={{ xs: 12, md: 6 }}>
            <Section title="Personal">
              <Grid container spacing={2}>
                {[["Title", titleCase(str("title"))], ["Gender", titleCase(str("gender"))], ["Date of birth", fmtDate(str("date_of_birth"))],
                  ["Marital status", titleCase(str("marital_status"))], ["Ghana Card", str("ghana_card_no")], ["SSNIT No", str("ssnit_number")],
                  ["TIN", str("tin")], ["Phone", str("phone")], ["Personal email", str("personal_email")],
                  ["Residential address", str("residential_address")], ["Digital address (GPS)", str("digital_address")], ["Hometown", str("hometown")]]
                  .map(([l, v]) => <Grid key={l} size={6}><Field label={l} value={v} /></Grid>)}
              </Grid>
            </Section>
          </Grid>
          <Grid size={{ xs: 12, md: 6 }}>
            <Section title="Employment">
              <Grid container spacing={2}>
                {[["Staff number", str("staff_number")], ["Job title", str("job_title_name")], ["Department", str("department_name")],
                  ["Grade", str("grade_code")], ["Supervisor", str("supervisor_name")], ["Employment type", titleCase(str("employment_type"))],
                  ["Hire date", fmtDate(str("hire_date"))], ["Confirmation date", fmtDate(str("confirmation_date"))],
                  ["Contract end", fmtDate(str("contract_end_date"))], ["Work email", str("work_email")]]
                  .map(([l, v]) => <Grid key={l} size={6}><Field label={l} value={v} /></Grid>)}
              </Grid>
            </Section>
            <Section title="Salary payment">
              {(p.bank_accounts as Record<string, string>[]).map((b, i) => (
                <Typography key={i} variant="body2">{b.bank_name} {b.account} {b.is_primary && "(primary)"}</Typography>
              ))}
              <Typography variant="caption" color="text.secondary">To change bank details, contact the Payroll Unit with a bank letter.</Typography>
            </Section>
          </Grid>
        </Grid>
      )}
      {tab === 1 && (
        <Card><ResourcePage embedded title="Emergency contact" url="/me/emergency-contacts/" searchable={false} canDelete
          columns={[{ key: "name", label: "Name" }, { key: "relationship", label: "Relationship" }, { key: "phone", label: "Phone" },
            { key: "is_primary", label: "Primary", render: (r) => (r.is_primary ? "Yes" : "") }]}
          fields={[{ name: "name", label: "Full name", required: true }, { name: "relationship", label: "Relationship", required: true, width: 6 },
            { name: "phone", label: "Phone", required: true, width: 6 }, { name: "alt_phone", label: "Alternative phone", width: 6 },
            { name: "address", label: "Address", width: 6 }, { name: "is_primary", label: "Primary contact", type: "checkbox" }]} /></Card>
      )}
      {tab === 2 && (
        <Card><ResourcePage embedded title="Beneficiary" url="/me/beneficiaries/" searchable={false} canDelete
          columns={[{ key: "name", label: "Name" }, { key: "relationship", label: "Relationship" }, { key: "percentage", label: "Share %" },
            { key: "is_next_of_kin", label: "Next of kin", render: (r) => (r.is_next_of_kin ? "Yes" : "") }]}
          fields={[{ name: "name", label: "Full name", required: true }, { name: "relationship", label: "Relationship", required: true, width: 6 },
            { name: "phone", label: "Phone", width: 6 }, { name: "date_of_birth", label: "Date of birth", type: "date", width: 6 },
            { name: "percentage", label: "Share (%)", type: "number", width: 6 }, { name: "is_next_of_kin", label: "Next of kin", type: "checkbox" }]} /></Card>
      )}
      {tab === 3 && (
        <Card><ResourcePage embedded title="Change requests" url="/me/change-requests/" searchable={false}
          columns={[{ key: "created_at", label: "Submitted", render: (r) => fmtDate(r.created_at as string) },
            { key: "changes", label: "Changes", render: (r) => Object.entries(r.changes as Record<string, string>).map(([k, v]) => `${titleCase(k)} → ${v}`).join("; ") },
            { key: "status", label: "Status", render: (r) => <StatusChip value={r.status as string} /> }]} /></Card>
      )}
      <FormDialog open={editing} onClose={() => setEditing(false)} title="Request a correction" submitLabel="Submit for approval"
        intro="Only change the fields that are wrong. HR will verify and may ask for supporting documents."
        initial={Object.fromEntries(p.editable_fields.map((f) => [f, p[f] ?? ""]))}
        fields={[...p.editable_fields.map((f) => ({ name: f, label: titleCase(f), type: f === "date_of_birth" ? "date" as const : "text" as const, width: 6 as const })),
          { name: "_reason", label: "Reason for change", type: "textarea" as const }]}
        onSubmit={async (vals) => {
          const v = vals as Record<string, unknown>;
          const changes: Record<string, unknown> = {};
          for (const f of p.editable_fields) if ((v[f] ?? "") !== (p[f] ?? "")) changes[f] = v[f];
          if (!Object.keys(changes).length) throw new Error("You haven't changed anything.");
          await post("/me/change-requests/", { changes, reason: v._reason });
          toast.ok("Change request submitted to HR.");
          inv("/me/");
        }} />
    </>
  );
}
