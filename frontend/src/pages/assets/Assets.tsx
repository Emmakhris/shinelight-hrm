import { Alert, Button, Card, CardContent, Grid2 as Grid, Tab, Tabs } from "@mui/material";
import { useState } from "react";
import { api } from "../../api/client";
import { post, useApi, useInvalidate } from "../../api/hooks";
import { useAuth } from "../../auth/AuthContext";
import { DataTable } from "../../components/DataTable";
import { StatusChip, useToast } from "../../components/Feedback";
import { FormDialog } from "../../components/FormDialog";
import { Kpi, PageHeader } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtDate, fmtMoney } from "../../utils";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
const opts = (p: string[][]) => p.map(([value, label]) => ({ value, label }));
const CONDITIONS = opts([["new", "New"], ["good", "Good"], ["fair", "Fair / worn"], ["damaged", "Damaged"], ["lost", "Lost"]]);
const STATUS = opts([["available", "Available"], ["assigned", "Assigned"], ["in_repair", "In repair"], ["lost", "Lost"], ["damaged", "Damaged / unusable"], ["retired", "Retired / disposed"]]);

export default function Assets() {
  const { can } = useAuth();
  const manage = can("assets.manage");
  const [tab, setTab] = useState(0);
  const [issuing, setIssuing] = useState(false);
  const [receiving, setReceiving] = useState<R | null>(null);
  const [transfer, setTransfer] = useState<R | null>(null);
  const dash = useApi<R>("/assets/dashboard/");
  const d = dash.data || {};
  const toast = useToast();
  const inv = useInvalidate();
  const refresh = () => inv("/assets/");
  return (
    <>
      <PageHeader title="Assets & equipment" subtitle="Laptops, phones, access cards, uniforms and PPE issued to staff, and recovery on exit."
        actions={manage && <Button variant="contained" onClick={() => setIssuing(true)}>Issue item</Button>} />
      <Grid container spacing={2} sx={{ mb: 2 }}>
        {[["Items with staff", d.assigned], ["Not yet acknowledged", d.unacknowledged], ["Overdue for return", d.overdue], ["Held by leavers", d.with_leavers, "#b45309"],
          ["Lost / damaged", d.lost_or_damaged], ["Recoveries pending", d.recovery_pending]].map(([l, v, color]) => (
          <Grid key={l} size={{ xs: 6, md: 2 }}><Kpi label={l} value={v ?? "—"} color={v ? color : undefined} /></Grid>))}
      </Grid>
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}><Tab label="Issued items" /><Tab label="Asset register" /><Tab label={`Recovery from leavers (${d.with_leavers ?? 0})`} /><Tab label="Categories" /></Tabs>
      <Card>
        {tab === 0 && <ResourcePage embedded title="Assignment" url="/assets/assignments/" params={{ open: 1 }} canCreate={false} canEdit={false}
          columns={[{ key: "employee_name", label: "Employee", render: (r) => <><b>{r.employee_name}</b><br /><small>{r.department_name}</small></> },
            { key: "item", label: "Item", render: (r) => <>{r.item}{r.quantity > 1 && ` × ${r.quantity}`}<br /><small>{r.tag ? `${r.tag} · ${r.serial_number || ""}` : r.category_name}</small></> },
            { key: "issued_on", label: "Issued", render: (r) => fmtDate(r.issued_on) },
            { key: "ack", label: "Acknowledged", render: (r) => (r.acknowledged_at ? fmtDate(r.acknowledged_at) : <StatusChip value="pending" label="No" />) },
            { key: "incident_report", label: "Reported", hideOnMobile: true, render: (r) => <small>{r.incident_report}</small> }]}
          rowActions={(r) => manage && r.returnable && <><Button size="small" onClick={() => setReceiving(r)}>Receive back</Button>{r.tag && <Button size="small" onClick={() => setTransfer(r)}>Transfer</Button>}</>} />}
        {tab === 1 && <ResourcePage embedded title="Asset" url="/assets/items/" writePerm="assets.manage" createLabel="Add asset"
          columns={[{ key: "tag", label: "Inventory ID", render: (r) => <b>{r.tag}</b> }, { key: "description", label: "Item", render: (r) => <>{r.description}<br /><small>{r.category_name} · {r.serial_number}</small></> },
            { key: "holder_name", label: "Held by" }, { key: "replacement_value", label: "Value", align: "right", render: (r) => fmtMoney(r.replacement_value) },
            { key: "status", label: "Status", render: (r) => <StatusChip value={r.status === "available" ? "active" : r.status === "assigned" ? "in_progress" : r.status} label={r.status} /> }]}
          fields={[{ name: "tag", label: "Inventory ID", required: true, width: 6 }, { name: "category", label: "Category", type: "ref", ref: "/assets/categories/", required: true, width: 6 },
            { name: "description", label: "Make and model", required: true }, { name: "serial_number", label: "Serial number", width: 6 },
            { name: "external_ref", label: "IT / procurement system ID", width: 6 }, { name: "purchase_date", label: "Purchase date", type: "date", width: 4 },
            { name: "cost", label: "Cost", type: "number", width: 4 }, { name: "replacement_value", label: "Replacement value", type: "number", width: 4 },
            { name: "location", label: "Location", type: "ref", ref: "/org/locations/", width: 6 }, { name: "status", label: "Status", type: "select", options: STATUS, width: 6 },
            { name: "notes", label: "Notes", type: "textarea" }]} defaults={{ status: "available" }} />}
        {tab === 2 && <CardContent>
          <Alert severity="info" sx={{ mb: 1 }}>Items still held by people who are leaving or have left. Exit clearance cannot be completed until they are returned or recovered.</Alert>
          <DataTable dense rows={d.leavers || []} rowKey={(r) => r.assignment} emptyTitle="Nothing outstanding" columns={[
            { key: "employee", label: "Employee" }, { key: "exit_date", label: "Exit date", render: (r) => fmtDate(r.exit_date) },
            { key: "item", label: "Item", render: (r) => `${r.item}${r.tag ? ` (${r.tag})` : ""}` }, { key: "value", label: "Value", align: "right", render: (r) => (r.value ? fmtMoney(r.value) : "—") }]} />
        </CardContent>}
        {tab === 3 && <ResourcePage embedded title="Category" url="/assets/categories/" writePerm="assets.manage" searchable={false}
          columns={[{ key: "name", label: "Category" }, { key: "owner", label: "Issued by" }, { key: "is_returnable", label: "Returned on exit", render: (r) => (r.is_returnable ? "Yes" : "No") },
            { key: "is_tracked", label: "Tagged", render: (r) => (r.is_tracked ? "Yes" : "No") }]}
          fields={[{ name: "name", label: "Name", required: true, width: 8 }, { name: "code", label: "Code", required: true, width: 4 },
            { name: "owner", label: "Issued by", type: "select", options: opts([["it", "IT"], ["admin", "Administration / facilities"]]) },
            { name: "is_returnable", label: "Must be returned", type: "checkbox", width: 6 }, { name: "is_tracked", label: "Individually tagged", type: "checkbox", width: 6 }]}
          defaults={{ owner: "admin", is_returnable: true, is_tracked: true }} />}
      </Card>
      <FormDialog open={issuing} title="Issue item" onClose={() => setIssuing(false)} initial={{ quantity: 1, condition_out: "good" }}
        intro={<Alert severity="info">Choose a tagged asset, or a category and description for uniforms and PPE. The employee is asked to acknowledge receipt.</Alert>}
        fields={[{ name: "employee", label: "Employee", type: "ref", ref: "/employees/", required: true },
          { name: "asset", label: "Tagged asset", type: "ref", ref: "/assets/items/", refParams: { status: "available" }, refLabel: (a) => `${a.tag} — ${a.description}` },
          { name: "category", label: "…or category (untagged items)", type: "ref", ref: "/assets/categories/", width: 6, hidden: (v) => !!v.asset },
          { name: "item", label: "Item description", width: 6, hidden: (v) => !!v.asset },
          { name: "quantity", label: "Quantity", type: "number", width: 4, hidden: (v) => !!v.asset },
          { name: "condition_out", label: "Condition", type: "select", options: CONDITIONS.slice(0, 3), width: 4 },
          { name: "due_back", label: "Due back (optional)", type: "date", width: 4 }, { name: "notes", label: "Notes" }]}
        onSubmit={async (v) => { await api.post("/assets/assignments/", v); toast.ok("Issued."); refresh(); }} />
      <FormDialog open={!!receiving} title={`Receive back: ${receiving?.item}`} onClose={() => setReceiving(null)} initial={{ condition: "good", to_payroll: false }}
        intro={receiving?.incident_report ? <Alert severity="warning">{receiving.incident_report}</Alert> : undefined}
        fields={[{ name: "condition", label: "Condition", type: "select", required: true, options: CONDITIONS },
          { name: "recovery_amount", label: "Amount to recover (default: replacement value)", type: "number", hidden: (v) => !["damaged", "lost"].includes(String(v.condition)) },
          { name: "to_payroll", label: "Recover through the next payroll", type: "checkbox", hidden: (v) => !["damaged", "lost"].includes(String(v.condition)) },
          { name: "notes", label: "Notes", type: "textarea" }]}
        onSubmit={async (v) => { await post(`/assets/assignments/${receiving?.id}/receive/`, v); toast.ok("Received."); refresh(); }} />
      <FormDialog open={!!transfer} title={`Transfer ${transfer?.tag}`} onClose={() => setTransfer(null)}
        fields={[{ name: "employee", label: "New holder", type: "ref", ref: "/employees/", required: true }, { name: "notes", label: "Notes" }]}
        onSubmit={async (v) => { await post(`/assets/assignments/${transfer?.id}/transfer/`, v); toast.ok("Transferred."); refresh(); }} />
    </>
  );
}
