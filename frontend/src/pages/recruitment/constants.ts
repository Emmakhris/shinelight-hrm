const opts = (pairs: string[][]) => pairs.map(([value, label]) => ({ value, label }));

export const STAGES = opts([["applied", "Applied"], ["screening", "Screening"], ["shortlisted", "Shortlisted"],
  ["interview", "Interview"], ["assessment", "Assessment"], ["reference_check", "Reference checks"], ["offer", "Offer"],
  ["hired", "Hired"], ["rejected", "Unsuccessful"], ["withdrawn", "Withdrawn"]]);
export const STAGE_LABEL: Record<string, string> = Object.fromEntries(STAGES.map((s) => [s.value, s.label]));
export const MANUAL_STAGES = STAGES.filter((s) => !["offer", "hired"].includes(s.value));

export const QUALIFICATIONS = opts([["none", "No formal qualification"], ["basic", "BECE / basic"],
  ["secondary", "WASSCE / SSSCE"], ["certificate", "Certificate"], ["diploma", "Diploma / HND"],
  ["degree", "Bachelor's degree"], ["masters", "Master's degree"], ["doctorate", "Doctorate"],
  ["professional", "Professional (ACCA, ICAG, etc.)"]]);

export const EMPLOYMENT_TYPES = opts([["permanent", "Permanent"], ["contract", "Fixed-term contract"],
  ["temporary", "Temporary"], ["national_service", "National Service"], ["intern", "Intern"], ["casual", "Casual"]]);

export const REASONS = opts([["new", "New position"], ["replacement", "Replacement"],
  ["expansion", "Additional headcount"], ["temporary", "Temporary cover"]]);

export const SOURCES = opts([["career_site", "Career site"], ["internal", "Internal employee"],
  ["referral", "Staff referral"], ["agency", "Recruitment agency"], ["job_board", "Job board"],
  ["newspaper", "Newspaper"], ["walk_in", "Walk-in / unsolicited"], ["other", "Other"]]);

export const VISIBILITY = opts([["both", "Internal and external"], ["external", "External only"],
  ["internal", "Internal only"]]);

export const CHECK_TYPES = opts([["reference", "Employment reference"], ["academic", "Academic verification"],
  ["professional", "Professional licence"], ["police", "Police / criminal record"],
  ["medical", "Pre-employment medical"], ["identity", "Ghana Card / identity"]]);

export const RECOMMENDATIONS = opts([["strong_yes", "Strongly recommend"], ["yes", "Recommend"],
  ["no", "Do not recommend"], ["strong_no", "Strongly against"]]);

export const OWNER_TYPES = opts([["hr", "HR"], ["manager", "Hiring manager / supervisor"], ["it", "IT"],
  ["finance", "Finance / payroll"], ["admin", "Administration / facilities"], ["employee", "New employee"],
  ["role", "Specific role"]]);

export const TASK_CATEGORIES = opts([["pre_employment", "Pre-employment checks"], ["documents", "Documents & information"],
  ["equipment", "Equipment & resources"], ["access", "Accounts & system access"], ["induction", "Induction & orientation"],
  ["policy", "Policy acknowledgment"], ["training", "Mandatory training"], ["probation", "Probation"],
  ["survey", "New-hire feedback"], ["other", "Other"]]);
