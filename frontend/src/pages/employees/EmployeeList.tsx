import Download from "@mui/icons-material/Download";
import PersonAdd from "@mui/icons-material/PersonAdd";
import Search from "@mui/icons-material/Search";
import { Avatar, Button, Card, InputAdornment, MenuItem, Stack, TextField } from "@mui/material";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { download } from "../../api/client";
import { post, useApi, useInvalidate, useList } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { DataTable } from "../../components/DataTable";
import { ErrorAlert, StatusChip, useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { PageHeader } from "../../components/PageHeader";
import { fmtDate, titleCase } from "../../utils";
import { hireFields } from "./fields";

export default function EmployeeList() {
  const { can } = useAuth();
  const nav = useNavigate();
  const toast = useToast();
  const inv = useInvalidate();
  const [search, setSearch] = useState("");
  const [department, setDepartment] = useState("");
  const [status, setStatus] = useState("");
  const [etype, setEtype] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [hiring, setHiring] = useState(false);
  const params = { search, department, status, employment_type: etype, page, page_size: pageSize, include_exited: status === "exited" ? 1 : undefined };
  const q = useApi<{ count: number; results: Record<string, unknown>[] }>("/employees/", params);
  const depts = useList<{ id: number; name: string }>("/org/departments/");

  return (
    <>
      <PageHeader title="Employees" subtitle={`${q.data?.count ?? "…"} records in your scope`}
        actions={<>
          {can("employees.export") && <Button startIcon={<Download />} onClick={() => download("/employees/export/", { department, status, employment_type: etype })}>Export</Button>}
          {can("employees.create") && <Button variant="contained" startIcon={<PersonAdd />} onClick={() => setHiring(true)}>New employee</Button>}
        </>} />
      <Card>
        <Stack direction={{ xs: "column", md: "row" }} spacing={1} sx={{ p: 1.5 }}>
          <TextField placeholder="Name, staff no, email, phone…" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            InputProps={{ startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment> }} sx={{ minWidth: 280 }} />
          <TextField select label="Department" value={department} onChange={(e) => { setDepartment(e.target.value); setPage(1); }} sx={{ minWidth: 200 }}>
            <MenuItem value="">All departments</MenuItem>
            {depts.items.map((d) => <MenuItem key={d.id} value={d.id}>{d.name}</MenuItem>)}
          </TextField>
          <TextField select label="Status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} sx={{ minWidth: 160 }}>
            <MenuItem value="">Current staff</MenuItem>
            {["active", "probation", "suspended", "on_leave", "exited"].map((s) => <MenuItem key={s} value={s}>{titleCase(s)}</MenuItem>)}
          </TextField>
          <TextField select label="Type" value={etype} onChange={(e) => { setEtype(e.target.value); setPage(1); }} sx={{ minWidth: 160 }}>
            <MenuItem value="">All types</MenuItem>
            {["permanent", "contract", "temporary", "national_service", "intern", "casual"].map((s) => <MenuItem key={s} value={s}>{titleCase(s)}</MenuItem>)}
          </TextField>
        </Stack>
        <ErrorAlert error={q.error} />
        <DataTable dense loading={q.isLoading} rows={q.data?.results || []} onRowClick={(r) => nav(`/employees/${r.id}`)}
          count={q.data?.count} page={page} pageSize={pageSize} onPageChange={setPage} onPageSizeChange={(s) => { setPageSize(s); setPage(1); }}
          columns={[
            { key: "full_name", label: "Name", render: (r) => (
              <Stack direction="row" spacing={1} alignItems="center">
                <Avatar src={(r.photo as string) || undefined} sx={{ width: 30, height: 30, fontSize: 13 }}>{String(r.first_name)[0]}</Avatar>
                <span>{r.full_name as string}</span>
              </Stack>) },
            { key: "staff_number", label: "Staff no" },
            { key: "job_title_name", label: "Job title", hideOnMobile: true },
            { key: "department_name", label: "Department", hideOnMobile: true },
            { key: "grade_code", label: "Grade", hideOnMobile: true },
            { key: "employment_type", label: "Type", render: (r) => titleCase(r.employment_type as string), hideOnMobile: true },
            { key: "hire_date", label: "Hired", render: (r) => fmtDate(r.hire_date as string), hideOnMobile: true },
            { key: "status", label: "Status", render: (r) => <StatusChip value={r.status as string} /> },
          ]} />
      </Card>
      <FormDialog open={hiring} onClose={() => setHiring(false)} title="New employee (appointment)" maxWidth="md" submitLabel="Create employee"
        fields={[...hireFields, { name: "allow_duplicate", label: "I have checked — this is not a duplicate person", type: "checkbox" }]}
        initial={{ nationality: "Ghanaian", employment_type: "permanent" }}
        onSubmit={async (d) => {
          const emp = await post<{ id: number }>("/employees/", d);
          toast.ok("Employee created. Next: add bank details, documents and a user account.");
          inv("/employees/");
          nav(`/employees/${emp.id}`);
        }} />
    </>
  );
}
