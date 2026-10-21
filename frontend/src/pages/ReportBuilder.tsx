import Add from "@mui/icons-material/Add";
import Delete from "@mui/icons-material/Delete";
import Download from "@mui/icons-material/Download";
import PlayArrow from "@mui/icons-material/PlayArrow";
import {
  Alert, Autocomplete, Box, Button, Card, Chip, Grid2 as Grid, IconButton, List, ListItemButton, ListItemText,
  MenuItem, Stack, TextField, Typography,
} from "@mui/material";
import { useMemo, useState } from "react";
import { api, download } from "../api/client";
import { useApi, useInvalidate } from "../api/hooks";
import { useAuth } from "../auth/AuthContext";
import { BarList, Columns } from "../components/Charts";
import { DataTable } from "../components/DataTable";
import { ErrorAlert, useToast } from "../components/Feedback";
import { PageHeader, Section } from "../components/PageHeader";

interface FieldDef { code: string; label: string; type: string; choices: { value: string; label: string }[] }
interface DatasetDef { code: string; label: string; description: string; fields: FieldDef[] }
interface Filter { field: string; op: string; value: string }
interface Agg { fn: string; field?: string }
interface Def {
  id?: number; code?: string; name: string; description?: string; dataset: string; columns: string[]; filters: Filter[];
  group_by: string[]; aggregates: Agg[]; sort: string; limit: number; chart: string; visibility: string;
  owner?: string; can_edit?: boolean;
}
interface Result { headers: string[]; rows: unknown[][]; truncated?: boolean; count?: number }

const OPS: Record<string, string> = {
  eq: "is", ne: "is not", in: "is one of (comma separated)", contains: "contains", gt: ">", gte: "≥", lt: "<", lte: "≤",
  isnull: "is empty (true/false)", last_days: "in the last N days",
};
const BLANK: Def = { name: "", dataset: "employees", columns: [], filters: [], group_by: [], aggregates: [], sort: "",
  limit: 0, chart: "none", visibility: "private" };

function ResultView({ result, chart }: { result: Result; chart?: string }) {
  const rows = result.rows.map((r, i) => Object.fromEntries([["id", i], ...r.map((v, j) => [`c${j}`, v])]));
  const chartData = chart && chart !== "none" && result.headers.length >= 2
    ? result.rows.slice(0, 30).map((r) => ({ label: String(r[0] || "—"), value: Number(r[r.length - 1]) || 0 })) : null;
  return (
    <>
      {result.truncated && <Alert severity="warning" sx={{ mb: 1 }}>Only the first 50,000 records were read. Add filters to narrow the report.</Alert>}
      {chartData && <Section title={result.headers[result.headers.length - 1]}>{chart === "bar"
        ? <BarList data={chartData} valueLabel={result.headers[result.headers.length - 1]} />
        : <Columns data={chartData} valueLabel={result.headers[result.headers.length - 1]} />}</Section>}
      <Card><DataTable dense rows={rows} emptyTitle="No matching records"
        columns={result.headers.map((h, j) => ({ key: `c${j}`, label: h }))} /></Card>
    </>
  );
}

