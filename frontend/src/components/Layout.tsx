import AccountTree from "@mui/icons-material/AccountTree";
import AdminPanelSettings from "@mui/icons-material/AdminPanelSettings";
import Assessment from "@mui/icons-material/Assessment";
import BadgeOutlined from "@mui/icons-material/BadgeOutlined";
import Campaign from "@mui/icons-material/Campaign";
import Dashboard from "@mui/icons-material/Dashboard";
import Description from "@mui/icons-material/Description";
import EventNote from "@mui/icons-material/EventNote";
import ExpandLess from "@mui/icons-material/ExpandLess";
import ExpandMore from "@mui/icons-material/ExpandMore";
import Gavel from "@mui/icons-material/Gavel";
import Groups from "@mui/icons-material/Groups";
import HealthAndSafety from "@mui/icons-material/HealthAndSafety";
import HomeOutlined from "@mui/icons-material/HomeOutlined";
import Inbox from "@mui/icons-material/Inbox";
import Insights from "@mui/icons-material/Insights";
import LocalHospital from "@mui/icons-material/LocalHospital";
import Logout from "@mui/icons-material/Logout";
import Menu from "@mui/icons-material/Menu";
import NotificationsOutlined from "@mui/icons-material/NotificationsOutlined";
import Payments from "@mui/icons-material/Payments";
import PersonAdd from "@mui/icons-material/PersonAdd";
import PersonOutline from "@mui/icons-material/PersonOutline";
import Savings from "@mui/icons-material/Savings";
import Schedule from "@mui/icons-material/Schedule";
import School from "@mui/icons-material/School";
import SupportAgent from "@mui/icons-material/SupportAgent";
import TrendingUp from "@mui/icons-material/TrendingUp";
import { LicenceBanner } from "./LicenceBanner";
import { AppBar, Avatar, Badge, Box, Collapse, Divider, Drawer, IconButton, List, ListItemButton, ListItemIcon,
  ListItemText, ListSubheader, Menu as MuiMenu, MenuItem, Toolbar, Tooltip, Typography, useMediaQuery } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { useState, type ReactNode } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { useApi } from "../api/hooks";
import { useAuth } from "../auth/AuthContext";
import NotificationsPopover from "./NotificationsPopover";

const DRAWER = 264;

interface NavItem { label: string; to: string; perm?: string | string[]; feature?: string; scope?: string; employee?: boolean; edition?: "self_hosted" | "cloud" }
interface NavGroup { label: string; icon: ReactNode; items: NavItem[] }

