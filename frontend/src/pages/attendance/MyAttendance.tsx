import Fingerprint from "@mui/icons-material/Fingerprint";
import { Alert, Box, Button, Card, CardContent, Chip, Grid2 as Grid, Stack, Typography } from "@mui/material";
import dayjs from "dayjs";
import { useState } from "react";
import { api, errorMessage } from "../../api/client";
import { post, useApi, useInvalidate, useList } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { DataTable } from "../../components/DataTable";
import { StatusChip, useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { PageHeader, Section } from "../../components/PageHeader";
import { fmtDate, fmtTime } from "../../utils";

interface ClockState { can_clock: boolean; next_direction: string; shift: string | null;
  events: { timestamp: string; direction: string; source: string; within_geofence: boolean | null }[] }

function position(): Promise<GeolocationPosition | null> {
  return new Promise((resolve) => {
    if (!navigator.geolocation) return resolve(null);
    navigator.geolocation.getCurrentPosition(resolve, () => resolve(null), { enableHighAccuracy: true, timeout: 8000 });
  });
}

export default function MyAttendance() {
  const { me } = useAuth();
  const toast = useToast();
  const inv = useInvalidate();
  const clock = useApi<ClockState>("/attendance/clock/");
  const start = dayjs().subtract(30, "day").format("YYYY-MM-DD");
  const days = useList("/attendance/days/", { employee: me?.employee?.id, start });
  const corrections = useList("/attendance/corrections/", { employee: me?.employee?.id });
  const roster = useList("/attendance/roster/", { employee: me?.employee?.id, start: dayjs().format("YYYY-MM-DD"), end: dayjs().add(14, "day").format("YYYY-MM-DD") });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [correcting, setCorrecting] = useState<string | null>(null);

  const doClock = async () => {
    setBusy(true); setError(null);
    try {
      const pos = await position();
      const r = await post<{ direction: string; timestamp: string }>("/attendance/clock/", {
        source: /Mobi|Android/i.test(navigator.userAgent) ? "mobile" : "web",
        latitude: pos ? Number(pos.coords.latitude.toFixed(6)) : null, longitude: pos ? Number(pos.coords.longitude.toFixed(6)) : null,
      });
      toast.ok(`Clocked ${r.direction} at ${fmtTime(r.timestamp)}`);
      inv("/attendance/");
    } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  };

  const c = clock.data;
  return (
    <>
      <PageHeader title="My attendance" />
      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid size={{ xs: 12, md: 5 }}>
          <Card sx={{ height: "100%" }}><CardContent sx={{ textAlign: "center" }}>
            <Typography variant="h4" fontWeight={700}>{dayjs().format("HH:mm")}</Typography>
            <Typography color="text.secondary">{dayjs().format("dddd, D MMMM YYYY")}</Typography>
            <Typography variant="body2" sx={{ my: 1 }}>Shift: {c?.shift || "No shift scheduled"}</Typography>
            {error && <Alert severity="error" sx={{ my: 1, textAlign: "left" }}>{error}</Alert>}
            <Button size="large" variant="contained" color={c?.next_direction === "out" ? "secondary" : "primary"} startIcon={<Fingerprint />}
              disabled={busy || !c?.can_clock} onClick={doClock} sx={{ px: 5, py: 1.5, mt: 1 }}>
              Clock {c?.next_direction === "out" ? "out" : "in"}
            </Button>
            <Stack direction="row" spacing={1} justifyContent="center" flexWrap="wrap" useFlexGap sx={{ mt: 2 }}>
              {(c?.events || []).map((e) => (
                <Chip key={e.timestamp} variant="outlined" label={`${e.direction.toUpperCase()} ${fmtTime(e.timestamp)} · ${e.source}`}
                  color={e.within_geofence === false ? "warning" : "default"} />
              ))}
            </Stack>
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>Your location is checked only at the moment you clock.</Typography>
          </CardContent></Card>
        </Grid>
        <Grid size={{ xs: 12, md: 7 }}>
          <Section title="My upcoming shifts (14 days)" dense>
            <DataTable dense rows={roster.items} emptyTitle="No published roster" columns={[
              { key: "date", label: "Date", render: (r) => dayjs(r.date as string).format("ddd DD/MM") },
              { key: "shift_name", label: "Shift", render: (r) => <Stack direction="row" spacing={1} alignItems="center">
                <Box sx={{ width: 10, height: 10, borderRadius: 5, bgcolor: (r.shift_color as string) || "#ccc" }} /><span>{(r.shift_name as string) || "Off"}</span></Stack> },
              { key: "is_on_call", label: "", render: (r) => (r.is_on_call ? <Chip label="On call" /> : null) },
            ]} />
          </Section>
        </Grid>
      </Grid>
      <Section title="Last 30 days" dense>
        <DataTable dense loading={days.isLoading} rows={days.items} columns={[
          { key: "date", label: "Date", render: (r) => dayjs(r.date as string).format("ddd DD/MM/YYYY") },
          { key: "shift_name", label: "Shift", hideOnMobile: true },
          { key: "first_in", label: "In", render: (r) => fmtTime(r.first_in as string) },
          { key: "last_out", label: "Out", render: (r) => fmtTime(r.last_out as string) },
          { key: "worked_minutes", label: "Hours", align: "right", render: (r) => ((r.worked_minutes as number) / 60).toFixed(1) },
          { key: "late_minutes", label: "Late (min)", align: "right", hideOnMobile: true },
          { key: "overtime_minutes", label: "OT (h)", align: "right", render: (r) => (r.overtime_minutes ? ((r.overtime_minutes as number) / 60).toFixed(1) : ""), hideOnMobile: true },
          { key: "status", label: "Status", render: (r) => <StatusChip value={r.status as string} /> },
          { key: "_c", label: "", render: (r) => ["incomplete", "absent", "late"].includes(r.status as string) && !r.locked ?
            <Button size="small" onClick={() => setCorrecting(r.date as string)}>Correct</Button> : null },
        ]} />
      </Section>
      <Section title="My correction requests" dense>
        <DataTable dense rows={corrections.items} emptyTitle="No corrections requested" columns={[
          { key: "date", label: "Date", render: (r) => fmtDate(r.date as string) }, { key: "reason", label: "Reason" },
          { key: "status", label: "Status", render: (r) => <StatusChip value={r.status as string} /> }]} />
      </Section>
      <FormDialog open={!!correcting} onClose={() => setCorrecting(null)} title={`Attendance correction — ${fmtDate(correcting)}`} submitLabel="Submit"
        intro="Your supervisor will review the correction."
        fields={[{ name: "clock_in", label: "Actual clock-in", type: "datetime", width: 6 }, { name: "clock_out", label: "Actual clock-out", type: "datetime", width: 6 },
          { name: "reason", label: "Reason (e.g. device fault, field work)", type: "textarea", required: true }]}
        initial={{ clock_in: correcting ? `${correcting}T08:00` : "", clock_out: correcting ? `${correcting}T17:00` : "" }}
        onSubmit={async (d) => {
          const v = d as Record<string, string>;
          const toIso = (s: string) => (s ? dayjs(s).toISOString() : null);
          await api.post("/attendance/corrections/", { date: correcting, reason: v.reason, clock_in: toIso(v.clock_in), clock_out: toIso(v.clock_out) });
          toast.ok("Correction submitted."); inv("/attendance/");
        }} />
    </>
  );
}
