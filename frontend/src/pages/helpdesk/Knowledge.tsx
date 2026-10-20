import ThumbDown from "@mui/icons-material/ThumbDownOffAlt";
import ThumbUp from "@mui/icons-material/ThumbUpOffAlt";
import { Button, Card, CardContent, Grid2 as Grid, InputAdornment, List, ListItemButton, ListItemText, Stack, TextField, Typography } from "@mui/material";
import Search from "@mui/icons-material/Search";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { post, useApi, useList } from "../../api/hooks";
import { Empty, useToast } from "../../components/Feedback";
import { PageHeader } from "../../components/PageHeader";

interface A { id: number; title: string; body: string; category_name: string | null; views: number }

export default function Knowledge() {
  const [params] = useSearchParams();
  const [search, setSearch] = useState("");
  const [sel, setSel] = useState<number | null>(params.get("article") ? Number(params.get("article")) : null);
  const list = useList<A>("/helpdesk/articles/", { search });
  const article = useApi<A>(sel ? `/helpdesk/articles/${sel}/` : null);
  const toast = useToast();
  return (
    <>
      <PageHeader title="HR knowledge base" subtitle="Answers to common HR questions and procedures" />
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 4 }}>
          <Card>
            <TextField fullWidth placeholder="Search articles…" value={search} onChange={(e) => setSearch(e.target.value)} sx={{ p: 1.5 }}
              InputProps={{ startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment> }} />
            <List dense>
              {list.items.map((a) => <ListItemButton key={a.id} selected={sel === a.id} onClick={() => setSel(a.id)}>
                <ListItemText primary={a.title} secondary={a.category_name} /></ListItemButton>)}
            </List>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, md: 8 }}>
          {article.data ? (
            <Card><CardContent>
              <Typography variant="h6" gutterBottom>{article.data.title}</Typography>
              <Typography sx={{ whiteSpace: "pre-wrap" }}>{article.data.body}</Typography>
              <Stack direction="row" spacing={1} sx={{ mt: 3 }} alignItems="center">
                <Typography variant="body2" color="text.secondary">Was this helpful?</Typography>
                <Button size="small" startIcon={<ThumbUp />} onClick={async () => { await post(`/helpdesk/articles/${sel}/helpful/`, { helpful: true }); toast.ok("Thanks!"); }}>Yes</Button>
                <Button size="small" startIcon={<ThumbDown />} onClick={async () => { await post(`/helpdesk/articles/${sel}/helpful/`, { helpful: false }); toast.info("Thanks — raise a request if you still need help."); }}>No</Button>
              </Stack>
            </CardContent></Card>
          ) : <Card><Empty title="Select an article" /></Card>}
        </Grid>
      </Grid>
    </>
  );
}
