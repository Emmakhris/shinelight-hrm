import { Alert, Card, Chip, Grid2 as Grid, List, ListItemButton, ListItemText, Typography } from "@mui/material";
import { useState } from "react";
import { useApi, useList } from "../../api/hooks";
import { PageHeader, Section } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";
import { titleCase } from "../../utils";

interface Def { id: number; name: string; request_type: string; request_type_label: string; priority: number; is_active: boolean; version: number; conditions: unknown }

const APPROVERS = [{ value: "supervisor", label: "Employee's supervisor" }, { value: "supervisor_2", label: "Supervisor's supervisor" },
  { value: "dept_head", label: "Head of department" }, { value: "role", label: "Users holding a role" }, { value: "user", label: "Specific user" }];

export default function Workflows() {
  const defs = useList<Def>("/workflow/definitions/");
  const types = useApi<{ code: string; label: string; context_fields: string[] }[]>("/workflow/definitions/request-types/");
  const [sel, setSel] = useState<number | null>(null);
  const def = defs.items.find((d) => d.id === sel) || defs.items[0];
  const typeOpts = (types.data || []).map((t) => ({ value: t.code, label: t.label }));
  return (
    <>
      <PageHeader title="Approval workflows" subtitle="Configure who approves what — no code changes needed. Steps with the same order run in parallel." />
      <Alert severity="info" sx={{ mb: 2 }}>
        Conditions route requests to different workflows, e.g. {'{"all": [{"field": "days", "op": ">", "value": 10}]}'} for long leave, or
        {' {"field": "amount", "op": ">=", "value": 5000}'} for large loans. The lowest priority number whose conditions match is used.
        The requester can never approve their own request.
      </Alert>
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 5 }}>
          <Card><ResourcePage embedded title="Workflow" url="/workflow/definitions/" onRowClick={(r) => setSel(r.id as number)} searchable={false} createLabel="New workflow"
            columns={[{ key: "name", label: "Workflow", render: (r) => <><b>{r.name as string}</b><br /><Typography variant="caption">{r.request_type_label as string}</Typography></> },
              { key: "priority", label: "Priority" }, { key: "is_active", label: "", render: (r) => (r.is_active ? <Chip color="success" variant="outlined" label="Active" /> : <Chip label="Off" />) }]}
            fields={[{ name: "name", label: "Name", required: true }, { name: "request_type", label: "Request type", type: "select", options: typeOpts, required: true, width: 6 },
              { name: "priority", label: "Priority (lower wins)", type: "number", width: 6 },
              { name: "conditions", label: "Conditions (JSON, {} = always)", type: "json" }, { name: "description", label: "Description", type: "textarea" },
              { name: "is_active", label: "Active", type: "checkbox" }]} defaults={{ priority: 100, conditions: "{}", is_active: true }} /></Card>
          <Card sx={{ mt: 2 }}><List dense>
            {(types.data || []).map((t) => <ListItemButton key={t.code} disabled><ListItemText primary={t.label} secondary={`Condition fields: ${t.context_fields.join(", ") || "department, grade_level, category, employment_type"}`} /></ListItemButton>)}
          </List></Card>
        </Grid>
        <Grid size={{ xs: 12, md: 7 }}>
          {def && (
            <Section title={`Steps — ${def.name} (v${def.version})`}>
              <ResourcePage embedded title="Step" url="/workflow/steps/" params={{ definition: def.id }} searchable={false} canDelete createLabel="Add step"
                columns={[{ key: "order", label: "#" }, { key: "name", label: "Step" },
                  { key: "approver_type", label: "Approver", render: (r) => r.approver_type === "role" ? `Role: ${r.role_name}` : r.approver_type === "user" ? `User: ${r.user_name}` : APPROVERS.find((a) => a.value === r.approver_type)?.label },
                  { key: "approval_mode", label: "Mode", render: (r) => titleCase(r.approval_mode as string) }, { key: "sla_hours", label: "SLA (h)" },
                  { key: "comment_rule", label: "Comments", render: (r) => titleCase(r.comment_rule as string) }]}
                fields={[{ name: "order", label: "Order", type: "number", required: true, width: 4 }, { name: "name", label: "Step name", required: true, width: 8 },
                  { name: "approver_type", label: "Approver", type: "select", options: APPROVERS, required: true, width: 6 },
                  { name: "approval_mode", label: "Mode", type: "select", width: 6, options: [{ value: "any", label: "Any one approver" }, { value: "all", label: "All approvers" }] },
                  { name: "role", label: "Role", type: "ref", ref: "/admin/roles/", hidden: (v) => v.approver_type !== "role" },
                  { name: "user", label: "User", type: "ref", ref: "/admin/users/", refLabel: (u) => `${u.first_name} ${u.last_name} (${u.username})`, hidden: (v) => v.approver_type !== "user" },
                  { name: "sla_hours", label: "SLA (hours)", type: "number", width: 6 },
                  { name: "escalate_to_role", label: "Escalate overdue to role (blank = approver's supervisor)", type: "ref", ref: "/admin/roles/", width: 6 },
                  { name: "comment_rule", label: "Comment rule", type: "select", width: 6, options: [{ value: "none", label: "Optional" }, { value: "reject", label: "Required to reject / return" }, { value: "all", label: "Always required" }] },
                  { name: "skip_if_no_approver", label: "Skip step if no approver found", type: "checkbox", width: 6 },
                  { name: "condition", label: "Step condition (JSON)", type: "json", helper: "Step runs only when matched, e.g. {\"field\": \"days\", \"op\": \">\", \"value\": 5}" },
                  { name: "definition", label: "", hidden: () => true }]}
                defaults={{ definition: def.id, approval_mode: "any", sla_hours: 48, comment_rule: "reject", condition: "{}", skip_if_no_approver: true }} />
            </Section>
          )}
        </Grid>
      </Grid>
    </>
  );
}
