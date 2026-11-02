import { Route, Routes, Navigate } from "react-router-dom"
import { LoginPage } from "./features/authentication/pages/Login"
import { SuperAdminLoginPage } from "./features/authentication/pages/SuperAdminLogin"
import { ForgotPasswordPage } from "./features/authentication/pages/ForgotPassword"
import { Dashboard } from "./features/barangay/pages/Dashboard"
import { useAuthStore } from "./store/authStore"
import { NetworkProvider } from "./context/NetworkContext"
import { BarangayRoute, BarangayMemberRoute, LguRoute, AuthRoutes, SuperAdminRoute } from "./routes/ProtectedRoutes"
import { NotFound } from "./features/general/NotFound"
import { useEffect } from "react"
import LoadingIndicator from "./features/general/LoadingIndicator"
import Navbar from "./layouts/Navbar"
import DashboardLayout from "./layouts/BarangayDashboardLayout"
import BarangayMemberDashboardLayout from "./layouts/BarangayMemberDashboardLayout"
import LguDashboardLayout from "./layouts/LguDashboardLayout"
import SuperAdminDashboardLayout from "./layouts/SuperAdminDashboardLayout"
import { IncidentPage } from "./features/barangay/pages/Incident"
import { IncidentDetails } from "./features/barangay/pages/IncidentDetails"
import { IncidentComplaints } from "./features/barangay/pages/IncidentComplaints"
import { ScheduledHearings } from "./features/barangay/pages/ScheduledHearings"
import { ArchiveIncidents as BarangayArchiveIncidents } from "./features/barangay/pages/ArchiveIncidents"
import { ComplaintDetails } from "./features/barangay/pages/ComplaintDetails"
import { AnnouncementsPage } from "./features/barangay/pages/Announcements"
import { EventsPage } from "./features/barangay/pages/Events"
import { LguDashboard } from "./features/lgu/pages/Dashboard"
import { LguIncidents } from "./features/lgu/pages/Incidents"
import { LguIncidentDetails } from "./features/lgu/pages/IncidentDetails"
import { LguIncidentComplaints } from "./features/lgu/pages/IncidentComplaints"
import { LguComplaintDetails } from "./features/lgu/pages/ComplaintDetails"
import { BarangayList } from "./features/lgu/pages/BarangayList"
import { BarangayIncidents } from "./features/lgu/pages/BarangayIncidents"
import { LguArchiveIncidents } from "./features/lgu/pages/ArchiveIncidents"
import { LguAnnouncements } from "./features/lgu/pages/Announcements"
import { MonthlyBarangayReports } from "./features/lgu/pages/MonthlyBarangayReports"
import { EmergencyIncidentsPage } from "./features/barangay/pages/EmergencyIncidents"
import { AssignedIncidentsPage } from "./features/barangay/pages/AssignedIncidents"
import MyDutyPage from "./features/barangayMember/pages/MyDuty"
import IncidentTrackingPage from "./features/general/pages/IncidentTrackingPage"
import { MonthlyReportDetails } from "./features/lgu/pages/MonthlyReportDetails"
import { CategoryIncidents } from "./features/lgu/pages/CategoryIncidents"
import { SuperAdminAccounts, SuperAdminCategories, SuperAdminDashboard, SuperAdminEmergencyHotlines, SuperAdminEvacuationCenters, SuperAdminResidentAccountManagement, SuperAdminUserDetails, SuperAdminUserRejectedComplaints, SuperAdminVerifyUsers } from "./features/superadmin/pages"
import { NotificationsPage } from "./features/general/pages/NotificationsPage"
import { FeedbacksPage } from "./features/general/pages/FeedbacksPage"
import KnowledgeBase from "./features/superadmin/pages/KnowledgeBase"
import { AccountDeletionPage } from "./features/general/pages/AccountDeletionPage"
import { MaryAppInstallPage } from "./features/general/pages/MaryAppInstallPage"
import { UsersGuidePage } from "./features/general/pages/UsersGuidePage"
import 'mapbox-gl/dist/mapbox-gl.css';

