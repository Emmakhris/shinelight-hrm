import Description from "@mui/icons-material/Description";
import Edit from "@mui/icons-material/Edit";
import ExitToApp from "@mui/icons-material/ExitToApp";
import ManageAccounts from "@mui/icons-material/ManageAccounts";
import MoreVert from "@mui/icons-material/MoreVert";
import SwapHoriz from "@mui/icons-material/SwapHoriz";
import Upload from "@mui/icons-material/Upload";
import { Alert, Avatar, Box, Button, Card, CardContent, Grid2 as Grid, IconButton, Menu, MenuItem, Stack, Tab, Tabs,
  Typography } from "@mui/material";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { api, download } from "../../api/client";
import { post, useApi, useInvalidate, useList } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { DataTable } from "../../components/DataTable";
import { ErrorAlert, Loading, StatusChip, useToast } from "../../components/Feedback";
import { FormDialog, type FieldDef } from "../../components/FormDialog";
import { Field, PageHeader, Section } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";
import SendForSignature from "../../components/SendForSignature";
import { NewRequestDialog } from "../helpdesk/HelpDesk";
import { TotalRewards } from "../compensation/MyBenefits";
import { fmtDate, fmtMoney, titleCase } from "../../utils";
import { personalFields, personnelActionFields } from "./fields";

type E = Record<string, unknown>;

