import Add from "@mui/icons-material/Add";
import Download from "@mui/icons-material/Download";
import { Button, Card, IconButton } from "@mui/material";
import { useState } from "react";
import { download } from "../../api/client";
import { post, useApi, useInvalidate } from "../../api/hooks";
import { DataTable } from "../../components/DataTable";
import { StatusChip, useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { PageHeader, Section } from "../../components/PageHeader";
import { fmtDate } from "../../utils";

interface Letters { templates: { id: number; name: string }[]; requests: Record<string, unknown>[] }

export default function MyDocuments() {
  const docs = useApi<Record<string, unknown>[]>("/me/documents/");
  const letters = useApi<Letters>("/me/letters/");
  const [requesting, setRequesting] = useState(false);
  const toast = useToast();
  const inv = useInvalidate();
  return (
    <>
      <PageHeader title="My documents & letters" subtitle="Your personnel documents and HR letters."
        actions={<Button variant="contained" startIcon={<Add />} onClick={() => setRequesting(true)}>Request a letter</Button>} />
      <Section title="Letter requests" dense>
        <DataTable dense rows={letters.data?.requests || []} loading={letters.isLoading} emptyTitle="No letter requests"
          columns={[
            { key: "template_name", label: "Letter" }, { key: "addressed_to", label: "Addressed to" },
            { key: "created_at", label: "Requested", render: (r) => fmtDate(r.created_at as string) },
            { key: "status", label: "Status", render: (r) => <StatusChip value={r.status as string} /> },
            { key: "document", label: "", align: "right", render: (r) => r.document ? (
              <IconButton size="small" onClick={() => download(`/documents/${r.document}/download/`)}><Download fontSize="small" /></IconButton>) : null },
          ]} />
      </Section>
      <Card>
        <DataTable rows={docs.data || []} loading={docs.isLoading} emptyTitle="No documents on file"
          columns={[
            { key: "title", label: "Document" }, { key: "category_name", label: "Category" },
            { key: "issue_date", label: "Issued", render: (r) => fmtDate(r.issue_date as string) },
            { key: "expiry_date", label: "Expires", render: (r) => fmtDate(r.expiry_date as string) },
            { key: "_dl", label: "", align: "right", render: (r) => (r.current_version as number) > 0 ? (
              <IconButton size="small" onClick={() => download(`/documents/${r.id}/download/`)}><Download fontSize="small" /></IconButton>) : null },
          ]} />
      </Card>
      <FormDialog open={requesting} onClose={() => setRequesting(false)} title="Request an HR letter" submitLabel="Submit request"
        fields={[
          { name: "template", label: "Letter", type: "select", required: true, options: (letters.data?.templates || []).map((t) => ({ value: t.id, label: t.name })) },
          { name: "addressed_to", label: "Addressed to (e.g. The Manager, GCB Bank, Ridge)" },
          { name: "purpose", label: "Purpose", type: "textarea" },
        ]}
        onSubmit={async (d) => { await post("/me/letters/", d); toast.ok("Letter request submitted."); inv("/me/letters/"); }} />
    </>
  );
}
