import PushPin from "@mui/icons-material/PushPin";
import { Button, Card, CardContent, Chip, Stack, Typography } from "@mui/material";
import { download } from "../../api/client";
import { post, useApi, useInvalidate, useList } from "../../api/hooks";
import { Empty, Loading, useToast } from "../../components/Feedback";
import { PageHeader, Section } from "../../components/PageHeader";
import { fmtDate } from "../../utils";

export default function Announcements() {
  const { items, isLoading } = useList<Record<string, unknown>>("/announcements/");
  const policies = useApi<Record<string, unknown>[]>("/documents/policies/");
  const inv = useInvalidate();
  const toast = useToast();
  return (
    <>
      <PageHeader title="Announcements & policies" />
      <Section title="Policies and handbooks" dense>
        {(policies.data || []).length === 0 ? <Empty title="No policies published" /> : (policies.data || []).map((p) => (
          <Stack key={p.id as number} direction={{ xs: "column", sm: "row" }} alignItems={{ sm: "center" }} spacing={1} sx={{ px: 2, py: 1.5, borderBottom: "1px solid #eef1f4" }}>
            <Typography flex={1} fontWeight={600}>{p.title as string}</Typography>
            <Button size="small" onClick={() => download(`/documents/${p.id}/download/`)}>Read</Button>
            {!!p.requires_acknowledgment && (p.acknowledged ? <Chip color="success" variant="outlined" label="Acknowledged" /> : (
              <Button size="small" variant="contained" onClick={async () => { await post(`/documents/${p.id}/acknowledge/`); toast.ok("Thank you — acknowledgment recorded."); inv("/documents/", "/me/"); }}>
                I have read and understood
              </Button>
            ))}
          </Stack>
        ))}
      </Section>
      {isLoading ? <Loading /> : items.length === 0 ? <Card><Empty title="No announcements" /></Card> : items.map((a) => (
        <Card key={a.id as number} sx={{ mb: 1.5 }}>
          <CardContent>
            <Stack direction="row" alignItems="center" spacing={1}>
              {!!a.is_pinned && <PushPin fontSize="small" color="secondary" />}
              <Typography variant="h6" flex={1}>{a.title as string}</Typography>
              <Typography variant="caption" color="text.secondary">{fmtDate(a.publish_at as string)}</Typography>
            </Stack>
            <Typography sx={{ whiteSpace: "pre-wrap", mt: 1 }}>{a.body as string}</Typography>
            {!!a.requires_acknowledgment && (a.acknowledged ? <Chip sx={{ mt: 1 }} color="success" variant="outlined" label="Acknowledged" /> : (
              <Button sx={{ mt: 1 }} variant="outlined" onClick={async () => { await post(`/announcements/${a.id}/acknowledge/`); inv("/announcements/"); }}>Acknowledge</Button>
            ))}
          </CardContent>
        </Card>
      ))}
    </>
  );
}
