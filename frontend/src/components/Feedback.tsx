import { Alert, Box, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, Snackbar,
  Stack, TextField, Typography } from "@mui/material";
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { errorMessage } from "../api/client";
import { STATUS_COLORS, titleCase } from "../utils";

type Toast = { message: string; severity: "success" | "error" | "info" | "warning" };
const ToastCtx = createContext<(t: Toast | string, severity?: Toast["severity"]) => void>(() => undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<Toast | null>(null);
  const show = useCallback((t: Toast | string, severity: Toast["severity"] = "success") =>
    setToast(typeof t === "string" ? { message: t, severity } : t), []);
  return (
    <ToastCtx.Provider value={show}>
      {children}
      <Snackbar open={!!toast} autoHideDuration={5000} onClose={() => setToast(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}>
        {toast ? <Alert severity={toast.severity} variant="filled" onClose={() => setToast(null)}>{toast.message}</Alert> : undefined}
      </Snackbar>
    </ToastCtx.Provider>
  );
}

export function useToast() {
  const show = useContext(ToastCtx);
  return {
    ok: (m: string) => show(m, "success"),
    info: (m: string) => show(m, "info"),
    error: (e: unknown) => show(errorMessage(e), "error"),
  };
}

export function StatusChip({ value, label }: { value?: string | null; label?: string }) {
  if (!value) return null;
  return <Chip label={label || titleCase(value)} color={STATUS_COLORS[value] || "default"} variant="outlined" />;
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <Stack alignItems="center" justifyContent="center" spacing={1} sx={{ py: 6 }}>
      <CircularProgress size={28} />
      <Typography variant="body2" color="text.secondary">{label}</Typography>
    </Stack>
  );
}

export function Empty({ title = "Nothing here yet", hint }: { title?: string; hint?: string }) {
  return (
    <Box sx={{ py: 5, textAlign: "center" }}>
      <Typography color="text.secondary" fontWeight={600}>{title}</Typography>
      {hint && <Typography variant="body2" color="text.secondary">{hint}</Typography>}
    </Box>
  );
}

export function ErrorAlert({ error }: { error: unknown }) {
  if (!error) return null;
  return <Alert severity="error" sx={{ my: 1 }}>{errorMessage(error)}</Alert>;
}

interface ConfirmProps {
  open: boolean;
  title: string;
  message?: ReactNode;
  confirmLabel?: string;
  color?: "primary" | "error" | "success" | "warning";
  comment?: "none" | "optional" | "required";
  onClose: () => void;
  onConfirm: (comment: string) => Promise<unknown> | void;
}

export function ConfirmDialog({ open, title, message, confirmLabel = "Confirm", color = "primary", comment = "none",
  onClose, onConfirm }: ConfirmProps) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const submit = async () => {
    setBusy(true);
    setErr(null);
    try {
      await onConfirm(text);
      setText("");
      onClose();
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        {message && <Box sx={{ mb: 2 }}>{message}</Box>}
        {comment !== "none" && (
          <TextField label={comment === "required" ? "Comment (required)" : "Comment"} value={text} multiline minRows={2}
            onChange={(e) => setText(e.target.value)} fullWidth autoFocus />
        )}
        <ErrorAlert error={err} />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" color={color} disabled={busy || (comment === "required" && !text.trim())}
          onClick={submit}>{confirmLabel}</Button>
      </DialogActions>
    </Dialog>
  );
}