function App() {

  const refreshAccessToken = useAuthStore(state => state.refreshAccessToken);
  const isCheckingAuth = useAuthStore(state => state.isCheckingAuth);
  const isAuthenticated = useAuthStore(state => !!state.accessToken);
  const userRole = useAuthStore(state => state.userRole);
  const clearAuth = useAuthStore(state => state.clearAuth);

  const getDefaultDashboardPath = (role: string | null) => {
    if (role === "barangay_member") return "/member/assigned-incidents";
    if (role === "lgu_official") return "/lgu/dashboard";
    if (role === "superadmin") return "/superadmin/dashboard";
    return "/dashboard";
  };

  useEffect(() => {
    refreshAccessToken();
  }, [refreshAccessToken]);

  if (isCheckingAuth) {
    return <LoadingIndicator/>;
  }
  return (
    <>
      {isAuthenticated && !["/delete-account", "/mary-app", "/users-guide"].includes(window.location.pathname) && <Navbar onLogout={clearAuth} />}
      <NetworkProvider>
        <Routes>
          <Route path="/delete-account" element={<AccountDeletionPage />} />
          <Route path="/mary-app" element={<MaryAppInstallPage />} />
          <Route path="/users-guide" element={<UsersGuidePage />} />
          <Route
            path="/"
            element={
              <Navigate
                to={isAuthenticated ? getDefaultDashboardPath(userRole) : "/officials-login"}
                replace
              />
            }
          />
          {/* Barangay Official Routes */}
          <Route element={<BarangayRoute />}>
            <Route path="/dashboard/*" element={<DashboardLayout />}>
              <Route index element={<Dashboard />} />
              <Route path="incidents" element={<IncidentPage />} />
              <Route path="scheduled-hearings" element={<ScheduledHearings />} />
              <Route path="archive" element={<BarangayArchiveIncidents />} />
              <Route path="incidents/:incidentId" element={<IncidentDetails />} />
              <Route path="incidents/:incidentId/tracking" element={<IncidentTrackingPage />} />
              <Route path="incidents/:incidentId/complaints" element={<IncidentComplaints />} />
              <Route path="incidents/complaints/:id" element={<ComplaintDetails />} />
              <Route path="emergency-incidents" element={<EmergencyIncidentsPage />} />
              <Route path="announcements" element={<AnnouncementsPage />} />
              <Route path="events" element={<EventsPage />} />
              <Route path="feedbacks" element={<FeedbacksPage />} />
              <Route path="notifications" element={<NotificationsPage />} />
            </Route>
          </Route>

          {/* Barangay Member Routes */}
          <Route element={<BarangayMemberRoute />}>
            <Route path="/member/*" element={<BarangayMemberDashboardLayout />}>
              <Route path="assigned-incidents" element={<AssignedIncidentsPage />} />
              <Route path="my-duty" element={<MyDutyPage />} />
              <Route path="incidents/:incidentId" element={<IncidentDetails />} />
                <Route path="incidents/:incidentId/tracking" element={<IncidentTrackingPage />} />
                <Route path="incidents/:incidentId/complaints" element={<IncidentComplaints />} />
                <Route path="notifications" element={<NotificationsPage />} />
              </Route>
          </Route>

          {/* LGU Official Routes */}
          <Route element={<LguRoute />}>
            <Route path="/lgu/*" element={<LguDashboardLayout />}>
              <Route path="dashboard" element={<LguDashboard />} />
              <Route path="barangay-incidents" element={<BarangayList />} />
              <Route path="barangay-incidents/:barangayId" element={<BarangayIncidents />} />
              <Route path="incidents" element={<LguIncidents />} />
              <Route path="archive" element={<LguArchiveIncidents />} />
              <Route path="incidents/:incidentId" element={<LguIncidentDetails />} />
              <Route path="incidents/:incidentId/tracking" element={<IncidentTrackingPage />} />
              <Route path="incidents/:incidentId/complaints" element={<LguIncidentComplaints />} />
              <Route path="incidents/complaints/:id" element={<LguComplaintDetails />} />
              <Route path="monthly-reports" element={<MonthlyBarangayReports />} />
              <Route path="monthly-reports/:barangayId" element={<MonthlyReportDetails />} />
              <Route path="monthly-reports/:barangayId/category/:categoryName" element={<CategoryIncidents />} />
              <Route path="announcements" element={<LguAnnouncements />} />
              <Route path="feedbacks" element={<FeedbacksPage />} />
              <Route path="notifications" element={<NotificationsPage />} />
              {/* Additional LGU routes can be added here */}
            </Route>
          </Route>

          {/* Super Admin Routes */}
          <Route element={<SuperAdminRoute />}>
            <Route path="/superadmin/*" element={<SuperAdminDashboardLayout />}>
              <Route index element={<SuperAdminDashboard />} />
              <Route path="dashboard" element={<SuperAdminDashboard />} />
              <Route path="accounts" element={<SuperAdminAccounts />} />
              <Route path="resident-account-management" element={<SuperAdminResidentAccountManagement />} />
              <Route path="resident-account-management/rejected-complaints/:userId" element={<SuperAdminUserRejectedComplaints />} />
              <Route path="categories" element={<SuperAdminCategories />} />
              <Route path="emergency-hotlines" element={<SuperAdminEmergencyHotlines />} />
              <Route path="evacuation-centers" element={<SuperAdminEvacuationCenters />} />
              <Route path="verify-users" element={<SuperAdminVerifyUsers />} />
              <Route path="verify-users/:userId" element={<SuperAdminUserDetails />} />
              <Route path="notifications" element={<NotificationsPage />} />
              <Route path="knowledge-base" element={<KnowledgeBase />} />
            </Route>
          </Route>

          {/* Auth Routes (Login) */}
          <Route element={<AuthRoutes />}>
            <Route path="/officials-login" element={<LoginPage />} />
            <Route path="/superadmin-login" element={<SuperAdminLoginPage />} />
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          </Route>

          {/* 404 Not Found */}
          <Route path="*" element={<NotFound />} />
        </Routes>
      </NetworkProvider>
    </>
  )
}

export default App
