import { Box, Breadcrumbs, Card, CardContent, Link, Stack, Typography } from "@mui/material";
import type { ReactNode } from "react";
import { Link as RouterLink } from "react-router-dom";

export function PageHeader({ title, subtitle, actions, crumbs }: {
  title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; crumbs?: { label: string; to?: string }[];
}) {
  return (
    <Box sx={{ mb: 2.5 }}>
      {crumbs && (
        <Breadcrumbs sx={{ mb: 0.5, fontSize: 13 }}>
          {crumbs.map((c) => c.to ? (
            <Link key={c.label} component={RouterLink} to={c.to} underline="hover" color="inherit">{c.label}</Link>
          ) : <Typography key={c.label} fontSize={13} color="text.primary">{c.label}</Typography>)}
        </Breadcrumbs>
      )}
      <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" alignItems={{ sm: "center" }} spacing={1}>
        <Box>
          <Typography variant="h5" component="h1">{title}</Typography>
          {subtitle && <Typography variant="body2" color="text.secondary">{subtitle}</Typography>}
        </Box>
        {actions && <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>{actions}</Stack>}
      </Stack>
    </Box>
  );
}

export function Section({ title, actions, children, dense }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; dense?: boolean }) {
  return (
    <Card sx={{ mb: 2 }}>
      {(title || actions) && (
        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ px: 2, pt: 1.5 }}>
          <Typography variant="subtitle1" fontWeight={650}>{title}</Typography>
          <Stack direction="row" spacing={1}>{actions}</Stack>
        </Stack>
      )}
      <CardContent sx={dense ? { p: 0, "&:last-child": { pb: 0 } } : undefined}>{children}</CardContent>
    </Card>
  );
}

export function Kpi({ label, value, hint, color, onClick }: { label: string; value: ReactNode; hint?: ReactNode;
  color?: string; onClick?: () => void }) {
  return (
    <Card sx={{ height: "100%", cursor: onClick ? "pointer" : undefined, "&:hover": onClick ? { borderColor: "primary.main" } : {} }}
      onClick={onClick}>
      <CardContent>
        <Typography variant="body2" color="text.secondary">{label}</Typography>
        <Typography variant="h5" sx={{ color: color || "text.primary", my: 0.5 }}>{value}</Typography>
        {hint && <Typography variant="caption" color="text.secondary">{hint}</Typography>}
      </CardContent>
    </Card>
  );
}

export function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary">{label}</Typography>
      <Typography variant="body2" sx={{ wordBreak: "break-word" }}>{value === null || value === undefined || value === "" ? "—" : value}</Typography>
    </Box>
  );
}