export default function ReportBuilder() {
  const { can } = useAuth();
  const toast = useToast();
  const inv = useInvalidate();
  const canBuild = can("reports.build");
  const saved = useApi<Def[]>("/reports/definitions/");
  const catalog = useApi<DatasetDef[]>(canBuild ? "/reports/definitions/datasets/" : null);
  const [def, setDef] = useState<Def | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [running, setRunning] = useState<Def | null>(null);
  const [error, setError] = useState<unknown>(null);
  const ds = useMemo(() => (catalog.data || []).find((d) => d.code === def?.dataset), [catalog.data, def?.dataset]);
  const fieldsOf = (codes: string[]) => (ds?.fields || []).filter((f) => codes.includes(f.code));
  const numeric = (ds?.fields || []).filter((f) => ["number", "money"].includes(f.type));
  const set = (patch: Partial<Def>) => setDef((d) => (d ? { ...d, ...patch } : d));

  const runSaved = async (d: Def) => {
    setError(null); setDef(null); setRunning(d);
    try { setResult((await api.get(`/reports/definitions/${d.id}/run/`)).data); } catch (e) { setError(e); setResult(null); }
  };
  const preview = async () => {
    setError(null);
    try { setResult((await api.post("/reports/definitions/preview/", def)).data); } catch (e) { setError(e); }
  };
  const save = async () => {
    if (!def) return;
    setError(null);
    try {
      const r = def.id ? await api.patch(`/reports/definitions/${def.id}/`, def) : await api.post("/reports/definitions/", def);
      setDef(r.data); toast.ok("Report saved."); inv("/reports/definitions/");
    } catch (e) { setError(e); }
  };
  const remove = async (d: Def) => {
    if (!window.confirm(`Delete "${d.name}"?`)) return;
    await api.delete(`/reports/definitions/${d.id}/`); toast.ok("Deleted."); inv("/reports/definitions/");
    if (def?.id === d.id) setDef(null);
  };
  const exportIt = async (d: Def) => {
    try {
      await download(`/reports/definitions/${d.id}/run/`, { format: "xlsx" }, `${d.name}.xlsx`);
    } catch (e) {
      if (!can("reports.export")) {
        const reason = window.prompt("Exports need approval. Reason for this export:");
        if (reason) {
          await api.post("/reports/export-requests/", { report_code: d.code, params: {}, reason });
          toast.ok("Export request submitted. Download it from Reports once approved.");
        }
      } else toast.error(e);
    }
  };

  return (
    <>
      <PageHeader title="Report builder" subtitle="Build your own reports from approved datasets. Results always respect the viewer's own data access."
        actions={canBuild && <Button variant="contained" startIcon={<Add />} onClick={() => { setDef({ ...BLANK }); setResult(null); setRunning(null); }}>New report</Button>} />
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 3 }}>
          <Section title="Saved reports" dense>
            {(saved.data || []).length === 0 && <Typography color="text.secondary" variant="body2">No saved reports yet.</Typography>}
            <List dense disablePadding>
              {(saved.data || []).map((d) => (
                <ListItemButton key={d.id} selected={running?.id === d.id || def?.id === d.id} onClick={() => runSaved(d)}>
                  <ListItemText primary={d.name} secondary={`${d.visibility === "shared" ? "Shared" : "Private"} · ${d.owner}`} />
                  {d.can_edit && <IconButton size="small" aria-label={`Delete ${d.name}`} onClick={(e) => { e.stopPropagation(); remove(d); }}><Delete fontSize="small" /></IconButton>}
                </ListItemButton>
              ))}
            </List>
          </Section>
        </Grid>
        <Grid size={{ xs: 12, md: 9 }}>
          <ErrorAlert error={error} />
          {def && canBuild && (
            <Section title={def.id ? `Edit: ${def.name}` : "New report"}>
              <Grid container spacing={1.5}>
                <Grid size={{ xs: 12, md: 6 }}><TextField fullWidth label="Name" value={def.name} onChange={(e) => set({ name: e.target.value })} /></Grid>
                <Grid size={{ xs: 12, md: 6 }}>
                  <TextField select fullWidth label="Dataset" value={def.dataset} helperText={ds?.description}
                    onChange={(e) => set({ dataset: e.target.value, columns: [], filters: [], group_by: [], aggregates: [], sort: "" })}>
                    {(catalog.data || []).map((d) => <MenuItem key={d.code} value={d.code}>{d.label}</MenuItem>)}
                  </TextField>
                </Grid>
                <Grid size={12}>
                  <Autocomplete multiple options={ds?.fields || []} value={fieldsOf(def.columns)} getOptionLabel={(f) => f.label}
                    isOptionEqualToValue={(a, b) => a.code === b.code} disabled={def.group_by.length > 0}
                    onChange={(_, v) => set({ columns: v.map((f) => f.code) })}
                    renderInput={(p) => <TextField {...p} label="Columns" helperText={def.group_by.length ? "Grouped reports show the group columns and summaries." : "Pick the columns in the order you want them."} />} />
                </Grid>
                <Grid size={{ xs: 12, md: 6 }}>
                  <Autocomplete multiple options={ds?.fields || []} value={fieldsOf(def.group_by)} getOptionLabel={(f) => f.label}
                    isOptionEqualToValue={(a, b) => a.code === b.code}
                    onChange={(_, v) => set({ group_by: v.slice(0, 2).map((f) => f.code), aggregates: v.length && !def.aggregates.length ? [{ fn: "count" }] : def.aggregates })}
                    renderInput={(p) => <TextField {...p} label="Group by (up to 2)" />} />
                </Grid>
                <Grid size={{ xs: 12, md: 6 }}>
                  <Stack spacing={1}>
                    {def.aggregates.map((a, i) => (
                      <Stack key={i} direction="row" spacing={1}>
                        <TextField select size="small" label="Summary" value={a.fn} sx={{ minWidth: 110 }}
                          onChange={(e) => set({ aggregates: def.aggregates.map((x, j) => (j === i ? { fn: e.target.value, field: e.target.value === "count" ? undefined : x.field || numeric[0]?.code } : x)) })}>
                          {["count", "sum", "avg", "min", "max"].map((f) => <MenuItem key={f} value={f}>{f === "avg" ? "Average" : f[0].toUpperCase() + f.slice(1)}</MenuItem>)}
                        </TextField>
                        {a.fn !== "count" && (
                          <TextField select size="small" label="of" value={a.field || ""} sx={{ flex: 1 }}
                            onChange={(e) => set({ aggregates: def.aggregates.map((x, j) => (j === i ? { ...x, field: e.target.value } : x)) })}>
                            {numeric.map((f) => <MenuItem key={f.code} value={f.code}>{f.label}</MenuItem>)}
                          </TextField>)}
                        <IconButton aria-label="Remove summary" onClick={() => set({ aggregates: def.aggregates.filter((_, j) => j !== i) })}><Delete fontSize="small" /></IconButton>
                      </Stack>))}
                    {def.group_by.length > 0 && <Button size="small" sx={{ alignSelf: "flex-start" }} onClick={() => set({ aggregates: [...def.aggregates, { fn: "count" }] })}>Add summary</Button>}
                  </Stack>
                </Grid>
                <Grid size={12}>
                  <Typography variant="subtitle2" sx={{ mb: 1 }}>Filters</Typography>
                  <Stack spacing={1}>
                    {def.filters.map((f, i) => {
                      const fd = ds?.fields.find((x) => x.code === f.field);
                      const upd = (patch: Partial<Filter>) => set({ filters: def.filters.map((x, j) => (j === i ? { ...x, ...patch } : x)) });
                      return (
                        <Stack key={i} direction={{ xs: "column", sm: "row" }} spacing={1}>
                          <TextField select size="small" label="Field" value={f.field} sx={{ minWidth: 180 }} onChange={(e) => upd({ field: e.target.value, value: "" })}>
                            {(ds?.fields || []).map((x) => <MenuItem key={x.code} value={x.code}>{x.label}</MenuItem>)}
                          </TextField>
                          <TextField select size="small" label="Condition" value={f.op} sx={{ minWidth: 170 }} onChange={(e) => upd({ op: e.target.value })}>
                            {Object.entries(OPS).filter(([k]) => k !== "last_days" || fd?.type === "date").map(([k, v]) => <MenuItem key={k} value={k}>{v}</MenuItem>)}
                          </TextField>
                          {fd?.choices.length && ["eq", "ne"].includes(f.op) ? (
                            <TextField select size="small" label="Value" value={f.value} sx={{ flex: 1 }} onChange={(e) => upd({ value: e.target.value })}>
                              {fd.choices.map((c) => <MenuItem key={c.value} value={c.value}>{c.label}</MenuItem>)}
                            </TextField>
                          ) : (
                            <TextField size="small" label="Value" value={f.value} sx={{ flex: 1 }}
                              type={fd?.type === "date" && !["last_days", "isnull", "in"].includes(f.op) ? "date" : "text"}
                              InputLabelProps={{ shrink: true }} onChange={(e) => upd({ value: e.target.value })} />)}
                          <IconButton aria-label="Remove filter" onClick={() => set({ filters: def.filters.filter((_, j) => j !== i) })}><Delete fontSize="small" /></IconButton>
                        </Stack>);
                    })}
                    <Button size="small" sx={{ alignSelf: "flex-start" }} disabled={!ds}
                      onClick={() => set({ filters: [...def.filters, { field: ds!.fields[0].code, op: "eq", value: "" }] })}>Add filter</Button>
                  </Stack>
                </Grid>
                <Grid size={{ xs: 6, md: 3 }}>
                  <TextField select fullWidth size="small" label="Sort by" value={def.sort.replace(/^-/, "")}
                    onChange={(e) => set({ sort: e.target.value ? (def.sort.startsWith("-") ? "-" : "") + e.target.value : "" })}>
                    <MenuItem value="">Default</MenuItem>
                    {(def.group_by.length ? [...fieldsOf(def.group_by).map((f) => ({ code: f.code, label: f.label })),
                      ...def.aggregates.map((a) => ({ code: a.fn === "count" ? "count" : `${a.fn}_${a.field}`, label: a.fn === "count" ? "Count" : `${a.fn} of ${a.field}` }))]
                      : fieldsOf(def.columns)).map((f) => <MenuItem key={f.code} value={f.code}>{f.label}</MenuItem>)}
                  </TextField>
                </Grid>
                <Grid size={{ xs: 6, md: 2 }}>
                  <TextField select fullWidth size="small" label="Order" value={def.sort.startsWith("-") ? "desc" : "asc"} disabled={!def.sort}
                    onChange={(e) => set({ sort: (e.target.value === "desc" ? "-" : "") + def.sort.replace(/^-/, "") })}>
                    <MenuItem value="asc">Ascending</MenuItem><MenuItem value="desc">Descending</MenuItem>
                  </TextField>
                </Grid>
                <Grid size={{ xs: 6, md: 2 }}><TextField fullWidth size="small" type="number" label="Row limit (0 = all)" value={def.limit} onChange={(e) => set({ limit: Number(e.target.value) })} /></Grid>
                <Grid size={{ xs: 6, md: 2 }}>
                  <TextField select fullWidth size="small" label="Chart" value={def.chart} disabled={!def.group_by.length} onChange={(e) => set({ chart: e.target.value })}>
                    <MenuItem value="none">Table only</MenuItem><MenuItem value="bar">Bar list</MenuItem><MenuItem value="column">Columns</MenuItem>
                  </TextField>
                </Grid>
                <Grid size={{ xs: 12, md: 3 }}>
                  <TextField select fullWidth size="small" label="Visibility" value={def.visibility} onChange={(e) => set({ visibility: e.target.value })}>
                    <MenuItem value="private">Only me</MenuItem><MenuItem value="shared">Everyone with report access</MenuItem>
                  </TextField>
                </Grid>
              </Grid>
              <Stack direction="row" spacing={1} sx={{ mt: 2 }}>
                <Button variant="outlined" startIcon={<PlayArrow />} onClick={preview}>Preview (first 200 rows)</Button>
                <Button variant="contained" onClick={save} disabled={!def.name}>Save report</Button>
                {def.id && <Button onClick={() => set({ id: undefined, name: `${def.name} (copy)` })}>Save as copy…</Button>}
              </Stack>
              {def.visibility === "shared" && <Alert severity="info" sx={{ mt: 2 }}>Colleagues who run a shared report see only the records their own access allows.</Alert>}
            </Section>
          )}
          {running && !def && (
            <Section title={running.name} actions={<Stack direction="row" spacing={1}>
              {running.can_edit && <Button size="small" onClick={() => { setDef({ ...running }); setResult(null); }}>Edit</Button>}
              {!running.can_edit && canBuild && <Button size="small" onClick={() => { setDef({ ...running, id: undefined, name: `${running.name} (copy)`, visibility: "private" }); setResult(null); }}>Copy and edit</Button>}
              <Button size="small" startIcon={<Download />} onClick={() => exportIt(running)}>Export to Excel</Button>
            </Stack>}>
              {running.description && <Typography variant="body2" color="text.secondary">{running.description}</Typography>}
            </Section>
          )}
          {result && <Box><ResultView result={result} chart={def ? def.chart : running?.chart} />
            {typeof result.count === "number" && <Chip size="small" sx={{ mt: 1 }} label={`${result.count} rows`} />}</Box>}
          {!def && !running && (
            <Alert severity="info">{canBuild ? "Pick a saved report to run it, or start a new one." : "Pick a saved report to run it. Building reports needs the report-builder permission."}</Alert>
          )}
        </Grid>
      </Grid>
    </>
  );
}
