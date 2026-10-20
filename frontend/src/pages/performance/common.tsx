import { MenuItem, TextField, Tooltip } from "@mui/material";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export const APPRAISAL_STATUS: Record<string, string> = {
  objective_setting: "Setting objectives", objectives_pending: "Objectives awaiting approval",
  objectives_returned: "Objectives returned", objectives_agreed: "Objectives agreed", self_review: "Self-assessment",
  manager_review: "Manager review", calibration: "Calibration", acknowledgement: "Awaiting acknowledgment",
  completed: "Completed", cancelled: "Cancelled",
};

export const CYCLE_STATUS: Record<string, string> = {
  draft: "Draft", goal_setting: "Objective setting", in_progress: "In progress (mid-year)", review: "Year-end review",
  calibration: "Calibration", closed: "Closed",
};

export const PROGRESS = [["on_track", "On track"], ["at_risk", "At risk"], ["off_track", "Off track"], ["done", "Achieved"]]
  .map(([value, label]) => ({ value, label }));

export function ratingLabel(scale: R[] | undefined, v?: number | null) {
  if (v === null || v === undefined) return "—";
  const l = (scale || []).find((x) => Number(x.value) === Number(v));
  return l ? `${v} – ${l.label}` : String(v);
}

export function RatingSelect({ scale, value, onChange, disabled, label = "Rating" }: {
  scale: R[]; value?: number | null; onChange: (v: number) => void; disabled?: boolean; label?: string;
}) {
  return (
    <TextField select size="small" label={label} value={value ?? ""} disabled={disabled} sx={{ minWidth: 170 }}
      onChange={(e) => onChange(Number(e.target.value))}>
      {[...scale].sort((a, b) => b.value - a.value).map((l) => (
        <MenuItem key={l.value} value={l.value}>
          <Tooltip describeChild title={l.description || ""} placement="right"><span>{l.value} – {l.label}</span></Tooltip>
        </MenuItem>
      ))}
    </TextField>
  );
}
