import { FormControlLabel, MenuItem, Switch, TextField } from "@mui/material";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtDate } from "../../utils";
import { QUALIFICATIONS, SOURCES, STAGE_LABEL } from "./constants";

export default function Candidates() {
  const nav = useNavigate();
  const [pool, setPool] = useState(true);
  const [qual, setQual] = useState("");
  return (
    <ResourcePage title="Candidates & talent pool" url="/recruitment/candidates/" writePerm="recruitment.manage" canCreate={false}
      params={{ talent_pool: pool ? "true" : undefined, highest_qualification: qual, anonymised: "false" }}
      subtitle="People who applied before. Candidates in the talent pool agreed to be contacted about future roles. Personal data is anonymised automatically when the retention period ends."
      onRowClick={(r) => r.applications?.[0] && nav(`/recruitment/applications/${r.applications[0].id}`)}
      filters={<>
        <FormControlLabel control={<Switch checked={pool} onChange={(e) => setPool(e.target.checked)} />} label="Talent pool only" />
        <TextField select size="small" label="Qualification" value={qual} onChange={(e) => setQual(e.target.value)} sx={{ minWidth: 180 }}>
          <MenuItem value="">Any</MenuItem>{QUALIFICATIONS.map((q) => <MenuItem key={q.value} value={q.value}>{q.label}</MenuItem>)}
        </TextField></>}
      columns={[
        { key: "full_name", label: "Name", render: (r) => <><b>{r.full_name}</b><br /><small>{r.email}</small></> },
        { key: "current_title", label: "Current role", hideOnMobile: true, render: (r) => [r.current_title, r.current_employer].filter(Boolean).join(", ") },
        { key: "highest_qualification", label: "Qualification", render: (r) => QUALIFICATIONS.find((q) => q.value === r.highest_qualification)?.label },
        { key: "years_experience", label: "Exp.", align: "right", render: (r) => Number(r.years_experience) },
        { key: "source", label: "Source", hideOnMobile: true, render: (r) => SOURCES.find((s) => s.value === r.source)?.label },
        { key: "applications", label: "Applications", render: (r) => r.applications.map((a: { id: number; vacancy: string; stage: string }) => <div key={a.id}><small>{a.vacancy} — {STAGE_LABEL[a.stage]}</small></div>) },
        { key: "retain_until", label: "Keep until", render: (r) => fmtDate(r.retain_until) },
      ]}
      fields={[
        { name: "tags", label: "Tags (JSON list)", type: "json", helper: '["nursing", "night shift"]' },
        { name: "talent_pool", label: "In talent pool (candidate consented)", type: "checkbox" },
        { name: "retain_until", label: "Retain personal data until", type: "date" },
        { name: "notes", label: "Notes", type: "textarea" },
      ]}
    />
  );
}
