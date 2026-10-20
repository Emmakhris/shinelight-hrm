import ChevronLeft from "@mui/icons-material/ChevronLeft";
import ChevronRight from "@mui/icons-material/ChevronRight";
import { Box, Card, IconButton, MenuItem, Stack, TextField, Tooltip, Typography } from "@mui/material";
import dayjs from "dayjs";
import { useMemo, useState } from "react";
import { useApi, useList } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { Empty, Loading } from "../../components/Feedback";
import { PageHeader } from "../../components/PageHeader";

interface Ev { id: number; employee: number; employee_name: string; leave_type: string; color: string; start: string; end: string; status: string }

export default function LeaveCalendar() {
  const { can } = useAuth();
  const [month, setMonth] = useState(dayjs().startOf("month"));
  const [dept, setDept] = useState("");
  const start = month.format("YYYY-MM-DD");
  const end = month.endOf("month").format("YYYY-MM-DD");
  const broad = can("leave.view", "team");
  const { data, isLoading } = useApi<Ev[]>("/leave/requests/calendar/", { start, end, department: dept, scope: broad ? undefined : "department" });
  const depts = useList<{ id: number; name: string }>(broad ? "/org/departments/" : null);
  const holidays = useList<{ date: string; name: string }>("/admin/holidays/", { year: month.year() });
  const days = Array.from({ length: month.daysInMonth() }, (_, i) => month.date(i + 1));
  const people = useMemo(() => {
    const m = new Map<number, { name: string; events: Ev[] }>();
    (data || []).forEach((e) => { if (!m.has(e.employee)) m.set(e.employee, { name: e.employee_name, events: [] }); m.get(e.employee)!.events.push(e); });
    return [...m.entries()].sort((a, b) => a[1].name.localeCompare(b[1].name));
  }, [data]);
  const hol = new Map(holidays.items.map((h) => [h.date, h.name]));
  return (
    <>
      <PageHeader title="Team leave calendar" subtitle="Approved leave shown solid; pending requests shown hatched."
        actions={<Stack direction="row" spacing={1} alignItems="center">
          {broad && (
            <TextField select label="Department" value={dept} onChange={(e) => setDept(e.target.value)} sx={{ minWidth: 200 }}>
              <MenuItem value="">All in my scope</MenuItem>
              {depts.items.map((d) => <MenuItem key={d.id} value={d.id}>{d.name}</MenuItem>)}
            </TextField>
          )}
          <IconButton onClick={() => setMonth(month.subtract(1, "month"))} aria-label="Previous month"><ChevronLeft /></IconButton>
          <Typography fontWeight={650} sx={{ minWidth: 130, textAlign: "center" }}>{month.format("MMMM YYYY")}</Typography>
          <IconButton onClick={() => setMonth(month.add(1, "month"))} aria-label="Next month"><ChevronRight /></IconButton>
        </Stack>} />
      <Card sx={{ overflowX: "auto" }}>
        {isLoading ? <Loading /> : people.length === 0 ? <Empty title="No leave this month" /> : (
          <Box component="table" sx={{ borderCollapse: "collapse", width: "100%", fontSize: 12 }}>
            <thead>
              <tr>
                <Box component="th" sx={{ textAlign: "left", p: 1, position: "sticky", left: 0, bgcolor: "#fff", minWidth: 160 }}>Employee</Box>
                {days.map((d) => (
                  <Box component="th" key={d.date()} sx={{ p: 0.5, minWidth: 26, color: d.day() % 6 === 0 ? "text.disabled" : undefined,
                    bgcolor: hol.has(d.format("YYYY-MM-DD")) ? "#fff7e6" : undefined }}>
                    <Tooltip title={hol.get(d.format("YYYY-MM-DD")) || ""}><span>{d.format("dd")[0]}<br />{d.date()}</span></Tooltip>
                  </Box>
                ))}
              </tr>
            </thead>
            <tbody>
              {people.map(([id, p]) => (
                <tr key={id}>
                  <Box component="td" sx={{ p: 1, position: "sticky", left: 0, bgcolor: "#fff", borderTop: "1px solid #eef1f4", whiteSpace: "nowrap" }}>{p.name}</Box>
                  {days.map((d) => {
                    const ds = d.format("YYYY-MM-DD");
                    const ev = p.events.find((e) => e.start <= ds && e.end >= ds);
                    return (
                      <Box component="td" key={ds} sx={{ borderTop: "1px solid #eef1f4", p: "2px", bgcolor: d.day() % 6 === 0 ? "#fafafa" : undefined }}>
                        {ev && (
                          <Tooltip title={`${ev.leave_type} (${ev.status})`}>
                            <Box sx={{ height: 18, borderRadius: 1, bgcolor: ev.status === "pending" ? "transparent" : ev.color,
                              border: `1.5px solid ${ev.color}`,
                              backgroundImage: ev.status === "pending" ? `repeating-linear-gradient(45deg, ${ev.color}55 0 3px, transparent 3px 6px)` : undefined }} />
                          </Tooltip>
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
    </>
  );
}
