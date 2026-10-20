import type { FieldDef } from "../../components/FormDialog";

export const EMPLOYMENT_TYPES = [
  { value: "permanent", label: "Permanent" }, { value: "contract", label: "Fixed-term contract" },
  { value: "temporary", label: "Temporary" }, { value: "national_service", label: "National Service" },
  { value: "intern", label: "Intern" }, { value: "casual", label: "Casual" },
];
export const TITLES = ["mr", "mrs", "ms", "miss", "dr", "prof", "rev", "hon"].map((t) => ({ value: t, label: t[0].toUpperCase() + t.slice(1) }));
export const GENDERS = [{ value: "male", label: "Male" }, { value: "female", label: "Female" }];
export const MARITAL = ["single", "married", "divorced", "widowed", "separated"].map((v) => ({ value: v, label: v[0].toUpperCase() + v.slice(1) }));

const empLabel = (e: Record<string, unknown>) => `${e.full_name} (${e.staff_number})`;
const posLabel = (p: Record<string, unknown>) => `${p.code} — ${p.job_title_name} (${p.department_name}) · ${p.vacancies} vacant`;

export const personalFields: FieldDef[] = [
  { name: "title", label: "Title", type: "select", options: TITLES, width: 3 },
  { name: "first_name", label: "First name", required: true, width: 3 },
  { name: "middle_name", label: "Middle name", width: 3 },
  { name: "last_name", label: "Surname", required: true, width: 3 },
  { name: "gender", label: "Gender", type: "select", options: GENDERS, width: 3 },
  { name: "date_of_birth", label: "Date of birth", type: "date", width: 3 },
  { name: "marital_status", label: "Marital status", type: "select", options: MARITAL, width: 3 },
  { name: "nationality", label: "Nationality", width: 3 },
  { name: "ghana_card_no", label: "Ghana Card PIN", placeholder: "GHA-123456789-0", width: 4 },
  { name: "ssnit_number", label: "SSNIT number", width: 4 },
  { name: "tin", label: "TIN", width: 4 },
  { name: "phone", label: "Phone", placeholder: "0241234567", width: 4 },
  { name: "work_email", label: "Work email", type: "email", width: 4 },
  { name: "personal_email", label: "Personal email", type: "email", width: 4 },
  { name: "residential_address", label: "Residential address", width: 8 },
  { name: "digital_address", label: "Ghana Post GPS", width: 4 },
];

export const hireFields: FieldDef[] = [
  ...personalFields,
  { name: "staff_number", label: "Staff number (blank = auto)", width: 4 },
  { name: "hire_date", label: "Hire / appointment date", type: "date", required: true, width: 4 },
  { name: "employment_type", label: "Employment type", type: "select", options: EMPLOYMENT_TYPES, width: 4 },
  { name: "position", label: "Position (approved post)", type: "ref", ref: "/org/positions/", refParams: { status: "approved" }, refLabel: posLabel,
    helper: "Department, job title and grade are taken from the position." },
  { name: "grade_step", label: "Grade step (sets basic salary)", type: "ref", ref: "/org/grade-steps/",
    refLabel: (s) => `${s.grade_code} · step ${s.step} · GHS ${s.basic_salary}`, width: 6 },
  { name: "basic_salary", label: "Basic salary override (GHS)", type: "number", width: 6 },
  { name: "supervisor", label: "Supervisor", type: "ref", ref: "/employees/", refLabel: empLabel, width: 6 },
  { name: "category", label: "Employee category", type: "ref", ref: "/employees/categories/", width: 6 },
  { name: "probation_end_date", label: "Probation end date", type: "date", width: 6 },
  { name: "contract_end_date", label: "Contract end date", type: "date", width: 6 },
];

export const personnelActionFields: FieldDef[] = [
  { name: "event_type", label: "Action", type: "select", required: true, options: [
    { value: "promotion", label: "Promotion" }, { value: "transfer", label: "Transfer" }, { value: "secondment", label: "Secondment" },
    { value: "salary_change", label: "Salary change / increment" }, { value: "redesignation", label: "Redesignation" },
    { value: "demotion", label: "Demotion" }, { value: "contract_renewal", label: "Contract renewal" },
    { value: "suspension", label: "Suspension" }, { value: "reinstatement", label: "Reinstatement" },
    { value: "status_change", label: "Status change" }, { value: "correction", label: "Data correction" }] },
  { name: "effective_from", label: "Effective date", type: "date", required: true, width: 6,
    helper: "Future dates take effect automatically; back-dated salary changes create arrears." },
  { name: "reference", label: "Memo / letter reference", width: 6 },
  { name: "position", label: "New position", type: "ref", ref: "/org/positions/", refParams: { status: "approved" }, refLabel: posLabel },
  { name: "department", label: "New department", type: "ref", ref: "/org/departments/", width: 6 },
  { name: "job_title", label: "New job title", type: "ref", ref: "/org/job-titles/", width: 6 },
  { name: "grade", label: "New grade", type: "ref", ref: "/org/grades/", refLabel: (g) => `${g.code} — ${g.name}`, width: 6 },
  { name: "grade_step", label: "New grade step", type: "ref", ref: "/org/grade-steps/", refLabel: (s) => `${s.grade_code} · step ${s.step} · GHS ${s.basic_salary}`, width: 6 },
  { name: "basic_salary", label: "New basic salary (GHS)", type: "number", width: 6 },
  { name: "supervisor", label: "New supervisor", type: "ref", ref: "/employees/", refLabel: empLabel, width: 6 },
  { name: "branch", label: "New branch", type: "ref", ref: "/org/branches/", width: 6 },
  { name: "location", label: "New location", type: "ref", ref: "/org/locations/", width: 6 },
  { name: "employment_type", label: "Employment type", type: "select", options: EMPLOYMENT_TYPES, width: 6 },
  { name: "status", label: "Status", type: "select", width: 6, options: [{ value: "active", label: "Active" },
    { value: "probation", label: "Probation" }, { value: "suspended", label: "Suspended" }, { value: "on_leave", label: "On extended leave" }] },
  { name: "reason", label: "Reason / remarks", type: "textarea" },
];
