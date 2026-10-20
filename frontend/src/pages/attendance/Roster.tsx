import AutoMode from "@mui/icons-material/AutoMode";
import ChevronLeft from "@mui/icons-material/ChevronLeft";
import ChevronRight from "@mui/icons-material/ChevronRight";
import Publish from "@mui/icons-material/Publish";
import { Alert, Box, Button, Card, IconButton, Menu, MenuItem, Stack, TextField, Typography } from "@mui/material";
import dayjs from "dayjs";
import { useMemo, useState } from "react";
import { api, errorMessage } from "../../api/client";
import { post, useInvalidate, useList } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { Loading, useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { PageHeader } from "../../components/PageHeader";

interface Entry { id: number; employee: number; date: string; shift: number | null; shift_name: string | null; shift_color: string | null; is_published: boolean; is_on_call: boolean }
interface Shift { id: number; name: string; code: string; color: string }

export default function Roster() {
  const { can } = useAuth();
  const manage = can("attendance.manage");
  const toast = useToast();
  const inv = useInvalidate();
  const [week, setWeek] = useState(dayjs().startOf("week").add(1, "day"));
  const [dept, setDept] = useState("");
  const [cell, setCell] = useState<{ anchor: HTMLElement; employee: number; date: string; entry?: Entry } | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const days = Array.from({ length: 14 }, (_, i) => week.add(i, "day"));
  const start = days[0].format("YYYY-MM-DD"), end = days[13].format("YYYY-MM-DD");
  const entries = useList<Entry>("/attendance/roster/", { start, end, employee__department: dept });
  const shifts = useList<Shift>("/attendance/shifts/");
  const patterns = useList<{ id: number; name: string }>(generating ? "/attendance/patterns/" : null);
  const depts = useList<{ id: number; name: string }>("/org/departments/");
  const emps = useList<{ id: number; full_name: string; job_title_name: string }>("/employees/", { department: dept });
  const byKey = useMemo(() => new Map(entries.items.map((e) => [`${e.employee}|${e.date}`, e])), [entries.items]);

  const assign = async (shift: number | null, onCall = false) => {
    if (!cell) return;
    setError(null);
    try {
      if (cell.entry) await api.patch(`/attendance/roster/${cell.entry.id}/`, { shift, is_on_call: onCall });
      else await api.post("/attendance/roster/", { employee: cell.employee, date: cell.date, shift, is_on_call: onCall });
      inv("/attendance/roster/");
    } catch (e) { setError(errorMessage(e)); }
    setCell(null);
  };
  const unpublished = entries.items.filter((e) => !e.is_published).length;
  return (
    <>
      <PageHeader title="Duty roster" subtitle="Two-week view. Click a cell to assign a shift. Staff see only published rosters."
        actions={<Stack direction="row" spacing={1} alignItems="center">
          <TextField select label="Department / ward" value={dept} onChange={(e) => setDept(e.target.value)} sx={{ minWidth: 200 }}>
            <MenuItem value="">All</MenuItem>{depts.items.map((d) => <MenuItem key={d.id} value={d.id}>{d.name}</MenuItem>)}
          </TextField>
          <IconButton onClick={() => setWeek(week.subtract(7, "day"))}><ChevronLeft /></IconButton>
          <Typography variant="body2" fontWeight={600}>{days[0].format("DD MMM")} – {days[13].format("DD MMM YYYY")}</Typography>
          <IconButton onClick={() => setWeek(week.add(7, "day"))}><ChevronRight /></IconButton>
          {manage && <Button startIcon={<AutoMode />} onClick={() => setGenerating(true)}>Generate</Button>}
          {manage && unpublished > 0 && <Button variant="contained" startIcon={<Publish />} onClick={async () => {
            const r = await post<{ published: number }>("/attendance/roster/publish/", { start, end, department: dept || undefined });
            toast.ok(`${r.published} shifts published.`); inv("/attendance/roster/");
          }}>Publish ({unpublished})</Button>}
        </Stack>} />
      {error && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>{error}</Alert>}
      <Stack direction="row" spacing={2} sx={{ mb: 1 }} flexWrap="wrap">
        {shifts.items.map((s) => <Stack key={s.id} direction="row" spacing={0.5} alignItems="center"><Box sx={{ width: 12, height: 12, borderRadius: 1, bgcolor: s.color }} /><Typography variant="caption">{s.name}</Typography></Stack>)}
      </Stack>
      <Card sx={{ overflowX: "auto" }}>
        {entries.isLoading || emps.isLoading ? <Loading /> : (
          <Box component="table" sx={{ borderCollapse: "collapse", fontSize: 12, width: "100%" }}>
            <thead><tr>
              <Box component="th" sx={{ textAlign: "left", p: 1, minWidth: 170, position: "sticky", left: 0, bgcolor: "#fff" }}>Staff</Box>
              {days.map((d) => <Box component="th" key={d.format()} sx={{ p: 0.5, minWidth: 54, bgcolor: d.day() % 6 === 0 ? "#f8fafc" : undefined }}>{d.format("ddd")}<br />{d.format("DD/MM")}</Box>)}
            </tr></thead>
            <tbody>
              {emps.items.map((e) => (
                <tr key={e.id}>
                  <Box component="td" sx={{ p: 1, borderTop: "1px solid #eef1f4", position: "sticky", left: 0, bgcolor: "#fff", whiteSpace: "nowrap" }}>
                    <b>{e.full_name}</b><br /><Typography variant="caption" color="text.secondary">{e.job_title_name}</Typography>
                  </Box>
                  {days.map((d) => {
                    const ds = d.format("YYYY-MM-DD");
                    const en = byKey.get(`${e.id}|${ds}`);
                    return (
                      <Box component="td" key={ds} onClick={(ev: React.MouseEvent<HTMLElement>) => manage && setCell({ anchor: ev.currentTarget, employee: e.id, date: ds, entry: en })}
                        sx={{ borderTop: "1px solid #eef1f4", p: "3px", cursor: manage ? "pointer" : undefined, textAlign: "center" }}>
                        {en && (
                          <Box sx={{ borderRadius: 1, px: 0.5, py: 0.25, color: en.shift ? "#fff" : "text.secondary", bgcolor: en.shift_color || "#e5e7eb",
                            opacity: en.is_published ? 1 : 0.55, outline: en.is_on_call ? "2px dashed #b45309" : undefined }}>
                            {en.shift_name ? en.shift_name.split(" ")[0] : "Off"}
                          </Box>
                        )}
                      </Box>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </Box>
        )}
      </Card>
      <Menu anchorEl={cell?.anchor} open={!!cell} onClose={() => setCell(null)}>
        {shifts.items.map((s) => <MenuItem key={s.id} onClick={() => assign(s.id)}>{s.name}</MenuItem>)}
        {shifts.items.map((s) => <MenuItem key={`oc${s.id}`} onClick={() => assign(s.id, true)}>{s.name} — on call</MenuItem>)}
        <MenuItem onClick={() => assign(null)}>Day off</MenuItem>
        {cell?.entry && <MenuItem onClick={async () => { await api.delete(`/attendance/roster/${cell.entry!.id}/`); inv("/attendance/roster/"); setCell(null); }}>Clear</MenuItem>}
      </Menu>
      <FormDialog open={generating} onClose={() => setGenerating(false)} title="Generate roster from a rotation pattern" submitLabel="Generate"
        intro="Creates unpublished entries for the selected staff. Existing entries are kept unless you tick overwrite. Clinical staff with lapsed licences are blocked."
        fields={[
          { name: "pattern", label: "Pattern", type: "select", required: true, options: patterns.items.map((p) => ({ value: p.id, label: p.name })) },
          { name: "employees", label: "Staff", type: "multiref", ref: "/employees/", refParams: dept ? { department: dept } : undefined, refLabel: (x) => String(x.full_name), required: true },
          { name: "start", label: "From", type: "date", required: true, width: 6 }, { name: "end", label: "To", type: "date", required: true, width: 6 },
          { name: "stagger", label: "Stagger each person by (days)", type: "number", width: 6 }, { name: "offset", label: "Start offset in cycle", type: "number", width: 6 },
          { name: "overwrite", label: "Overwrite existing entries", type: "checkbox" },
        ]} initial={{ start, end, stagger: 1, offset: 0 }}
        onSubmit={async (d) => { const r = await post<{ created: number }>("/attendance/roster/generate/", d); toast.ok(`${r.created} roster entries created.`); inv("/attendance/roster/"); }} />
    </>
  );
}
