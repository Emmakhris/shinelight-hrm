import { Box, Button, Divider, List, ListItemButton, ListItemText, Popover, Stack, Typography } from "@mui/material";
import { useNavigate } from "react-router-dom";
import { post, useInvalidate, useList } from "../api/hooks";
import { fmtDateTime } from "../utils";
import { Empty } from "./Feedback";

interface N { id: number; title: string; body: string; link: string; is_read: boolean; created_at: string }

export default function NotificationsPopover({ anchor, onClose }: { anchor: HTMLElement | null; onClose: () => void }) {
  const { items } = useList<N>(anchor ? "/notifications/" : null, { page_size: 20 });
  const inv = useInvalidate();
  const nav = useNavigate();
  const open = async (n: N) => {
    if (!n.is_read) await post(`/notifications/${n.id}/read/`);
    inv("/notifications/");
    onClose();
    if (n.link) nav(n.link);
  };
  return (
    <Popover open={!!anchor} anchorEl={anchor} onClose={onClose} anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
      transformOrigin={{ vertical: "top", horizontal: "right" }} slotProps={{ paper: { sx: { width: 380, maxWidth: "95vw" } } }}>
      <Stack direction="row" alignItems="center" sx={{ px: 2, py: 1 }}>
        <Typography fontWeight={650} flex={1}>Notifications</Typography>
        <Button size="small" onClick={async () => { await post("/notifications/read-all/"); inv("/notifications/"); }}>
          Mark all read
        </Button>
      </Stack>
      <Divider />
      {items.length === 0 ? <Empty title="You're all caught up" /> : (
        <List dense sx={{ maxHeight: 420, overflowY: "auto" }}>
          {items.map((n) => (
            <ListItemButton key={n.id} onClick={() => open(n)} sx={{ bgcolor: n.is_read ? undefined : "rgba(15,61,94,0.06)" }}>
              <ListItemText primary={<Box component="span" fontWeight={n.is_read ? 400 : 650}>{n.title}</Box>}
                secondary={<>{n.body}<br /><Typography component="span" variant="caption">{fmtDateTime(n.created_at)}</Typography></>} />
            </ListItemButton>
          ))}
        </List>
      )}
    </Popover>
  );
}