const NAV: NavGroup[] = [
  { label: "My workspace", icon: <HomeOutlined />, items: [
    { label: "Home", to: "/" },
    { label: "My profile", to: "/me/profile", employee: true },
    { label: "Ask HR assistant", to: "/assistant", feature: "ai_assistant" },
    { label: "My leave", to: "/leave/my", employee: true },
    { label: "My attendance", to: "/attendance/my", employee: true },
    { label: "My payslips", to: "/me/payslips", employee: true, feature: "payroll" },
    { label: "My documents & letters", to: "/me/documents", employee: true },
    { label: "Documents to sign", to: "/me/signatures" },
    { label: "HR help desk", to: "/helpdesk" },
    { label: "Travel & expenses", to: "/expenses/my", employee: true },
    { label: "Benefits & total rewards", to: "/me/benefits", employee: true },
    { label: "Loans & advances", to: "/me/loans", employee: true, feature: "payroll" },
    { label: "My requests", to: "/me/requests" },
    { label: "My performance", to: "/performance/my", employee: true },
    { label: "My learning", to: "/learning", employee: true },
    { label: "My career", to: "/talent/me", employee: true },
    { label: "My equipment", to: "/assets/my", employee: true },
    { label: "Raise a concern", to: "/relations/my", employee: true },
    { label: "Engagement & wellbeing", to: "/engagement", employee: true },
    { label: "Report a safety incident", to: "/safety/my" },
    { label: "Resignation & exit", to: "/offboarding/my", employee: true },
    { label: "Feedback requests", to: "/performance/feedback" },
    { label: "Onboarding tasks", to: "/onboarding/my-tasks" },
    { label: "Interview panels", to: "/recruitment/my-interviews" },
    { label: "Internal job openings", to: "/me/jobs", employee: true },
    { label: "Staff directory", to: "/directory" },
    { label: "Announcements & policies", to: "/announcements" },
  ] },
  { label: "Manager", icon: <Groups />, items: [
    { label: "My team", to: "/team", perm: ["leave.approve", "attendance.approve"] },
    { label: "Team attendance today", to: "/attendance/team", perm: "attendance.approve" },
    { label: "Delegations", to: "/delegations", perm: ["leave.approve", "attendance.approve", "payroll.approve"] },
    { label: "Staff requisitions", to: "/recruitment/requisitions", perm: "recruitment.requisition" },
    { label: "Probation reviews", to: "/onboarding/probation", perm: ["leave.approve", "onboarding.view"] },
    { label: "Team appraisals", to: "/performance/team", perm: ["leave.approve", "performance.manage"] },
    { label: "Improvement plans", to: "/performance/plans", perm: ["leave.approve", "performance.manage"] },
    { label: "Team learning", to: "/learning/team", perm: ["leave.approve", "learning.manage"] },
    { label: "Talent review", to: "/talent", perm: ["leave.approve", "talent.view"] },
  ] },
  { label: "Recruitment & onboarding", icon: <PersonAdd />, items: [
    { label: "Vacancies & pipeline", to: "/recruitment/vacancies", perm: "recruitment.view" },
    { label: "Requisitions", to: "/recruitment/requisitions", perm: "recruitment.view" },
    { label: "Candidates & talent pool", to: "/recruitment/candidates", perm: "recruitment.view" },
    { label: "Recruitment analytics", to: "/recruitment/analytics", perm: "recruitment.view" },
    { label: "Onboarding", to: "/onboarding", perm: "onboarding.view", scope: "organization" },
    { label: "Onboarding checklists", to: "/onboarding/setup", perm: "onboarding.manage" },
  ] },
  { label: "Employee relations & exits", icon: <Gavel />, items: [
    { label: "Employee relations cases", to: "/relations", perm: ["relations.manage", "relations.view_all"] },
    { label: "Exits & clearance", to: "/offboarding", perm: ["offboarding.view", "assets.manage", "payroll.prepare", "expenses.pay"] },
    { label: "Assets & equipment", to: "/assets", perm: "assets.view" },
  ] },
  { label: "Talent & workforce planning", icon: <Insights />, items: [
    { label: "Talent & succession", to: "/talent", perm: "talent.view" },
    { label: "Workforce planning", to: "/planning", perm: "planning.view" },
  ] },
  { label: "Engagement & safety", icon: <HealthAndSafety />, items: [
    { label: "Surveys & engagement", to: "/engagement/admin", perm: "engagement.manage" },
    { label: "Health & safety", to: "/safety", perm: "ohs.view" },
    { label: "Occupational health records", to: "/safety/occupational-health", perm: "ohs.medical" },
  ] },
  { label: "Learning & development", icon: <School />, items: [
    { label: "Training administration", to: "/learning/admin", perm: "learning.manage" },
    { label: "Compliance & effectiveness", to: "/learning/compliance", perm: ["learning.manage", "learning.view"], scope: "department" },
  ] },
  { label: "Performance", icon: <TrendingUp />, items: [
    { label: "Review cycles & calibration", to: "/performance/cycles", perm: "performance.manage" },
    { label: "Improvement plans", to: "/performance/plans", perm: "performance.manage" },
    { label: "Forms, competencies & scales", to: "/performance/setup", perm: "performance.manage" },
  ] },
  { label: "HR service desk", icon: <SupportAgent />, items: [
    { label: "Ticket queue", to: "/helpdesk/queue", perm: ["servicedesk.agent", "servicedesk.manage"] },
    { label: "Service KPIs", to: "/helpdesk/metrics", perm: "servicedesk.manage" },
    { label: "Catalogue & knowledge base", to: "/helpdesk/setup", perm: "servicedesk.manage" },
  ] },
  { label: "Rewards & expenses", icon: <Savings />, items: [
    { label: "Salary reviews", to: "/compensation/reviews", perm: "compensation.view" },
    { label: "Bonuses", to: "/compensation/bonuses", perm: "compensation.view" },
    { label: "Benefits administration", to: "/benefits/admin", perm: "benefits.manage" },
    { label: "Travel & claims admin", to: "/expenses/manage", perm: ["expenses.manage", "expenses.pay"] },
    { label: "Per diem & budgets", to: "/expenses/setup", perm: "expenses.manage" },
  ] },
  { label: "Dashboards & reports", icon: <Assessment />, items: [
    { label: "HR dashboard", to: "/dashboard", perm: "reports.view" },
    { label: "Workforce analytics", to: "/analytics", perm: "reports.view" },
    { label: "Reports", to: "/reports", perm: "reports.view" },
    { label: "Report builder", to: "/reports/builder", perm: "reports.view" },
    { label: "Workforce forecasts", to: "/forecasts", perm: "reports.view" },
  ] },
  { label: "People", icon: <BadgeOutlined />, items: [
    { label: "Employees", to: "/employees", perm: "employees.view", scope: "team" },
    { label: "Bulk import", to: "/employees/import", perm: "employees.import" },
    { label: "Data quality", to: "/employees/data-quality", perm: "employees.view", scope: "organization" },
    { label: "Change requests", to: "/employees/change-requests", perm: "employees.change" },
  ] },
  { label: "Organization", icon: <AccountTree />, items: [
    { label: "Org chart", to: "/org/chart", perm: "organization.view" },
    { label: "Departments & units", to: "/org/departments", perm: "organization.manage" },
    { label: "Positions & establishment", to: "/org/positions", perm: "organization.manage" },
    { label: "Grades & salary scales", to: "/org/grades", perm: "organization.manage" },
    { label: "Job titles", to: "/org/job-titles", perm: "organization.manage" },
    { label: "Branches, locations, cost centres", to: "/org/locations", perm: "organization.manage" },
  ] },
  { label: "Leave", icon: <EventNote />, items: [
    { label: "Leave requests", to: "/leave/requests", perm: "leave.approve" },
    { label: "Leave calendar", to: "/leave/calendar", perm: "leave.view" },
    { label: "Balances & adjustments", to: "/leave/balances", perm: "leave.manage" },
    { label: "Leave types & policies", to: "/leave/setup", perm: "leave.manage" },
  ] },
  { label: "Time & attendance", icon: <Schedule />, items: [
    { label: "Timesheets & exceptions", to: "/attendance/days", perm: "attendance.approve" },
    { label: "Roster", to: "/attendance/roster", perm: "attendance.view", scope: "team" },
    { label: "Period summaries", to: "/attendance/summaries", perm: "attendance.manage" },
    { label: "Shifts, policies & devices", to: "/attendance/setup", perm: "attendance.manage" },
  ] },
  { label: "Payroll", icon: <Payments />, items: [
    { label: "Payroll runs", to: "/payroll/runs", perm: "payroll.view", feature: "payroll" },
    { label: "Employee pay", to: "/payroll/employees", perm: "payroll.prepare", feature: "payroll" },
    { label: "Loans & advances", to: "/payroll/loans", perm: "payroll.view", feature: "payroll" },
    { label: "Payroll setup & statutory", to: "/payroll/setup", perm: "payroll.manage", feature: "payroll" },
  ] },
  { label: "Documents", icon: <Description />, items: [
    { label: "Personnel documents", to: "/documents", perm: "documents.upload" },
    { label: "Letter templates", to: "/documents/templates", perm: "documents.manage" },
  ] },
  { label: "Clinical workforce", icon: <LocalHospital />, items: [
    { label: "Professional licences", to: "/hospital/licenses", perm: "hospital.view", feature: "hospital" },
    { label: "Competency matrix", to: "/hospital/matrix", perm: "hospital.view", feature: "hospital" },
    { label: "Ward staffing", to: "/hospital/staffing", perm: "hospital.view", feature: "hospital" },
  ] },
  { label: "Administration", icon: <AdminPanelSettings />, items: [
    { label: "Users & access", to: "/admin/users", perm: "admin.users" },
    { label: "Roles & permissions", to: "/admin/roles", perm: "admin.roles" },
    { label: "Approval workflows", to: "/admin/workflows", perm: "workflow.manage" },
    { label: "Organization settings", to: "/admin/settings", perm: "admin.settings" },
    { label: "Notifications & announcements", to: "/admin/notifications", perm: "notifications.manage" },
    { label: "Integrations & API", to: "/admin/integrations", perm: "integrations.manage" },
    { label: "Single sign-on", to: "/admin/sso", perm: "admin.settings" },
    { label: "AI assistant", to: "/admin/assistant", perm: "admin.settings" },
    { label: "Licence", to: "/admin/licence", perm: "admin.settings", edition: "self_hosted" },
    { label: "Audit trail", to: "/admin/audit", perm: "audit.view" },
  ] },
];

