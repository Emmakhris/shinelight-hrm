import dayjs from "dayjs";

export const fmtDate = (v?: string | null) => (v ? dayjs(v).format("DD/MM/YYYY") : "—");
export const fmtDateTime = (v?: string | null) => (v ? dayjs(v).format("DD/MM/YYYY HH:mm") : "—");
export const fmtTime = (v?: string | null) => (v ? dayjs(v).format("HH:mm") : "—");

const money = new Intl.NumberFormat("en-GH", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const fmtMoney = (v?: string | number | null, currency = "GHS") =>
  v === null || v === undefined || v === "" ? "—" : `${currency} ${money.format(Number(v))}`;
export const fmtNum = (v?: string | number | null, dp = 2) =>
  v === null || v === undefined || v === "" ? "—" : Number(v).toLocaleString("en-GH", { maximumFractionDigits: dp });

export const titleCase = (s?: string | null) =>
  (s || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

export const today = () => dayjs().format("YYYY-MM-DD");

export const STATUS_COLORS: Record<string, "default" | "primary" | "success" | "warning" | "error" | "info"> = {
  active: "success", approved: "success", paid: "success", ok: "success", present: "success", issued: "success",
  completed: "success", success: "success", current: "success", sent: "success",
  pending: "warning", submitted: "warning", in_progress: "warning", probation: "info", calculated: "info",
  draft: "default", late: "warning", half_day: "warning", warning: "warning", returned: "warning", expiring: "warning",
  rejected: "error", error: "error", absent: "error", exited: "default", cancelled: "default", reversed: "default",
  incomplete: "error", failed: "error", expired: "error", missing: "error", hold: "warning", recalled: "info",
  on_leave: "info", holiday: "info", off: "default", suspended: "error",
  published: "success", filled: "success", accepted: "success", verified: "success", done: "success", hired: "success",
  scheduled: "info", negotiating: "warning", concerns: "warning", shortlisted: "info", interview: "info", offer: "info",
  declined: "error", withdrawn: "default", superseded: "default", waived: "default", closed: "default",
};
