import { Avatar, Box, Card, Collapse, IconButton, Stack, TextField, Typography } from "@mui/material";
import ChevronRight from "@mui/icons-material/ChevronRight";
import ExpandMore from "@mui/icons-material/ExpandMore";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApi } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { ErrorAlert, Loading } from "../../components/Feedback";
import { PageHeader } from "../../components/PageHeader";

interface Node { id: number; name: string; title: string; department: string; photo: string | null; children: Node[] }

function count(n: Node): number { return n.children.reduce((s, c) => s + 1 + count(c), 0); }
function matches(n: Node, q: string): boolean {
  return !q || n.name.toLowerCase().includes(q) || n.title.toLowerCase().includes(q) || n.children.some((c) => matches(c, q));
}

function NodeView({ n, depth, q }: { n: Node; depth: number; q: string }) {
  const [open, setOpen] = useState(depth < 2);
  const nav = useNavigate();
  const { can } = useAuth();
  if (!matches(n, q)) return null;
  return (
    <Box sx={{ ml: depth ? 3 : 0, borderLeft: depth ? "2px solid #e3e8ef" : undefined, pl: depth ? 1.5 : 0 }}>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ py: 0.75 }}>
        <IconButton size="small" disabled={!n.children.length} onClick={() => setOpen(!open)}>
          {n.children.length ? (open || q ? <ExpandMore fontSize="small" /> : <ChevronRight fontSize="small" />) : <Box width={20} />}
        </IconButton>
        <Avatar src={n.photo || undefined} sx={{ width: 32, height: 32, fontSize: 13, bgcolor: "primary.main" }}>{n.name[0]}</Avatar>
        <Box sx={{ cursor: can("employees.view") ? "pointer" : undefined }} onClick={() => can("employees.view") && nav(`/employees/${n.id}`)}>
          <Typography variant="body2" fontWeight={650}>{n.name}</Typography>
          <Typography variant="caption" color="text.secondary">{n.title} · {n.department}{n.children.length ? ` · ${count(n)} below` : ""}</Typography>
        </Box>
      </Stack>
      <Collapse in={open || !!q}>
        {n.children.map((c) => <NodeView key={c.id} n={c} depth={depth + 1} q={q} />)}
      </Collapse>
    </Box>
  );
}

export default function OrgChart() {
  const { data, isLoading, error } = useApi<Node[]>("/org/chart/");
  const [q, setQ] = useState("");
  return (
    <>
      <PageHeader title="Organization chart" subtitle="Live reporting lines built from supervisor relationships"
        actions={<TextField placeholder="Find a person or title…" value={q} onChange={(e) => setQ(e.target.value.toLowerCase())} />} />
      <ErrorAlert error={error} />
      <Card sx={{ p: 2, overflowX: "auto" }}>
        {isLoading ? <Loading /> : (data || []).map((n) => <NodeView key={n.id} n={n} depth={0} q={q} />)}
      </Card>
    </>
  );
}
