import { Alert, Autocomplete, Box, Button, Checkbox, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel,
  Grid2 as Grid, MenuItem, TextField, Typography } from "@mui/material";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { errorMessage, fieldErrors } from "../api/client";
import { useList } from "../api/hooks";

export type FieldType = "text" | "number" | "date" | "datetime" | "time" | "select" | "ref" | "multiref" | "checkbox"
  | "textarea" | "json" | "file" | "email" | "password" | "color";

export interface FieldDef {
  name: string;
  label: string;
  type?: FieldType;
  required?: boolean;
  options?: { value: string | number; label: string }[];
  ref?: string; // API url for ref/multiref
  refLabel?: string | ((o: Record<string, unknown>) => string);
  refParams?: Record<string, string | number>;
  helper?: string;
  width?: 12 | 6 | 4 | 3 | 8;
  hidden?: (values: Record<string, unknown>) => boolean;
  disabled?: boolean;
  placeholder?: string;
}

function RefField({ f, value, onChange, error }: { f: FieldDef; value: unknown; onChange: (v: unknown) => void; error?: string }) {
  const { items, isLoading } = useList<Record<string, unknown>>(f.ref || null, f.refParams);
  const labelOf = (o: Record<string, unknown>) =>
    typeof f.refLabel === "function" ? f.refLabel(o)
      : String(o[f.refLabel || "name"] ?? o.full_name ?? o.title ?? o.code ?? o.username ?? o.id);
  if (f.type === "multiref") {
    const ids = (value as (number | string)[]) || [];
    const selected = items.filter((o) => ids.includes(o.id as number));
    return (
      <Autocomplete multiple options={items} loading={isLoading} value={selected} getOptionLabel={labelOf}
        isOptionEqualToValue={(a, b) => a.id === b.id} onChange={(_, v) => onChange(v.map((o) => o.id))}
        renderInput={(p) => <TextField {...p} label={f.label} required={f.required && !ids.length} error={!!error} helperText={error || f.helper} />} />
    );
  }
  const selected = items.find((o) => o.id === value) || null;
  return (
    <Autocomplete options={items} loading={isLoading} value={selected} getOptionLabel={labelOf}
      isOptionEqualToValue={(a, b) => a.id === b.id} onChange={(_, v) => onChange(v ? v.id : null)} disabled={f.disabled}
      renderInput={(p) => <TextField {...p} label={f.label} required={f.required} error={!!error} helperText={error || f.helper} />} />
  );
}

