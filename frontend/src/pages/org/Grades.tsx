import { Card, Grid2 as Grid } from "@mui/material";
import { useState } from "react";
import { PageHeader, Section } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";
import { fmtMoney } from "../../utils";

export default function Grades() {
  const [grade, setGrade] = useState<Record<string, unknown> | null>(null);
  return (
    <>
      <PageHeader title="Grades & salary scales" subtitle="Select a grade to manage its steps (salary scale)." />
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 7 }}>
          <Card><ResourcePage embedded title="Grade" url="/org/grades/" onRowClick={setGrade} createLabel="Add grade"
            columns={[{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "level", label: "Level" },
              { key: "min_salary", label: "Min", align: "right", render: (r) => fmtMoney(r.min_salary as string) },
              { key: "max_salary", label: "Max", align: "right", render: (r) => fmtMoney(r.max_salary as string) },
              { key: "steps", label: "Steps", render: (r) => (r.steps as unknown[]).length }]}
            fields={[{ name: "code", label: "Code", required: true, width: 4 }, { name: "name", label: "Name", required: true, width: 8 },
              { name: "level", label: "Seniority level", type: "number", required: true, width: 4 },
              { name: "min_salary", label: "Minimum salary", type: "number", width: 4 }, { name: "max_salary", label: "Maximum salary", type: "number", width: 4 },
              { name: "is_active", label: "Active", type: "checkbox" }]} defaults={{ is_active: true, level: 1 }} /></Card>
        </Grid>
        <Grid size={{ xs: 12, md: 5 }}>
          {grade ? (
            <Section title={`Steps — ${grade.code}`}>
              <ResourcePage embedded title="Step" url="/org/grade-steps/" params={{ grade: grade.id as number }} searchable={false} canDelete
                columns={[{ key: "step", label: "Step" }, { key: "basic_salary", label: "Basic salary", align: "right", render: (r) => fmtMoney(r.basic_salary as string) },
                  { key: "effective_from", label: "Effective" }]}
                fields={[{ name: "step", label: "Step", type: "number", required: true, width: 6 },
                  { name: "basic_salary", label: "Monthly basic (GHS)", type: "number", required: true, width: 6 },
                  { name: "effective_from", label: "Effective from", type: "date" }, { name: "grade", label: "", hidden: () => true }]}
                defaults={{ grade: grade.id }} createLabel="Add step" />
            </Section>
          ) : <Section title="Steps">Select a grade.</Section>}
        </Grid>
      </Grid>
    </>
  );
}
