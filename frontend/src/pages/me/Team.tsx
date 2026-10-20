import { Card, Chip, FormControlLabel, Switch } from "@mui/material";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApi } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { DataTable } from "../../components/DataTable";
import { ErrorAlert, StatusChip } from "../../components/Feedback";
import { Kpi, PageHeader } from "../../components/PageHeader";
import { fmtDate } from "../../utils";

interface T { members: Record<string, unknown>[]; pending_approvals: number }

export default function Team() {
  const [direct, setDirect] = useState(false);
  const { data, isLoading, error } = useApi<T>("/me/team/", { direct: direct ? 1 : undefined });
  const nav = useNavigate();
  const { can } = useAuth();
  const members = data?.members || [];
  return (
    <>
      <PageHeader title="My team" subtitle="Your direct and indirect reports"
        actions={<FormControlLabel control={<Switch checked={direct} onChange={(e) => setDirect(e.target.checked)} />} label="Direct reports only" />} />
      <ErrorAlert error={error} />
      <Card sx={{ mb: 2, display: "flex", gap: 2, p: 2, flexWrap: "wrap", border: 0, bgcolor: "transparent" }}>
        <Kpi label="Team members" value={members.length} />
        <Kpi label="On leave today" value={members.filter((m) => m.on_leave).length} onClick={() => nav("/leave/calendar")} />
        <Kpi label="Awaiting my approval" value={data?.pending_approvals ?? 0} onClick={() => nav("/inbox")} />
      </Card>
      <Card>
        <DataTable loading={isLoading} rows={members} onRowClick={can("employees.view") ? (r) => nav(`/employees/${r.id}`) : undefined}
          columns={[
            { key: "name", label: "Name" }, { key: "staff_number", label: "Staff no" }, { key: "job_title", label: "Job title" },
            { key: "is_direct", label: "Reports", render: (r) => (r.is_direct ? "Direct" : "Indirect") },
            { key: "status", label: "Status", render: (r) => r.on_leave ? <Chip color="info" variant="outlined" label={`On ${r.on_leave}`} /> : <StatusChip value={r.status as string} /> },
            { key: "probation_end_date", label: "Probation ends", render: (r) => fmtDate(r.probation_end_date as string) },
            { key: "contract_end_date", label: "Contract ends", render: (r) => fmtDate(r.contract_end_date as string) },
          ]} />
      </Card>
    </>
  );
}
