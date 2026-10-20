import { Alert, Button, Card, CardContent, Stack, TextField, Typography } from "@mui/material";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, errorMessage } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";

export default function ChangePassword() {
  const { me, refresh } = useAuth();
  const nav = useNavigate();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (next !== confirm) return setError("The new passwords do not match.");
    try {
      await api.post("/auth/change-password/", { current_password: current, new_password: next });
      await refresh();
      nav("/");
    } catch (err) {
      setError(errorMessage(err));
    }
  };
  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>Change password</Typography>
        {me?.must_change_password && <Alert severity="info" sx={{ mb: 2 }}>Please set a new password before continuing.</Alert>}
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <form onSubmit={submit}>
          <Stack spacing={2}>
            <TextField type="password" label="Current password" value={current} onChange={(e) => setCurrent(e.target.value)} required autoComplete="current-password" />
            <TextField type="password" label="New password" value={next} onChange={(e) => setNext(e.target.value)} required
              helperText="At least 10 characters. Avoid names, dates and common words." autoComplete="new-password" />
            <TextField type="password" label="Confirm new password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required autoComplete="new-password" />
            <Button type="submit" variant="contained">Update password</Button>
          </Stack>
        </form>
      </CardContent>
    </Card>
  );
}
