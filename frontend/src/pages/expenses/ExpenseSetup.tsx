import { Card, Tab, Tabs } from "@mui/material";
import { useState } from "react";
import { PageHeader } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtDate, fmtMoney } from "../../utils";

const DEST = [["local", "Within region"], ["national", "Other region in Ghana"], ["africa", "Africa"], ["international", "Outside Africa"]]
  .map(([value, label]) => ({ value, label }));

export default function ExpenseSetup() {
  const [tab, setTab] = useState(0);
  const year = new Date().getFullYear();
  return (
    <>
      <PageHeader title="Per diem rates & budgets" />
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}><Tab label="Per diem rates" /><Tab label={`Budgets ${year}`} /></Tabs>
      <Card>
        {tab === 0 && <ResourcePage embedded title="Rate" url="/expenses/per-diem/" canDelete searchable={false}
          columns={[{ key: "destination_class", label: "Destination" }, { key: "location", label: "City" },
            { key: "min_grade_level", label: "Grades", render: (r) => `${r.min_grade_level}–${r.max_grade_level}` },
            { key: "daily_allowance", label: "Daily", align: "right", render: (r) => fmtMoney(r.daily_allowance, r.currency) },
            { key: "accommodation_cap", label: "Hotel cap / night", align: "right", render: (r) => fmtMoney(r.accommodation_cap, r.currency) },
            { key: "effective_from", label: "From", render: (r) => fmtDate(r.effective_from) }]}
          fields={[{ name: "destination_class", label: "Destination type", type: "select", options: DEST, required: true, width: 6 },
            { name: "location", label: "Specific city (optional)", width: 6 },
            { name: "min_grade_level", label: "Min grade level", type: "number", width: 3 }, { name: "max_grade_level", label: "Max grade level", type: "number", width: 3 },
            { name: "currency", label: "Currency", width: 3 }, { name: "effective_from", label: "Effective from", type: "date", required: true, width: 3 },
            { name: "daily_allowance", label: "Daily allowance", type: "number", required: true, width: 6 },
            { name: "accommodation_cap", label: "Accommodation cap per night", type: "number", width: 6 },
            { name: "is_active", label: "Active", type: "checkbox" }]} defaults={{ currency: "GHS", min_grade_level: 0, max_grade_level: 99, is_active: true }} />}
        {tab === 1 && <ResourcePage embedded title="Budget" url="/expenses/budgets/" params={{ year }} canDelete searchable={false}
          columns={[{ key: "department_name", label: "Department" }, { key: "category", label: "Category" },
            { key: "amount", label: "Budget", align: "right", render: (r) => fmtMoney(r.amount) },
            { key: "spent", label: "Spent", align: "right", render: (r) => fmtMoney(r.status?.spent) },
            { key: "committed", label: "Committed", align: "right", render: (r) => fmtMoney(r.status?.committed) },
            { key: "available", label: "Available", align: "right", render: (r) => fmtMoney(r.status?.available) }]}
          fields={[{ name: "department", label: "Department", type: "ref", ref: "/org/departments/", required: true },
            { name: "year", label: "Year", type: "number", required: true, width: 4 },
            { name: "category", label: "Category", type: "select", width: 4, options: [{ value: "travel", label: "Travel (all)" }, { value: "training", label: "Training" }, { value: "other", label: "Other" }] },
            { name: "amount", label: "Amount (GHS)", type: "number", required: true, width: 4 }]} defaults={{ year, category: "travel" }} />}
      </Card>
    </>
  );
}
