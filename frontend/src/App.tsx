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
const ReportBuilder = lazy(() => import("./pages/ReportBuilder"));
const Forecasts = lazy(() => import("./pages/Forecasts"));
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
const SingleSignOn = lazy(() => import("./pages/admin/SingleSignOn"));
const AssistantSettings = lazy(() => import("./pages/admin/AssistantSettings"));
const Assistant = lazy(() => import("./pages/me/Assistant"));
const HelpDesk = lazy(() => import("./pages/helpdesk/HelpDesk"));
const TicketDetail = lazy(() => import("./pages/helpdesk/TicketDetail"));
const Queue = lazy(() => import("./pages/helpdesk/Queue"));
const HelpdeskMetrics = lazy(() => import("./pages/helpdesk/Metrics"));
const Knowledge = lazy(() => import("./pages/helpdesk/Knowledge"));
const HelpdeskSetup = lazy(() => import("./pages/helpdesk/HelpdeskSetup"));
const MyExpenses = lazy(() => import("./pages/expenses/MyExpenses"));
const ExpenseAdmin = lazy(() => import("./pages/expenses/ExpenseAdmin"));
const ExpenseSetup = lazy(() => import("./pages/expenses/ExpenseSetup"));
const Reviews = lazy(() => import("./pages/compensation/Reviews"));
const ReviewDetail = lazy(() => import("./pages/compensation/ReviewDetail"));
const Bonuses = lazy(() => import("./pages/compensation/Bonuses"));
const MyBenefits = lazy(() => import("./pages/compensation/MyBenefits"));
const BenefitsAdmin = lazy(() => import("./pages/compensation/BenefitsAdmin"));
const MySignatures = lazy(() => import("./pages/me/MySignatures"));
const Requisitions = lazy(() => import("./pages/recruitment/Requisitions"));
const Vacancies = lazy(() => import("./pages/recruitment/Vacancies"));
const VacancyPipeline = lazy(() => import("./pages/recruitment/VacancyPipeline"));
const ApplicationDetail = lazy(() => import("./pages/recruitment/ApplicationDetail"));
const Candidates = lazy(() => import("./pages/recruitment/Candidates"));
const RecruitmentAnalytics = lazy(() => import("./pages/recruitment/RecruitmentAnalytics"));
const MyInterviews = lazy(() => import("./pages/recruitment/MyInterviews"));
const InternalJobs = lazy(() => import("./pages/me/InternalJobs"));
const Onboardings = lazy(() => import("./pages/onboarding/Onboardings"));
const OnboardingDetail = lazy(() => import("./pages/onboarding/OnboardingDetail"));
const OnboardingSetup = lazy(() => import("./pages/onboarding/OnboardingSetup"));
const OnboardingTasks = lazy(() => import("./pages/onboarding/MyTasks"));
const Probation = lazy(() => import("./pages/onboarding/Probation"));
const MyPerformance = lazy(() => import("./pages/performance/MyPerformance"));
const TeamAppraisals = lazy(() => import("./pages/performance/TeamAppraisals"));
const AppraisalDetail = lazy(() => import("./pages/performance/AppraisalDetail"));
const PerfCycles = lazy(() => import("./pages/performance/Cycles"));
const PerfCycleDetail = lazy(() => import("./pages/performance/CycleDetail"));
const FeedbackRequests = lazy(() => import("./pages/performance/FeedbackRequests"));
const Plans = lazy(() => import("./pages/performance/Plans"));
const PerformanceSetup = lazy(() => import("./pages/performance/PerformanceSetup"));
const MyLearning = lazy(() => import("./pages/learning/MyLearning"));
const EnrollmentPage = lazy(() => import("./pages/learning/EnrollmentPage"));
const TeamLearning = lazy(() => import("./pages/learning/TeamLearning"));
const LearningAdmin = lazy(() => import("./pages/learning/LearningAdmin"));
const LearningCompliance = lazy(() => import("./pages/learning/Compliance"));
const MyCases = lazy(() => import("./pages/relations/MyCases"));
const ERCases = lazy(() => import("./pages/relations/Cases"));
const CaseDetail = lazy(() => import("./pages/relations/CaseDetail"));
const AssetsPage = lazy(() => import("./pages/assets/Assets"));
const MyAssets = lazy(() => import("./pages/assets/MyAssets"));
const Exits = lazy(() => import("./pages/offboarding/Exits"));
const ExitDetail = lazy(() => import("./pages/offboarding/ExitDetail"));
const MyExit = lazy(() => import("./pages/offboarding/MyExit"));
const EngagementHub = lazy(() => import("./pages/engagement/Engagement"));
const EngagementAdmin = lazy(() => import("./pages/engagement/EngagementAdmin"));
const SafetyPage = lazy(() => import("./pages/safety/Safety"));
const IncidentDetail = lazy(() => import("./pages/safety/IncidentDetail"));
const OccupationalHealth = lazy(() => import("./pages/safety/OccupationalHealth"));
const MySafety = lazy(() => import("./pages/safety/MySafety"));
const MyCareer = lazy(() => import("./pages/talent/MyCareer"));
const TalentReview = lazy(() => import("./pages/talent/TalentReview"));
const PlanningPage = lazy(() => import("./pages/talent/Planning"));
const PlanDetail = lazy(() => import("./pages/talent/Planning").then((m) => ({ default: m.PlanDetail })));
const Careers = lazy(() => import("./pages/public/Careers"));
const OfferResponse = lazy(() => import("./pages/public/OfferResponse"));
const Signup = lazy(() => import("./pages/public/Signup"));
const Platform = lazy(() => import("./pages/platform/Platform"));

