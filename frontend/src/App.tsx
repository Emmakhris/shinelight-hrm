import { Alert, Box } from "@mui/material";
import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import LoginPage from "./auth/LoginPage";
import { Loading } from "./components/Feedback";
import Layout from "./components/Layout";

const Home = lazy(() => import("./pages/Home"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Analytics = lazy(() => import("./pages/Analytics"));
const Reports = lazy(() => import("./pages/Reports"));
const Inbox = lazy(() => import("./pages/Inbox"));
const MyRequests = lazy(() => import("./pages/MyRequests"));
const Delegations = lazy(() => import("./pages/Delegations"));
const ChangePassword = lazy(() => import("./pages/me/ChangePassword"));
const Profile = lazy(() => import("./pages/me/Profile"));
const MyPayslips = lazy(() => import("./pages/me/MyPayslips"));
const MyDocuments = lazy(() => import("./pages/me/MyDocuments"));
const MyLoans = lazy(() => import("./pages/me/MyLoans"));
const Team = lazy(() => import("./pages/me/Team"));
const Directory = lazy(() => import("./pages/me/Directory"));
const Announcements = lazy(() => import("./pages/me/Announcements"));
const EmployeeList = lazy(() => import("./pages/employees/EmployeeList"));
const EmployeeDetail = lazy(() => import("./pages/employees/EmployeeDetail"));
const ImportPage = lazy(() => import("./pages/employees/Import"));
const DataQuality = lazy(() => import("./pages/employees/DataQuality"));
const ChangeRequests = lazy(() => import("./pages/employees/ChangeRequests"));
const OrgChart = lazy(() => import("./pages/org/OrgChart"));
const Departments = lazy(() => import("./pages/org/Departments"));
const Positions = lazy(() => import("./pages/org/Positions"));
const Grades = lazy(() => import("./pages/org/Grades"));
const JobTitles = lazy(() => import("./pages/org/JobTitles"));
const Locations = lazy(() => import("./pages/org/Locations"));
const MyLeave = lazy(() => import("./pages/leave/MyLeave"));
const LeaveRequests = lazy(() => import("./pages/leave/LeaveRequests"));
const LeaveCalendar = lazy(() => import("./pages/leave/LeaveCalendar"));
const LeaveBalances = lazy(() => import("./pages/leave/LeaveBalances"));
const LeaveSetup = lazy(() => import("./pages/leave/LeaveSetup"));
const MyAttendance = lazy(() => import("./pages/attendance/MyAttendance"));
const TeamToday = lazy(() => import("./pages/attendance/TeamToday"));
const Days = lazy(() => import("./pages/attendance/Days"));
const Roster = lazy(() => import("./pages/attendance/Roster"));
const Summaries = lazy(() => import("./pages/attendance/Summaries"));
const AttendanceSetup = lazy(() => import("./pages/attendance/AttendanceSetup"));
const Runs = lazy(() => import("./pages/payroll/Runs"));
const RunDetail = lazy(() => import("./pages/payroll/RunDetail"));
const EmployeePay = lazy(() => import("./pages/payroll/EmployeePay"));
const Loans = lazy(() => import("./pages/payroll/Loans"));
const PayrollSetup = lazy(() => import("./pages/payroll/PayrollSetup"));
const Documents = lazy(() => import("./pages/documents/Documents"));
const Templates = lazy(() => import("./pages/documents/Templates"));
const Licenses = lazy(() => import("./pages/hospital/Licenses"));
const Matrix = lazy(() => import("./pages/hospital/Matrix"));
const Staffing = lazy(() => import("./pages/hospital/Staffing"));
const Users = lazy(() => import("./pages/admin/Users"));
const Roles = lazy(() => import("./pages/admin/Roles"));
const Workflows = lazy(() => import("./pages/admin/Workflows"));
const Settings = lazy(() => import("./pages/admin/Settings"));
const NotificationsAdmin = lazy(() => import("./pages/admin/NotificationsAdmin"));
const Integrations = lazy(() => import("./pages/admin/Integrations"));
const Audit = lazy(() => import("./pages/admin/Audit"));

function Guard({ perm, scope, feature, children }: { perm?: string | string[]; scope?: string; feature?: string; children: ReactNode }) {
  const { can, feature: hasFeature } = useAuth();
  if ((perm && !can(perm, scope)) || (feature && !hasFeature(feature))) {
    return <Alert severity="warning">You do not have access to this page. Contact HR if you believe this is an error.</Alert>;
  }
  return <>{children}</>;
}

export default function App() {
  const { me, loading } = useAuth();
  if (loading) return <Box sx={{ pt: 20 }}><Loading label="Starting ShineLight HRM…" /></Box>;
  if (!me) {
    return (
      <Routes>
        <Route path="/reset-password" element={<LoginPage />} />
        <Route path="*" element={<LoginPage />} />
      </Routes>
    );
  }
  const g = (el: ReactNode, perm?: string | string[], opts: { scope?: string; feature?: string } = {}) =>
    <Guard perm={perm} scope={opts.scope} feature={opts.feature}>{el}</Guard>;
  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        <Route path="/change-password" element={<Box sx={{ p: 3, maxWidth: 520, mx: "auto" }}><ChangePassword /></Box>} />
        <Route element={me.must_change_password ? <Navigate to="/change-password" replace /> : <Layout />}>
          <Route index element={<Home />} />
          <Route path="dashboard" element={g(<Dashboard />, "reports.view")} />
          <Route path="analytics" element={g(<Analytics />, "reports.view")} />
          <Route path="reports" element={g(<Reports />, "reports.view")} />
          <Route path="inbox" element={<Inbox />} />
          <Route path="me/requests" element={<MyRequests />} />
          <Route path="delegations" element={<Delegations />} />
          <Route path="me/profile" element={<Profile />} />
          <Route path="me/payslips" element={<MyPayslips />} />
          <Route path="me/documents" element={<MyDocuments />} />
          <Route path="me/loans" element={<MyLoans />} />
          <Route path="team" element={<Team />} />
          <Route path="directory" element={<Directory />} />
          <Route path="announcements" element={<Announcements />} />
          <Route path="employees" element={g(<EmployeeList />, "employees.view")} />
          <Route path="employees/import" element={g(<ImportPage />, "employees.import")} />
          <Route path="employees/data-quality" element={g(<DataQuality />, "employees.view", { scope: "organization" })} />
          <Route path="employees/change-requests" element={g(<ChangeRequests />, "employees.change")} />
          <Route path="employees/:id" element={g(<EmployeeDetail />, "employees.view")} />
          <Route path="org/chart" element={g(<OrgChart />, "organization.view")} />
          <Route path="org/departments" element={g(<Departments />, "organization.manage")} />
          <Route path="org/positions" element={g(<Positions />, "organization.manage")} />
          <Route path="org/grades" element={g(<Grades />, "organization.manage")} />
          <Route path="org/job-titles" element={g(<JobTitles />, "organization.manage")} />
          <Route path="org/locations" element={g(<Locations />, "organization.manage")} />
          <Route path="leave/my" element={<MyLeave />} />
          <Route path="leave/requests" element={g(<LeaveRequests />, "leave.approve")} />
          <Route path="leave/calendar" element={<LeaveCalendar />} />
          <Route path="leave/balances" element={g(<LeaveBalances />, "leave.manage")} />
          <Route path="leave/setup" element={g(<LeaveSetup />, "leave.manage")} />
          <Route path="attendance/my" element={<MyAttendance />} />
          <Route path="attendance/team" element={g(<TeamToday />, "attendance.approve")} />
          <Route path="attendance/days" element={g(<Days />, "attendance.approve")} />
          <Route path="attendance/roster" element={g(<Roster />, "attendance.view")} />
          <Route path="attendance/summaries" element={g(<Summaries />, "attendance.manage")} />
          <Route path="attendance/setup" element={g(<AttendanceSetup />, "attendance.manage")} />
          <Route path="payroll/runs" element={g(<Runs />, "payroll.view", { feature: "payroll" })} />
          <Route path="payroll/runs/:id" element={g(<RunDetail />, "payroll.view", { feature: "payroll" })} />
          <Route path="payroll/employees" element={g(<EmployeePay />, "payroll.prepare", { feature: "payroll" })} />
          <Route path="payroll/loans" element={g(<Loans />, "payroll.view", { feature: "payroll" })} />
          <Route path="payroll/setup" element={g(<PayrollSetup />, "payroll.manage", { feature: "payroll" })} />
          <Route path="documents" element={g(<Documents />, "documents.upload")} />
          <Route path="documents/templates" element={g(<Templates />, "documents.manage")} />
          <Route path="hospital/licenses" element={g(<Licenses />, "hospital.view", { feature: "hospital" })} />
          <Route path="hospital/matrix" element={g(<Matrix />, "hospital.view", { feature: "hospital" })} />
          <Route path="hospital/staffing" element={g(<Staffing />, "hospital.view", { feature: "hospital" })} />
          <Route path="admin/users" element={g(<Users />, "admin.users")} />
          <Route path="admin/roles" element={g(<Roles />, "admin.roles")} />
          <Route path="admin/workflows" element={g(<Workflows />, "workflow.manage")} />
          <Route path="admin/settings" element={g(<Settings />, "admin.settings")} />
          <Route path="admin/notifications" element={g(<NotificationsAdmin />, "notifications.manage")} />
          <Route path="admin/integrations" element={g(<Integrations />, "integrations.manage")} />
          <Route path="admin/audit" element={g(<Audit />, "audit.view")} />
          <Route path="*" element={<Alert severity="info">Page not found.</Alert>} />
        </Route>
      </Routes>
    </Suspense>
  );
}