export default function EmployeeDetail() {
  const { id } = useParams();
  const { can, feature } = useAuth();
  const toast = useToast();
  const inv = useInvalidate();
  const { data: e, isLoading, error } = useApi<E>(`/employees/${id}/`);
  const [tab, setTab] = useState("overview");
  const [dialog, setDialog] = useState<string | null>(null);
  const [menu, setMenu] = useState<HTMLElement | null>(null);
  const history = useList<E>(tab === "history" ? `/employees/${id}/history/` : null);
  const balances = useApi<E[]>(tab === "leave" ? "/leave/requests/balances/" : null, { employee: id });
  const templates = useList<E>(dialog === "letter" ? "/documents/templates/" : null);
  if (isLoading) return <Loading />;
  if (error || !e) return <ErrorAlert error={error} />;
  const s = (k: string) => (e[k] as string) || "";
  const refresh = () => inv(`/employees`, "/documents", "/leave");
  const exited = e.status === "exited";

  const actions = (
    <>
      {can("employees.change") && !exited && <Button variant="contained" startIcon={<SwapHoriz />} onClick={() => setDialog("action")}>Personnel action</Button>}
      {can("employees.change") && <Button startIcon={<Edit />} onClick={() => setDialog("edit")}>Edit details</Button>}
      <IconButton onClick={(ev) => setMenu(ev.currentTarget)} aria-label="More actions"><MoreVert /></IconButton>
      <Menu anchorEl={menu} open={!!menu} onClose={() => setMenu(null)} onClick={() => setMenu(null)}>
        {e.status === "probation" && can("employees.change") && <MenuItem onClick={() => setDialog("confirm")}>Confirm appointment</MenuItem>}
        {e.status === "probation" && can("employees.change") && <MenuItem onClick={() => setDialog("extend")}>Extend probation</MenuItem>}
        {can("servicedesk.agent") && <MenuItem onClick={() => setDialog("ticket")}>Log help desk request</MenuItem>}
        {can("documents.generate") && <MenuItem onClick={() => setDialog("letter")}><Description fontSize="small" sx={{ mr: 1 }} />Generate letter</MenuItem>}
        {can("admin.users") && !e.has_account && !exited && <MenuItem onClick={() => setDialog("account")}><ManageAccounts fontSize="small" sx={{ mr: 1 }} />Create user account</MenuItem>}
        {can("employees.change") && !exited && <MenuItem onClick={() => setDialog("separate")}><ExitToApp fontSize="small" sx={{ mr: 1 }} />Record separation / exit</MenuItem>}
        {can("employees.create") && exited && <MenuItem onClick={() => setDialog("rehire")}>Rehire</MenuItem>}
      </Menu>
    </>
  );

  const child = (title: string, url: string, columns: { key: string; label: string; render?: (r: E) => React.ReactNode }[],
    fields: FieldDef[], extra?: Partial<React.ComponentProps<typeof ResourcePage>>) => (
    <Card><ResourcePage embedded title={title} url={url} params={{ employee: id }} searchable={false} canDelete
      writePerm="employees.change" columns={columns} fields={fields.concat({ name: "employee", label: "", hidden: () => true })}
      defaults={{ employee: Number(id) }} toInitial={(r) => ({ ...r, employee: Number(id) })} createLabel={`Add ${title.toLowerCase()}`} {...extra} /></Card>
  );

  return (
    <>
      <PageHeader title={s("full_name")} crumbs={[{ label: "Employees", to: "/employees" }, { label: s("staff_number") }]} actions={actions} />
      <Card sx={{ mb: 2 }}>
        <CardContent>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems={{ sm: "center" }}>
            <Box position="relative">
              <Avatar src={s("photo") || undefined} sx={{ width: 72, height: 72, bgcolor: "primary.main", fontSize: 28 }}>{s("first_name")[0]}</Avatar>
              {can("employees.change") && (
                <IconButton component="label" size="small" sx={{ position: "absolute", bottom: -6, right: -6, bgcolor: "#fff", border: "1px solid #ddd" }}>
                  <Upload fontSize="inherit" />
                  <input hidden type="file" accept="image/*" onChange={async (ev) => {
                    const f = ev.target.files?.[0]; if (!f) return;
                    const fd = new FormData(); fd.append("photo", f);
                    await api.patch(`/employees/${id}/`, fd); refresh();
                  }} />
                </IconButton>
              )}
            </Box>
            <Box flex={1}>
              <Typography variant="h6">{s("job_title_name") || "—"}</Typography>
              <Typography color="text.secondary">{s("department_name")} · {s("branch_name")} · Grade {s("grade_code") || "—"}</Typography>
              <Stack direction="row" spacing={1} mt={0.5} alignItems="center">
                <StatusChip value={s("status")} />
                <Typography variant="body2">{titleCase(s("employment_type"))} · {String(e.years_of_service)} yrs service · Reports to {s("supervisor_name") || "—"}</Typography>
              </Stack>
            </Box>
            {e.basic_salary !== null && <Box textAlign="right"><Typography variant="caption" color="text.secondary">Basic salary</Typography>
              <Typography variant="h6">{fmtMoney(s("basic_salary"))}</Typography></Box>}
          </Stack>
        </CardContent>
      </Card>
      {exited && <Alert severity="info" sx={{ mb: 2 }}>Exited on {fmtDate(s("exit_date"))} ({titleCase(s("exit_reason"))}). Rehire eligible: {e.rehire_eligible ? "Yes" : "No"}.</Alert>}
      <Tabs value={tab} onChange={(_, v) => setTab(v)} variant="scrollable" sx={{ mb: 2 }}>
        {[["overview", "Overview"], ["history", "Employment history"], ["contracts", "Contracts"], ["documents", "Documents"],
          ["bank", "Bank & payment"], ["contacts", "Emergency & beneficiaries"], ["qualifications", "Qualifications"],
          ["leave", "Leave"], ["concurrent", "Acting / concurrent roles"], ...(can("employees.view_salary") ? [["rewards", "Total rewards"]] : [])].map(([v, l]) => <Tab key={v} value={v} label={l} />)}
      </Tabs>

      {tab === "overview" && (
        <Grid container spacing={2}>
          <Grid size={{ xs: 12, md: 6 }}>
            <Section title="Personal information">
              <Grid container spacing={2}>
                {[["Gender", titleCase(s("gender"))], ["Date of birth", fmtDate(s("date_of_birth"))], ["Marital status", titleCase(s("marital_status"))],
                  ["Nationality", s("nationality")], ["Ghana Card", s("ghana_card_no")], ["SSNIT", s("ssnit_number")], ["TIN", s("tin")],
                  ["Phone", s("phone")], ["Work email", s("work_email")], ["Personal email", s("personal_email")],
                  ["Address", s("residential_address")], ["GPS address", s("digital_address")]].map(([l, v]) => <Grid key={l} size={6}><Field label={l} value={v} /></Grid>)}
              </Grid>
            </Section>
          </Grid>
          <Grid size={{ xs: 12, md: 6 }}>
            <Section title="Employment">
              <Grid container spacing={2}>
                {[["Staff number", s("staff_number")], ["Position", s("position_code")], ["Category", s("category_name")], ["Location", s("location_name")],
                  ["Hire date", fmtDate(s("hire_date"))], ["Original hire date", fmtDate(s("original_hire_date"))],
                  ["Probation ends", fmtDate(s("probation_end_date"))], ["Confirmed", fmtDate(s("confirmation_date"))],
                  ["Contract ends", fmtDate(s("contract_end_date"))], ["Retirement date", fmtDate(s("retirement_date"))],
                  ["User account", e.has_account ? "Yes" : "No"]].map(([l, v]) => <Grid key={l} size={6}><Field label={l} value={v} /></Grid>)}
              </Grid>
            </Section>
          </Grid>
        </Grid>
      )}

      {tab === "history" && (
        <Card>
          <DataTable dense loading={history.isLoading} rows={history.items} columns={[
            { key: "effective_from", label: "Effective", render: (r) => fmtDate(r.effective_from as string) },
            { key: "effective_to", label: "Until", render: (r) => r.effective_to ? fmtDate(r.effective_to as string) : (r.is_current ? "Current" : "Future-dated") },
            { key: "event_label", label: "Action" }, { key: "job_title_name", label: "Job title" }, { key: "department_name", label: "Department" },
            { key: "grade_code", label: "Grade" }, { key: "basic_salary", label: "Basic", align: "right", render: (r) => r.basic_salary === null ? "—" : fmtMoney(r.basic_salary as string) },
            { key: "status", label: "Status", render: (r) => titleCase(r.status as string) }, { key: "reason", label: "Reason" },
            { key: "approved_by_name", label: "By" },
          ]} />
        </Card>
      )}

      {tab === "contracts" && child("Contract", "/employees/contracts/", [
        { key: "contract_type_label", label: "Type" }, { key: "reference", label: "Reference" },
        { key: "start_date", label: "Start", render: (r) => fmtDate(r.start_date as string) },
        { key: "end_date", label: "End", render: (r) => fmtDate(r.end_date as string) },
        { key: "status", label: "Status", render: (r) => <StatusChip value={r.status as string} /> }], [
        { name: "contract_type", label: "Type", type: "select", required: true, options: ["permanent", "probation", "fixed_term", "temporary", "consultancy", "national_service", "internship"].map((v) => ({ value: v, label: titleCase(v) })) },
        { name: "reference", label: "Reference", width: 6 }, { name: "notice_period_days", label: "Notice period (days)", type: "number", width: 6 },
        { name: "start_date", label: "Start", type: "date", required: true, width: 6 }, { name: "end_date", label: "End", type: "date", width: 6 },
        { name: "status", label: "Status", type: "select", options: ["active", "expired", "renewed", "terminated"].map((v) => ({ value: v, label: titleCase(v) })) },
        { name: "notes", label: "Notes", type: "textarea" }])}

      {tab === "documents" && (
        <Card><ResourcePage embedded title="Document" url="/documents/" params={{ employee: id }} writePerm="documents.upload" canDelete
          columns={[{ key: "title", label: "Title" }, { key: "category_name", label: "Category" },
            { key: "confidentiality", label: "Access", render: (r) => titleCase(r.confidentiality as string) },
            { key: "expiry_date", label: "Expires", render: (r) => r.is_expired ? <StatusChip value="expired" label={fmtDate(r.expiry_date as string)} /> : fmtDate(r.expiry_date as string) },
            { key: "current_version", label: "Ver." },
            { key: "_dl", label: "", render: (r) => (r.current_version as number) > 0 && <>
              <Button size="small" onClick={() => download(`/documents/${r.id}/download/`)}>Open</Button>
              {can("documents.upload") && <SendForSignature doc={r} />}</> }]}
          fields={[{ name: "category", label: "Category", type: "ref", ref: "/documents/categories/", required: true },
            { name: "title", label: "Title", required: true }, { name: "file", label: "Choose file", type: "file" },
            { name: "issue_date", label: "Issue date", type: "date", width: 6 }, { name: "expiry_date", label: "Expiry date", type: "date", width: 6 },
            { name: "reference_no", label: "Reference no", width: 6 },
            { name: "confidentiality", label: "Confidentiality", type: "select", width: 6, options: [{ value: "internal", label: "Internal" }, { value: "confidential", label: "Confidential (HR)" }, { value: "restricted", label: "Restricted" }] },
            { name: "visible_to_employee", label: "Visible to the employee", type: "checkbox" },
            { name: "employee", label: "", hidden: () => true }]}
          defaults={{ employee: Number(id), visible_to_employee: true }} createLabel="Upload document" /></Card>
      )}

      {tab === "bank" && (
        <>
          {child("Bank account", "/employees/bank-accounts/", [
            { key: "payment_method", label: "Method", render: (r) => titleCase(r.payment_method as string) },
            { key: "bank_name", label: "Bank / network", render: (r) => (r.bank_name || r.momo_network) as string },
            { key: "branch_code", label: "Sort code" }, { key: "account_number", label: "Account", render: (r) => (r.account_number || r.momo_number) as string },
            { key: "account_name", label: "Account name" }, { key: "is_primary", label: "Primary", render: (r) => (r.is_primary ? "Yes" : "") }], [
            { name: "payment_method", label: "Method", type: "select", required: true, options: [{ value: "bank", label: "Bank transfer" }, { value: "momo", label: "Mobile money" }, { value: "cash", label: "Cash / cheque" }] },
            { name: "bank_name", label: "Bank", width: 6, hidden: (v) => v.payment_method !== "bank" },
            { name: "bank_code", label: "Bank code", width: 3, hidden: (v) => v.payment_method !== "bank" },
            { name: "branch_code", label: "Sort code", width: 3, hidden: (v) => v.payment_method !== "bank" },
            { name: "account_number", label: "Account number", width: 6, hidden: (v) => v.payment_method !== "bank" },
            { name: "account_name", label: "Account name", width: 6 },
            { name: "momo_network", label: "Network", type: "select", width: 6, hidden: (v) => v.payment_method !== "momo", options: [{ value: "mtn", label: "MTN MoMo" }, { value: "telecel", label: "Telecel Cash" }, { value: "at", label: "AT Money" }] },
            { name: "momo_number", label: "Wallet number", width: 6, hidden: (v) => v.payment_method !== "momo" },
            { name: "is_primary", label: "Primary account for salary", type: "checkbox" }], { writePerm: ["payroll.prepare", "employees.change"], defaults: { employee: Number(id), payment_method: "bank", is_primary: true } })}
          {feature("payroll") && can("payroll.view") && (
            <Section title="Recurring pay elements">
              <ResourcePage embedded title="Pay element" url="/payroll/employee-elements/" params={{ employee: id }} searchable={false} canDelete writePerm="payroll.prepare"
                columns={[{ key: "element_name", label: "Element" }, { key: "element_type", label: "Type", render: (r) => titleCase(r.element_type as string) },
                  { key: "amount", label: "Amount", render: (r) => r.amount === null ? (r.percent ? `${r.percent}%` : "default") : fmtMoney(r.amount as string) },
                  { key: "start_date", label: "From", render: (r) => fmtDate(r.start_date as string) }, { key: "end_date", label: "To", render: (r) => fmtDate(r.end_date as string) }]}
                fields={[{ name: "element", label: "Pay element", type: "ref", ref: "/payroll/elements/", refLabel: (x) => `${x.code} — ${x.name}`, required: true },
                  { name: "amount", label: "Amount (GHS)", type: "number", width: 4 }, { name: "percent", label: "Percent", type: "number", width: 4 },
                  { name: "quantity", label: "Quantity", type: "number", width: 4 },
                  { name: "start_date", label: "Start date", type: "date", required: true, width: 6 }, { name: "end_date", label: "End date", type: "date", width: 6 },
                  { name: "note", label: "Note" }, { name: "employee", label: "", hidden: () => true }]}
                defaults={{ employee: Number(id) }} createLabel="Add element" />
            </Section>
          )}
        </>
      )}

      {tab === "contacts" && (
        <Stack spacing={2}>
          {child("Emergency contact", "/employees/emergency-contacts/", [{ key: "name", label: "Name" }, { key: "relationship", label: "Relationship" }, { key: "phone", label: "Phone" }],
            [{ name: "name", label: "Name", required: true }, { name: "relationship", label: "Relationship", required: true, width: 6 },
              { name: "phone", label: "Phone", required: true, width: 6 }, { name: "address", label: "Address" }, { name: "is_primary", label: "Primary", type: "checkbox" }])}
          {child("Beneficiary", "/employees/beneficiaries/", [{ key: "name", label: "Name" }, { key: "relationship", label: "Relationship" }, { key: "percentage", label: "Share %" }],
            [{ name: "name", label: "Name", required: true }, { name: "relationship", label: "Relationship", required: true, width: 6 },
              { name: "percentage", label: "Share %", type: "number", width: 6 }, { name: "phone", label: "Phone", width: 6 },
              { name: "date_of_birth", label: "Date of birth", type: "date", width: 6 }, { name: "is_next_of_kin", label: "Next of kin", type: "checkbox" }])}
        </Stack>
      )}

      {tab === "qualifications" && child("Qualification", "/employees/qualifications/", [
        { key: "level", label: "Level", render: (r) => titleCase(r.level as string) }, { key: "title", label: "Qualification" },
        { key: "institution", label: "Institution" }, { key: "year_obtained", label: "Year" }, { key: "verified", label: "Verified", render: (r) => (r.verified ? "Yes" : "No") }], [
        { name: "level", label: "Level", type: "select", required: true, options: ["shs", "certificate", "diploma", "bachelor", "master", "doctorate", "professional", "other"].map((v) => ({ value: v, label: titleCase(v) })) },
        { name: "title", label: "Qualification", required: true }, { name: "institution", label: "Institution", required: true, width: 6 },
        { name: "field_of_study", label: "Field of study", width: 6 }, { name: "year_obtained", label: "Year", type: "number", width: 6 },
        { name: "grade", label: "Class / grade", width: 6 }, { name: "verified", label: "Verified with institution", type: "checkbox" }])}

      {tab === "concurrent" && child("Acting / concurrent role", "/employees/concurrent-assignments/", [
        { key: "position_label", label: "Position" }, { key: "assignment_type", label: "Type", render: (r) => titleCase(r.assignment_type as string) },
        { key: "start_date", label: "From", render: (r) => fmtDate(r.start_date as string) }, { key: "end_date", label: "To", render: (r) => fmtDate(r.end_date as string) },
        { key: "allowance_amount", label: "Allowance", render: (r) => fmtMoney(r.allowance_amount as string) }], [
        { name: "position", label: "Position", type: "ref", ref: "/org/positions/", refLabel: (p) => `${p.code} — ${p.job_title_name}`, required: true },
        { name: "assignment_type", label: "Type", type: "select", options: [{ value: "acting", label: "Acting" }, { value: "joint", label: "Joint" }, { value: "secondary", label: "Secondary" }] },
        { name: "start_date", label: "Start", type: "date", required: true, width: 6 }, { name: "end_date", label: "End", type: "date", width: 6 },
        { name: "allowance_amount", label: "Monthly allowance (GHS)", type: "number" }])}

      {tab === "leave" && (
        <>
          <Grid container spacing={2} sx={{ mb: 2 }}>
            {(balances.data || []).filter((b) => b.tracks_balance).map((b) => (
              <Grid key={b.leave_type as number} size={{ xs: 6, md: 3 }}>
                <Card><CardContent><Typography variant="body2" color="text.secondary">{b.leave_type_name as string}</Typography>
                  <Typography variant="h6">{Number(b.available)} days</Typography>
                  <Typography variant="caption">Taken {Number(b.taken)} · Pending {Number(b.pending)}</Typography></CardContent></Card>
              </Grid>
            ))}
          </Grid>
          <Card><ResourcePage embedded title="Leave" url="/leave/requests/" params={{ employee: id }} searchable={false}
            columns={[{ key: "leave_type_name", label: "Type" }, { key: "start_date", label: "From", render: (r) => fmtDate(r.start_date as string) },
              { key: "end_date", label: "To", render: (r) => fmtDate(r.end_date as string) }, { key: "days", label: "Days" },
              { key: "status", label: "Status", render: (r) => <StatusChip value={r.status as string} /> }]} /></Card>
        </>
      )}

      {tab === "rewards" && <TotalRewards employee={Number(id)} />}
      <NewRequestDialog open={dialog === "ticket"} onClose={() => setDialog(null)} employee={Number(id)} />
      {/* dialogs */}
      <FormDialog open={dialog === "edit"} onClose={() => setDialog(null)} title="Edit personal details" maxWidth="md" initial={e}
        fields={personalFields} onSubmit={async (d) => { await api.patch(`/employees/${id}/`, d); toast.ok("Saved."); refresh(); }} />
      <FormDialog open={dialog === "action"} onClose={() => setDialog(null)} title="Personnel action" maxWidth="md" fields={personnelActionFields}
        intro="Only fill the fields that change. A new effective-dated record is created; history is never overwritten."
        onSubmit={async (d) => {
          const data = Object.fromEntries(Object.entries(d as E).filter(([, v]) => v !== null && v !== ""));
          await post(`/employees/${id}/personnel_action/`, data); toast.ok("Personnel action recorded."); refresh();
        }} />
      <FormDialog open={dialog === "confirm"} onClose={() => setDialog(null)} title="Confirm appointment" submitLabel="Confirm"
        fields={[{ name: "effective_from", label: "Confirmation date", type: "date", required: true }, { name: "reason", label: "Remarks", type: "textarea" }]}
        onSubmit={async (d) => { await post(`/employees/${id}/confirm/`, d); toast.ok("Appointment confirmed."); refresh(); }} />
      <FormDialog open={dialog === "extend"} onClose={() => setDialog(null)} title="Extend probation"
        fields={[{ name: "new_end_date", label: "New probation end date", type: "date", required: true }, { name: "reason", label: "Reason", type: "textarea", required: true }]}
        onSubmit={async (d) => { await post(`/employees/${id}/extend_probation/`, d); toast.ok("Probation extended."); refresh(); }} />
      <FormDialog open={dialog === "separate"} onClose={() => setDialog(null)} title="Record separation" submitLabel="Record exit"
        intro="On the exit date the user account is disabled automatically. Run a final settlement payroll for terminal benefits."
        fields={[{ name: "exit_date", label: "Last working date", type: "date", required: true, width: 6 },
          { name: "reason", label: "Reason", type: "select", required: true, width: 6, options: ["resignation", "retirement", "contract_end", "termination", "dismissal", "redundancy", "death", "abandonment", "other"].map((v) => ({ value: v, label: titleCase(v) })) },
          { name: "notes", label: "Notes", type: "textarea" }, { name: "rehire_eligible", label: "Eligible for rehire", type: "checkbox" }]}
        initial={{ rehire_eligible: true }}
        onSubmit={async (d) => { await post(`/employees/${id}/separate/`, d); toast.ok("Separation recorded."); refresh(); }} />
      <FormDialog open={dialog === "rehire"} onClose={() => setDialog(null)} title="Rehire former employee"
        intro="The person's history is preserved and linked to the new employment record."
        fields={[{ name: "hire_date", label: "New hire date", type: "date", required: true },
          { name: "position", label: "Position", type: "ref", ref: "/org/positions/", refParams: { status: "approved" }, refLabel: (p) => `${p.code} — ${p.job_title_name} (${p.department_name})` },
          { name: "basic_salary", label: "Basic salary", type: "number" }]}
        onSubmit={async (d) => { const n = await post<{ id: number }>(`/employees/${id}/rehire/`, d); toast.ok("Rehired."); window.location.assign(`/employees/${n.id}`); }} />
      <FormDialog open={dialog === "account"} onClose={() => setDialog(null)} title="Create user account" submitLabel="Create account"
        intro="A temporary password is emailed to the employee's work email. The Employee role is assigned (plus Line Manager if they supervise staff)."
        fields={[{ name: "username", label: "Username (blank = from email)" }]}
        onSubmit={async (d) => { const r = await post<{ detail: string }>(`/employees/${id}/create_account/`, d); toast.ok(r.detail); refresh(); }} />
      <FormDialog open={dialog === "letter"} onClose={() => setDialog(null)} title="Generate letter" submitLabel="Generate"
        fields={[{ name: "template", label: "Template", type: "select", required: true, options: templates.items.map((t) => ({ value: t.id as number, label: t.name as string })) },
          { name: "reference", label: "Reference number" }, { name: "addressed_to", label: "Addressed to" }, { name: "purpose", label: "Purpose" }]}
        onSubmit={async (d) => {
          const v = d as E;
          await post(`/documents/templates/${v.template}/generate/`, { employee: Number(id), reference: v.reference, context: { addressed_to: v.addressed_to, purpose: v.purpose } });
          toast.ok("Letter generated and filed under Documents."); refresh(); setTab("documents");
        }} />
    </>
  );
}
