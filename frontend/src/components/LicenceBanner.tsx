import { Alert, Button } from "@mui/material";
import { Link as RouterLink, useLocation } from "react-router-dom";
import { useApi } from "../api/hooks";
import { useAuth } from "../auth/AuthContext";

/** Self-hosted edition: licence warnings. Administrators see every warning; other staff only see that the
 *  system is read-only, because that's the one that affects them. */
export function LicenceBanner() {
  const { can } = useAuth();
  const { pathname } = useLocation();
  const { data } = useApi<{ state: string; read_only: boolean; message: string }>("/licence/status/", undefined,
    { refetchInterval: 30 * 60 * 1000 });
  if (!data || !data.message || pathname === "/admin/licence") return null;   // that page shows it already
  const admin = can("admin.settings");
  if (!admin && !data.read_only) return null;
  const severity = data.read_only ? "error" : data.state === "evaluation" ? "info" : "warning";
  return (
    <Alert severity={severity} sx={{ mb: 2 }}
      action={admin ? <Button color="inherit" size="small" component={RouterLink} to="/admin/licence">Licence</Button> : undefined}>
      {admin ? data.message : "The system is currently read-only. You can still view and export information; please contact your administrator."}
    </Alert>
  );
}
