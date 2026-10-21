import Add from "@mui/icons-material/Add";
import DeleteOutline from "@mui/icons-material/DeleteOutline";
import Send from "@mui/icons-material/Send";
import ThumbDownOutlined from "@mui/icons-material/ThumbDownOutlined";
import ThumbUpOutlined from "@mui/icons-material/ThumbUpOutlined";
import {
  Alert, Box, Button, Chip, CircularProgress, Grid2 as Grid, IconButton, Link, List, ListItemButton, ListItemText,
  Paper, Stack, TextField, Typography,
} from "@mui/material";
import { useEffect, useRef, useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import { api, errorMessage } from "../../api/client";
import { useApi, useInvalidate } from "../../api/hooks";
import { Loading, useToast } from "../../components/Feedback";
import { PageHeader, Section } from "../../components/PageHeader";

interface Msg { id: number; role: string; text: string; sources: { title: string; link: string }[]; helpful: boolean | null }
interface Conv { id: number; title: string }
interface Status { available: boolean; enabled: boolean; configured: boolean; mode: string; mode_label: string;
  daily_limit: number; used_today: number; disclaimer: string }

const EXAMPLES = ["How many days of annual leave do I have left?", "What is the maternity leave policy?",
  "Who is my request waiting on?", "How do I claim a travel allowance?"];

export default function Assistant() {
  const status = useApi<Status>("/assistant/status/");
  const convs = useApi<Conv[]>("/assistant/conversations/");
  const [active, setActive] = useState<number | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();
  const inv = useInvalidate();
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, busy]);

  const open = async (id: number) => {
    setActive(id); setError(null);
    setMessages((await api.get(`/assistant/conversations/${id}/`)).data.messages);
  };
  const send = async (q?: string) => {
    const message = (q ?? text).trim();
    if (!message) return;
    setBusy(true); setError(null); setText("");
    setMessages((m) => [...m, { id: -Date.now(), role: "user", text: message, sources: [], helpful: null }]);
    try {
      const { data } = await api.post("/assistant/ask/", { message, conversation: active });
      setActive(data.conversation);
      await open(data.conversation);
      inv("/assistant/");
    } catch (e) {
      setError(errorMessage(e));
      setMessages((m) => m.filter((x) => x.id > 0));
      setText(message);
    } finally { setBusy(false); }
  };
  const rate = async (m: Msg, helpful: boolean) => {
    await api.post(`/assistant/messages/${m.id}/feedback/`, { helpful });
    setMessages((all) => all.map((x) => (x.id === m.id ? { ...x, helpful } : x)));
    toast.ok("Thanks for the feedback.");
  };
  const remove = async (id: number) => {
    await api.delete(`/assistant/conversations/${id}/`);
    if (active === id) { setActive(null); setMessages([]); }
    inv("/assistant/");
  };

  if (status.isLoading) return <Loading />;
  const s = status.data;
  if (!s?.available) {
    return (
      <>
        <PageHeader title="HR assistant" />
        <Alert severity="info">{!s?.enabled ? "The AI assistant isn't enabled for your organization." : "The AI assistant isn't configured yet. Please contact your administrator."}</Alert>
      </>
    );
  }
  return (
    <>
      <PageHeader title="HR assistant" subtitle={`Ask about HR policies${s.mode === "hr_data" ? ", your leave, pay and requests" : ""}. ${s.used_today}/${s.daily_limit} questions used today.`}
        actions={<Button startIcon={<Add />} onClick={() => { setActive(null); setMessages([]); setError(null); }}>New conversation</Button>} />
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 3 }}>
          <Section title="Conversations" dense>
            {(convs.data || []).length === 0 && <Typography variant="body2" color="text.secondary">No conversations yet.</Typography>}
            <List dense disablePadding>
              {(convs.data || []).map((c) => (
                <ListItemButton key={c.id} selected={active === c.id} onClick={() => open(c.id)}>
                  <ListItemText primary={c.title || "Conversation"} primaryTypographyProps={{ noWrap: true }} />
                  <IconButton size="small" aria-label="Delete conversation" onClick={(e) => { e.stopPropagation(); remove(c.id); }}><DeleteOutline fontSize="small" /></IconButton>
                </ListItemButton>))}
            </List>
            <Typography variant="caption" color="text.secondary">Only you can see your conversations. They are deleted automatically after a while.</Typography>
          </Section>
        </Grid>
        <Grid size={{ xs: 12, md: 9 }}>
          <Paper variant="outlined" sx={{ p: 2, minHeight: 360, display: "flex", flexDirection: "column", gap: 1.5 }}>
            {messages.length === 0 && !busy && (
              <Box sx={{ textAlign: "center", my: "auto" }}>
                <Typography color="text.secondary" gutterBottom>Try asking:</Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap justifyContent="center">
                  {EXAMPLES.filter((_, i) => s.mode === "hr_data" || i % 2 === 1).map((e) => <Chip key={e} label={e} onClick={() => send(e)} />)}
                </Stack>
              </Box>
            )}
            {messages.map((m) => (
              <Box key={m.id} sx={{ alignSelf: m.role === "user" ? "flex-end" : "flex-start", maxWidth: "85%" }}>
                <Paper elevation={0} sx={{ p: 1.5, bgcolor: m.role === "user" ? "primary.main" : "action.hover", color: m.role === "user" ? "primary.contrastText" : "text.primary", borderRadius: 2 }}>
                  <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>{m.text}</Typography>
                </Paper>
                {m.role === "assistant" && (
                  <Stack direction="row" spacing={0.5} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mt: 0.5 }}>
                    {m.sources.map((src) => <Link key={src.link + src.title} component={RouterLink} to={src.link} variant="caption">{src.title}</Link>)}
                    {m.sources.length === 0 && <Typography variant="caption" color="text.secondary">No source cited. Check with HR.</Typography>}
                    <IconButton size="small" aria-label="Helpful" color={m.helpful === true ? "success" : "default"} onClick={() => rate(m, true)}><ThumbUpOutlined fontSize="inherit" /></IconButton>
                    <IconButton size="small" aria-label="Not helpful" color={m.helpful === false ? "error" : "default"} onClick={() => rate(m, false)}><ThumbDownOutlined fontSize="inherit" /></IconButton>
                  </Stack>
                )}
              </Box>
            ))}
            {busy && <Stack direction="row" spacing={1} alignItems="center"><CircularProgress size={16} /><Typography variant="body2" color="text.secondary">Thinking…</Typography></Stack>}
            <div ref={end} />
          </Paper>
          {error && <Alert severity="error" sx={{ mt: 1 }}>{error}</Alert>}
          <Stack direction="row" spacing={1} sx={{ mt: 1.5 }} component="form" onSubmit={(e) => { e.preventDefault(); send(); }}>
            <TextField fullWidth size="small" placeholder="Ask a question…" value={text} onChange={(e) => setText(e.target.value)} disabled={busy}
              inputProps={{ maxLength: 4000, "aria-label": "Your question" }} />
            <Button type="submit" variant="contained" endIcon={<Send />} disabled={busy || !text.trim()}>Ask</Button>
          </Stack>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>{s.disclaimer} Don't type ID, bank or medical details.</Typography>
        </Grid>
      </Grid>
    </>
  );
}