export function FormFields({ fields, values, setValue, errors }: {
  fields: FieldDef[]; values: Record<string, unknown>; setValue: (k: string, v: unknown) => void; errors: Record<string, string>;
}) {
  return (
    <Grid container spacing={2}>
      {fields.filter((f) => !f.hidden?.(values)).map((f) => {
        const err = errors[f.name];
        const v = values[f.name];
        const common = { label: f.label, required: f.required, fullWidth: true, error: !!err, helperText: err || f.helper,
          disabled: f.disabled, placeholder: f.placeholder };
        let input: ReactNode;
        switch (f.type) {
          case "checkbox":
            input = <FormControlLabel control={<Checkbox checked={!!v} onChange={(e) => setValue(f.name, e.target.checked)} />} label={f.label} />;
            break;
          case "select":
            input = (
              <TextField select {...common} value={v ?? ""} onChange={(e) => setValue(f.name, e.target.value)}>
                {!f.required && <MenuItem value="">—</MenuItem>}
                {(f.options || []).map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
              </TextField>
            );
            break;
          case "ref":
          case "multiref":
            input = <RefField f={f} value={v} onChange={(nv) => setValue(f.name, nv)} error={err} />;
            break;
          case "textarea":
            input = <TextField {...common} multiline minRows={3} value={v ?? ""} onChange={(e) => setValue(f.name, e.target.value)} />;
            break;
          case "json":
            input = <TextField {...common} multiline minRows={3} value={typeof v === "string" ? v : JSON.stringify(v ?? null, null, 1)}
              onChange={(e) => setValue(f.name, e.target.value)} InputProps={{ sx: { fontFamily: "monospace", fontSize: 13 } }} />;
            break;
          case "file":
            input = (
              <Box>
                <Button variant="outlined" component="label" fullWidth>
                  {v instanceof File ? v.name : f.label}
                  <input hidden type="file" onChange={(e) => setValue(f.name, e.target.files?.[0] || null)} />
                </Button>
                {(err || f.helper) && <Typography variant="caption" color={err ? "error" : "text.secondary"}>{err || f.helper}</Typography>}
              </Box>
            );
            break;
          default: {
            const type = f.type === "datetime" ? "datetime-local" : f.type || "text";
            input = <TextField {...common} type={type} value={v ?? ""} onChange={(e) => setValue(f.name, e.target.value)}
              InputLabelProps={["date", "datetime", "time", "color"].includes(f.type || "") ? { shrink: true } : undefined}
              inputProps={f.type === "number" ? { step: "any" } : undefined} />;
          }
        }
        return <Grid key={f.name} size={{ xs: 12, sm: f.width || 12 }}>{input}</Grid>;
      })}
    </Grid>
  );
}

function normalize(fields: FieldDef[], values: Record<string, unknown>) {
  const out: Record<string, unknown> = {};
  let hasFile = false;
  for (const f of fields) {
    if (f.hidden?.(values)) continue;
    let v = values[f.name];
    if (f.type === "file") {
      if (v instanceof File) hasFile = true;
      else continue;
    }
    if (f.type === "json" && typeof v === "string") {
      try { v = v.trim() ? JSON.parse(v) : null; } catch { throw new Error(`${f.label}: invalid JSON`); }
    }
    if ((f.type === "number" || f.type === "date" || f.type === "ref" || f.type === "datetime" || f.type === "time") && v === "") v = null;
    out[f.name] = v;
  }
  if (!hasFile) return out;
  const fd = new FormData();
  for (const [k, v] of Object.entries(out)) {
    if (v === null || v === undefined) continue;
    if (Array.isArray(v)) v.forEach((x) => fd.append(k, String(x)));
    else fd.append(k, v instanceof File ? v : String(v));
  }
  return fd;
}

export function FormDialog({ open, title, fields, initial, onClose, onSubmit, submitLabel = "Save", maxWidth = "sm", intro }: {
  open: boolean; title: string; fields: FieldDef[]; initial?: Record<string, unknown>; onClose: () => void;
  onSubmit: (data: Record<string, unknown> | FormData) => Promise<unknown>; submitLabel?: string;
  maxWidth?: "xs" | "sm" | "md" | "lg"; intro?: ReactNode;
}) {
  const defaults = useMemo(() => {
    const d: Record<string, unknown> = {};
    fields.forEach((f) => { d[f.name] = f.type === "checkbox" ? false : f.type === "multiref" ? [] : ""; });
    return d;
  }, [fields]);
  const [values, setValues] = useState<Record<string, unknown>>({ ...defaults, ...initial });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setValues({ ...defaults, ...initial });
      setErrors({});
      setError(null);
    }
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setErrors({});
    try {
      await onSubmit(normalize(fields, values));
      onClose();
    } catch (err) {
      const fe = fieldErrors(err);
      setErrors(fe);
      setError(err instanceof Error && !("response" in err) ? err.message : errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth={maxWidth}>
      <form onSubmit={submit}>
        <DialogTitle>{title}</DialogTitle>
        <DialogContent dividers>
          {intro && <Box sx={{ mb: 2 }}>{intro}</Box>}
          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
          <FormFields fields={fields} values={values} errors={errors}
            setValue={(k, v) => setValues((s) => ({ ...s, [k]: v }))} />
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="contained" disabled={busy}>{submitLabel}</Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