export default function Layout() {
  const { me, can, feature, logout } = useAuth();
  const theme = useTheme();
  const mobile = useMediaQuery(theme.breakpoints.down("md"));
  const [open, setOpen] = useState(false);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [menu, setMenu] = useState<HTMLElement | null>(null);
  const [notifAnchor, setNotifAnchor] = useState<HTMLElement | null>(null);
  const nav = useNavigate();
  const loc = useLocation();
  const unread = useApi<{ unread: number }>("/notifications/unread-count/", undefined, { refetchInterval: 60000 });
  const inbox = useApi<{ pending: number }>("/workflow/inbox/counts/", undefined, { refetchInterval: 60000 });

  const visible = (i: NavItem) => (!i.perm || can(i.perm, i.scope)) && (!i.feature || feature(i.feature))
    && (!i.employee || !!me?.employee) && (!i.edition || i.edition === me?.edition);

  const drawer = (
    <Box sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <Toolbar sx={{ gap: 1.5 }}>
        <Box component="img" src="/favicon.svg" alt="" sx={{ width: 34 }} />
        <Box>
          <Typography fontWeight={700} lineHeight={1.1}>ShineLight HRM</Typography>
          <Typography variant="caption" color="text.secondary" noWrap>{me?.organization?.name}</Typography>
        </Box>
      </Toolbar>
      <Divider />
      <List dense sx={{ flex: 1, overflowY: "auto", py: 0 }}>
        <ListItemButton selected={loc.pathname === "/inbox"} onClick={() => { nav("/inbox"); setOpen(false); }} sx={{ my: 0.5 }}>
          <ListItemIcon><Badge badgeContent={inbox.data?.pending || 0} color="error"><Inbox /></Badge></ListItemIcon>
          <ListItemText primary="Approvals inbox" primaryTypographyProps={{ fontWeight: 600 }} />
        </ListItemButton>
        {NAV.map((g) => {
          const items = g.items.filter(visible);
          if (!items.length) return null;
          const isCollapsed = collapsed[g.label] ?? (g.label !== "My workspace" && !items.some((i) => loc.pathname.startsWith(i.to) && i.to !== "/"));
          return (
            <Box key={g.label}>
              <ListSubheader disableSticky onClick={() => setCollapsed((c) => ({ ...c, [g.label]: !isCollapsed }))}
                sx={{ cursor: "pointer", display: "flex", alignItems: "center", gap: 1, lineHeight: "36px" }}>
                <Box sx={{ display: "flex", color: "primary.main", "& svg": { fontSize: 18 } }}>{g.icon}</Box>
                <Box flex={1}>{g.label}</Box>
                {isCollapsed ? <ExpandMore fontSize="small" /> : <ExpandLess fontSize="small" />}
              </ListSubheader>
              <Collapse in={!isCollapsed}>
                {items.map((i) => (
                  <ListItemButton key={i.to} selected={loc.pathname === i.to} sx={{ pl: 5.5, py: 0.4 }}
                    onClick={() => { nav(i.to); setOpen(false); }}>
                    <ListItemText primary={i.label} primaryTypographyProps={{ fontSize: 13.5 }} />
                  </ListItemButton>
                ))}
              </Collapse>
            </Box>
          );
        })}
      </List>
    </Box>
  );

  return (
    <Box sx={{ display: "flex", minHeight: "100vh" }}>
      <AppBar position="fixed" color="inherit" elevation={0}
        sx={{ borderBottom: "1px solid #e3e8ef", width: { md: `calc(100% - ${DRAWER}px)` }, ml: { md: `${DRAWER}px` } }}>
        <Toolbar>
          {mobile && <IconButton edge="start" onClick={() => setOpen(true)} aria-label="Open menu"><Menu /></IconButton>}
          <Box flex={1} />
          <Tooltip title="Notifications">
            <IconButton onClick={(e) => setNotifAnchor(e.currentTarget)} aria-label="Notifications">
              <Badge badgeContent={unread.data?.unread || 0} color="error"><NotificationsOutlined /></Badge>
            </IconButton>
          </Tooltip>
          <Tooltip title="Announcements">
            <IconButton onClick={() => nav("/announcements")} aria-label="Announcements"><Campaign /></IconButton>
          </Tooltip>
          <IconButton onClick={(e) => setMenu(e.currentTarget)} sx={{ ml: 1 }} aria-label="Account">
            <Avatar src={me?.employee?.photo || undefined} sx={{ width: 34, height: 34, bgcolor: "primary.main", fontSize: 14 }}>
              {me?.full_name?.split(" ").map((s) => s[0]).slice(0, 2).join("")}
            </Avatar>
          </IconButton>
          <MuiMenu anchorEl={menu} open={!!menu} onClose={() => setMenu(null)}>
            <Box sx={{ px: 2, py: 1 }}>
              <Typography fontWeight={600}>{me?.full_name}</Typography>
              <Typography variant="caption" color="text.secondary">{me?.employee?.job_title || me?.username}</Typography>
            </Box>
            <Divider />
            {me?.employee && <MenuItem onClick={() => { setMenu(null); nav("/me/profile"); }}><PersonOutline fontSize="small" sx={{ mr: 1 }} />My profile</MenuItem>}
            <MenuItem onClick={() => { setMenu(null); nav("/change-password"); }}><Dashboard fontSize="small" sx={{ mr: 1 }} />Change password</MenuItem>
            <MenuItem onClick={() => { setMenu(null); logout(); }}><Logout fontSize="small" sx={{ mr: 1 }} />Sign out</MenuItem>
          </MuiMenu>
        </Toolbar>
      </AppBar>
      <Box component="nav" sx={{ width: { md: DRAWER }, flexShrink: { md: 0 } }}>
        <Drawer variant={mobile ? "temporary" : "permanent"} open={mobile ? open : true} onClose={() => setOpen(false)}
          sx={{ "& .MuiDrawer-paper": { width: DRAWER, boxSizing: "border-box", borderRight: "1px solid #e3e8ef" } }}>
          {drawer}
        </Drawer>
      </Box>
      <Box component="main" sx={{ flexGrow: 1, p: { xs: 2, md: 3 }, width: { md: `calc(100% - ${DRAWER}px)` }, minWidth: 0 }}>
        <Toolbar />
        {me?.edition === "self_hosted" && <LicenceBanner />}
        <Outlet />
      </Box>
      <NotificationsPopover anchor={notifAnchor} onClose={() => setNotifAnchor(null)} />
    </Box>
  );
}