// Public pages (career site and offer response) work signed in or not.
const publicRoutes = [
  <Route key="c" path="/careers/:org" element={<Careers />} />,
  <Route key="cv" path="/careers/:org/:id" element={<Careers />} />,
  <Route key="o" path="/offer/:token" element={<OfferResponse />} />,
  <Route key="s" path="/signup" element={<Signup />} />,
];

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
      <Suspense fallback={<Loading />}>
        <Routes>
          {publicRoutes}
          <Route path="/reset-password" element={<LoginPage />} />
          <Route path="*" element={<LoginPage />} />
        </Routes>
      </Suspense>
    );
  }
  const g = (el: ReactNode, perm?: string | string[], opts: { scope?: string; feature?: string } = {}) =>
    <Guard perm={perm} scope={opts.scope} feature={opts.feature}>{el}</Guard>;
  if (me.is_platform_admin) {
    // Platform operators have no organization: they only get the platform console.
    return (
      <Suspense fallback={<Loading />}>
        <Routes>
          <Route path="/change-password" element={<Box sx={{ p: 3, maxWidth: 520, mx: "auto" }}><ChangePassword /></Box>} />
          <Route path="*" element={me.must_change_password ? <Navigate to="/change-password" replace /> : <Platform />} />
        </Routes>
      </Suspense>
    );
  }
  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        {publicRoutes}
        <Route path="/change-password" element={<Box sx={{ p: 3, maxWidth: 520, mx: "auto" }}><ChangePassword /></Box>} />
        <Route element={me.must_change_password ? <Navigate to="/change-password" replace /> : <Layout />}>
          <Route index element={<Home />} />
          <Route path="dashboard" element={g(<Dashboard />, "reports.view")} />
          <Route path="analytics" element={g(<Analytics />, "reports.view")} />
          <Route path="reports" element={g(<Reports />, "reports.view")} />
          <Route path="reports/builder" element={g(<ReportBuilder />, "reports.view")} />
          <Route path="forecasts" element={g(<Forecasts />, "reports.view")} />
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
          <Route path="admin/sso" element={g(<SingleSignOn />, "admin.settings")} />
          <Route path="admin/assistant" element={g(<AssistantSettings />, "admin.settings")} />
          <Route path="assistant" element={<Assistant />} />
          <Route path="helpdesk" element={<HelpDesk />} />
          <Route path="helpdesk/kb" element={<Knowledge />} />
          <Route path="helpdesk/tickets/:id" element={<TicketDetail />} />
          <Route path="helpdesk/queue" element={g(<Queue />, ["servicedesk.agent", "servicedesk.manage"])} />
          <Route path="helpdesk/metrics" element={g(<HelpdeskMetrics />, ["servicedesk.manage", "reports.view"])} />
          <Route path="helpdesk/setup" element={g(<HelpdeskSetup />, "servicedesk.manage")} />
          <Route path="expenses/my" element={<MyExpenses />} />
          <Route path="expenses/manage" element={g(<ExpenseAdmin />, ["expenses.manage", "expenses.pay"])} />
          <Route path="expenses/setup" element={g(<ExpenseSetup />, "expenses.manage")} />
          <Route path="compensation/reviews" element={g(<Reviews />, "compensation.view")} />
          <Route path="compensation/reviews/:id" element={g(<ReviewDetail />, "compensation.view")} />
          <Route path="compensation/bonuses" element={g(<Bonuses />, "compensation.view")} />
          <Route path="me/benefits" element={<MyBenefits />} />
          <Route path="benefits/admin" element={g(<BenefitsAdmin />, "benefits.manage")} />
          <Route path="me/signatures" element={<MySignatures />} />
          <Route path="me/jobs" element={<InternalJobs />} />
          <Route path="recruitment/requisitions" element={g(<Requisitions />, ["recruitment.requisition", "recruitment.view"])} />
          <Route path="recruitment/vacancies" element={g(<Vacancies />, "recruitment.view")} />
          <Route path="recruitment/vacancies/:id" element={g(<VacancyPipeline />, "recruitment.view")} />
          <Route path="recruitment/applications/:id" element={g(<ApplicationDetail />, "recruitment.view")} />
          <Route path="recruitment/candidates" element={g(<Candidates />, "recruitment.view")} />
          <Route path="recruitment/analytics" element={g(<RecruitmentAnalytics />, "recruitment.view")} />
          <Route path="recruitment/my-interviews" element={<MyInterviews />} />
          <Route path="onboarding" element={g(<Onboardings />, "onboarding.view")} />
          <Route path="onboarding/my-tasks" element={<OnboardingTasks />} />
          <Route path="onboarding/probation" element={<Probation />} />
          <Route path="onboarding/setup" element={g(<OnboardingSetup />, "onboarding.manage")} />
          <Route path="onboarding/:id" element={g(<OnboardingDetail />, "onboarding.view")} />
          <Route path="talent/me" element={<MyCareer />} />
          <Route path="talent" element={<TalentReview />} />
          <Route path="planning" element={g(<PlanningPage />, "planning.view")} />
          <Route path="planning/:id" element={g(<PlanDetail />, "planning.view")} />
          <Route path="engagement" element={<EngagementHub />} />
          <Route path="engagement/admin" element={g(<EngagementAdmin />, "engagement.manage")} />
          <Route path="safety" element={g(<SafetyPage />, "ohs.view")} />
          <Route path="safety/my" element={<MySafety />} />
          <Route path="safety/incidents/:id" element={<IncidentDetail />} />
          <Route path="safety/occupational-health" element={g(<OccupationalHealth />, "ohs.medical")} />
          <Route path="relations/my" element={<MyCases />} />
          <Route path="relations" element={g(<ERCases />, ["relations.manage", "relations.view_all"])} />
          <Route path="relations/cases/:id" element={g(<CaseDetail />, ["relations.manage", "relations.view_all"])} />
          <Route path="assets" element={g(<AssetsPage />, "assets.view")} />
          <Route path="assets/my" element={<MyAssets />} />
          <Route path="offboarding" element={g(<Exits />, ["offboarding.view", "assets.manage", "payroll.prepare", "expenses.pay"])} />
          <Route path="offboarding/my" element={<MyExit />} />
          <Route path="offboarding/:id" element={<ExitDetail />} />
          <Route path="learning" element={<MyLearning />} />
          <Route path="learning/enrollments/:id" element={<EnrollmentPage />} />
          <Route path="learning/team" element={<TeamLearning />} />
          <Route path="learning/admin" element={g(<LearningAdmin />, "learning.manage")} />
          <Route path="learning/compliance" element={g(<LearningCompliance />, ["learning.manage", "learning.view"], { scope: "department" })} />
          <Route path="performance/my" element={<MyPerformance />} />
          <Route path="performance/team" element={<TeamAppraisals />} />
          <Route path="performance/appraisals/:id" element={<AppraisalDetail />} />
          <Route path="performance/feedback" element={<FeedbackRequests />} />
          <Route path="performance/plans" element={<Plans />} />
          <Route path="performance/cycles" element={g(<PerfCycles />, "performance.manage")} />
          <Route path="performance/cycles/:id" element={g(<PerfCycleDetail />, "performance.manage")} />
          <Route path="performance/setup" element={g(<PerformanceSetup />, "performance.manage")} />
          <Route path="*" element={<Alert severity="info">Page not found.</Alert>} />
        </Route>
      </Routes>
    </Suspense>
  );
}
