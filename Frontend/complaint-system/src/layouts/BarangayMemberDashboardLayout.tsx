import { Sidebar } from "../features/barangayMember/components/Sidebar";
import { MemberLocationReporter } from "../features/barangayMember/components/MemberLocationReporter";
import { DashboardLayout } from "./DashboardLayout";

export const BarangayMemberDashboardLayout: React.FC = () => (
  <>
    <MemberLocationReporter />
    <DashboardLayout SidebarComponent={Sidebar} />
  </>
);

export default BarangayMemberDashboardLayout;
