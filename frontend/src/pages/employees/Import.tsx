import Download from "@mui/icons-material/Download";
import UploadFile from "@mui/icons-material/UploadFile";
import { Alert, Button, Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography } from "@mui/material";
import { useState } from "react";
import { api, download, errorMessage } from "../../api/client";
import { useInvalidate } from "../../api/hooks";
import { PageHeader, Section } from "../../components/PageHeader";

interface Result { ok: boolean; rows?: number; valid?: number; created: number; dry_run?: boolean; errors: { row: number; errors: string[] }[] }

export default function ImportPage() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inv = useInvalidate();
  const send = async (dryRun: boolean) => {
    if (!file) return;
    setBusy(true); setError(null);
    const fd = new FormData();
    fd.append("file", file);
    fd.append("dry_run", String(dryRun));
    try {
      const { data } = await api.post<Result>("/employees/import/", fd);
      setResult(data);
      if (!dryRun) inv("/employees");
    } catch (e: unknown) {
      const data = (e as { response?: { data?: Result } }).response?.data;
      if (data?.errors) setResult(data); else setError(errorMessage(e));
    } finally { setBusy(false); }
  };
  return (
    <>
      <PageHeader title="Bulk import employees" subtitle="Migrate existing staff records from Excel. Every row is validated before anything is saved." />
      <Section title="1. Download the template">
        <Typography variant="body2" sx={{ mb: 1 }}>Use department codes, grade codes and job titles exactly as configured. Dates as DD/MM/YYYY. Format account numbers as Text.</Typography>
        <Button startIcon={<Download />} onClick={() => download("/employees/import-template/")}>Download template</Button>
      </Section>
      <Section title="2. Upload and validate">
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
          <Button component="label" variant="outlined" startIcon={<UploadFile />}>
            {file ? file.name : "Choose .xlsx file"}
            <input hidden type="file" accept=".xlsx" onChange={(e) => { setFile(e.target.files?.[0] || null); setResult(null); }} />
          </Button>
          <Button variant="contained" disabled={!file || busy} onClick={() => send(true)}>Validate (dry run)</Button>
          <Button variant="contained" color="success" disabled={!file || busy || !result?.ok || !result?.dry_run} onClick={() => send(false)}>Import {result?.valid ?? ""} records</Button>
        </Stack>
        {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
        {result && (
          <>
            <Alert severity={result.ok ? "success" : "error"} sx={{ mt: 2 }}>
              {result.dry_run === false && result.ok ? `${result.created} employees imported.` :
                result.ok ? `All ${result.valid} rows are valid. Click Import to save them.` : `${result.errors.length} row(s) have problems — fix them in Excel and validate again. Nothing was saved.`}
            </Alert>
            {result.errors.length > 0 && (
              <Table size="small" sx={{ mt: 1 }}>
                <TableHead><TableRow><TableCell>Row</TableCell><TableCell>Problems</TableCell></TableRow></TableHead>
                <TableBody>{result.errors.map((r) => <TableRow key={r.row}><TableCell>{r.row}</TableCell><TableCell>{r.errors.join("; ")}</TableCell></TableRow>)}</TableBody>
              </Table>
            )}
          </>
        )}
      </Section>
    </>
  );
}
