import { Card, MenuItem, Stack, TextField } from "@mui/material";
import { useState } from "react";
import { useApi } from "../../api/hooks";
import { PageHeader } from "../../components/PageHeader";
import { APPRAISAL_STATUS } from "./common";
import { AppraisalTable } from "./MyPerformance";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export default function TeamAppraisals() {
  const [status, setStatus] = useState("");
  const q = useApi<R>("/performance/appraisals/", { team: 1, status, page_size: 200 });
  return (
    <>
      <PageHeader title="Team appraisals" subtitle="Agree objectives, hold mid-year check-ins and complete reviews for the people you appraise." />
      <Card>
        <Stack direction="row" sx={{ p: 1.5 }}>
          <TextField select size="small" label="Stage" value={status} onChange={(e) => setStatus(e.target.value)} sx={{ minWidth: 220 }}>
            <MenuItem value="">All</MenuItem>{Object.entries(APPRAISAL_STATUS).map(([k, v]) => <MenuItem key={k} value={k}>{v}</MenuItem>)}
          </TextField>
        </Stack>
        <AppraisalTable rows={q.data?.results || []} loading={q.isLoading} showEmployee />
      </Card>
    </>
  );
}
