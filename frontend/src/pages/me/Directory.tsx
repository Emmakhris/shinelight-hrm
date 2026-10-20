import { Avatar, Stack } from "@mui/material";
import { ResourcePage } from "../../components/ResourcePage";

export default function Directory() {
  return (
    <ResourcePage title="Staff directory" subtitle="Find colleagues by name, staff number, department or job title." url="/directory/"
      columns={[
        { key: "full_name", label: "Name", render: (r) => (
          <Stack direction="row" spacing={1} alignItems="center">
            <Avatar src={(r.photo as string) || undefined} sx={{ width: 28, height: 28, fontSize: 13 }}>{String(r.full_name)[0]}</Avatar>
            <span>{r.full_name as string}</span>
          </Stack>) },
        { key: "job_title_name", label: "Job title" }, { key: "department_name", label: "Department" },
        { key: "location_name", label: "Location", hideOnMobile: true }, { key: "work_email", label: "Email", hideOnMobile: true },
      ]} />
  );
}
