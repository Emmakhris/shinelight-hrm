import { Button, Card, MenuItem, Tab, Tabs, TextField } from "@mui/material";
import { useState } from "react";
import { api, download } from "../../api/client";
import { useInvalidate, useList } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { StatusChip, useToast } from "../../components/Feedback";
import { PageHeader } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";
import SendForSignature from "../../components/SendForSignature";
import { fmtDate, titleCase } from "../../utils";

const CONF = [{ value: "internal", label: "Internal" }, { value: "confidential", label: "Confidential (HR)" }, { value: "restricted", label: "Restricted" }];

export default function Documents() {
  const { can } = useAuth();
  const [tab, setTab] = useState(0);
  const [category, setCategory] = useState("");
  const cats = useList<{ id: number; name: string }>("/documents/categories/");
  const toast = useToast();
  const inv = useInvalidate();
  const docFields = [
    { name: "employee", label: "Employee (blank = organization document / policy)", type: "ref" as const, ref: "/employees/", refLabel: (e: Record<string, unknown>) => `${e.full_name} (${e.staff_number})` },
    { name: "category", label: "Category", type: "ref" as const, ref: "/documents/categories/", required: true, width: 6 as const },
    { name: "title", label: "Title", required: true, width: 6 as const },
    { name: "file", label: "Choose file (PDF, Word, Excel, image ≤ 15 MB)", type: "file" as const },
    { name: "issue_date", label: "Issue date", type: "date" as const, width: 4 as const },
    { name: "expiry_date", label: "Expiry date", type: "date" as const, width: 4 as const },
    { name: "reference_no", label: "Reference", width: 4 as const },
    { name: "confidentiality", label: "Confidentiality", type: "select" as const, options: CONF, width: 6 as const },
    { name: "tags", label: "Tags", width: 6 as const },
    { name: "is_policy", label: "Policy / handbook (visible to all staff)", type: "checkbox" as const, width: 6 as const },
    { name: "requires_acknowledgment", label: "Staff must acknowledge", type: "checkbox" as const, width: 6 as const },
    { name: "visible_to_employee", label: "Visible to the employee", type: "checkbox" as const, width: 6 as const },
    { name: "allow_download", label: "Allow download / print", type: "checkbox" as const, width: 6 as const },
    { name: "description", label: "Description", type: "textarea" as const },
  ];
  const cols = [
    { key: "title", label: "Title" }, { key: "employee_name", label: "Employee", render: (r: Record<string, unknown>) => (r.employee_name as string) || "Organization" },
    { key: "category_name", label: "Category" }, { key: "confidentiality", label: "Access", render: (r: Record<string, unknown>) => titleCase(r.confidentiality as string) },
    { key: "expiry_date", label: "Expires", render: (r: Record<string, unknown>) => r.is_expired ? <StatusChip value="expired" label={fmtDate(r.expiry_date as string)} /> : fmtDate(r.expiry_date as string) },
    { key: "current_version", label: "Ver." },
    { key: "legal_hold", label: "Hold", render: (r: Record<string, unknown>) => (r.legal_hold ? "Legal hold" : "") },
  ];
  const actions = (r: Record<string, unknown>) => <>
    {(r.current_version as number) > 0 && <Button size="small" onClick={() => download(`/documents/${r.id}/download/`)}>Open</Button>}
    {can("documents.upload") && <SendForSignature doc={r} />}
    {can("documents.manage") && <Button size="small" onClick={async () => {
      const reason = r.legal_hold ? "" : window.prompt("Legal hold reason:"); if (!r.legal_hold && !reason) return;
      await api.post(`/documents/${r.id}/legal_hold/`, { hold: !r.legal_hold, reason }); toast.ok("Legal hold updated."); inv("/documents/");
    }}>{r.legal_hold ? "Release hold" : "Legal hold"}</Button>}
  </>;
  return (
    <>
      <PageHeader title="Personnel documents" subtitle="Versioned, classified and access-controlled. Every download is logged." />
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}><Tab label="All documents" /><Tab label="Expiring (60 days)" />
        {can("documents.manage") && <Tab label="Retention: due for disposal" />}{can("documents.manage") && <Tab label="Categories" />}</Tabs>
      <Card>
        {tab === 0 && <ResourcePage embedded title="Document" url="/documents/" params={{ category, is_archived: "false" }} fields={docFields} canDelete
          columns={cols} rowActions={actions} createLabel="Upload document" writePerm="documents.upload"
          defaults={{ confidentiality: "confidential", visible_to_employee: true, allow_download: true }}
          filters={<TextField select label="Category" value={category} onChange={(e) => setCategory(e.target.value)} sx={{ minWidth: 200 }}>
            <MenuItem value="">All</MenuItem>{cats.items.map((c) => <MenuItem key={c.id} value={c.id}>{c.name}</MenuItem>)}</TextField>} />}
        {tab === 1 && <ResourcePage embedded title="Expiring" url="/documents/expiring/" columns={cols} rowActions={actions} searchable={false} />}
        {tab === 2 && <ResourcePage embedded title="Disposal" url="/documents/disposal-queue/" columns={cols} searchable={false}
          rowActions={(r) => <Button size="small" color="error" onClick={async () => {
            if (!window.confirm("Permanently and securely dispose of this document? This cannot be undone.")) return;
            await api.post(`/documents/${r.id}/dispose/`); toast.ok("Disposed."); inv("/documents/");
          }}>Dispose</Button>} />}
        {tab === 3 && <ResourcePage embedded title="Category" url="/documents/categories/"
          columns={[{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "default_confidentiality", label: "Default access" },
            { key: "retention_years", label: "Retention (yrs after exit)" }, { key: "requires_expiry", label: "Expiry", render: (r) => (r.requires_expiry ? "Required" : "") },
            { key: "is_mandatory", label: "Mandatory", render: (r) => (r.is_mandatory ? "Yes" : "") }]}
          fields={[{ name: "code", label: "Code", required: true, width: 4 }, { name: "name", label: "Name", required: true, width: 8 },
            { name: "default_confidentiality", label: "Default access", type: "select", options: CONF, width: 6 },
            { name: "retention_years", label: "Retain for (years after exit)", type: "number", width: 6 },
            { name: "requires_expiry", label: "Requires expiry date", type: "checkbox", width: 4 }, { name: "is_mandatory", label: "Mandatory for all staff", type: "checkbox", width: 4 },
            { name: "visible_to_employee", label: "Visible to employee", type: "checkbox", width: 4 }]} defaults={{ retention_years: 7, default_confidentiality: "confidential", visible_to_employee: true }} />}
      </Card>
    </>
  );
}
