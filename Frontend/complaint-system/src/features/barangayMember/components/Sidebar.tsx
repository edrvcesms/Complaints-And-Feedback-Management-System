import { CalendarClock, ClipboardList } from "lucide-react";
import { Sidebar as GenericSidebar } from "../../general";

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ isOpen, onClose }) => {
  const NAV_ITEMS = [
    { path: "/member/assigned-incidents", label: "Assigned Incidents", icon: <ClipboardList className="h-5 w-5" />, end: true, group: "Member" },
    { path: "/member/my-duty", label: "My Duty", icon: <CalendarClock className="h-5 w-5" />, end: true, group: "Member" },
  ];

  return (
    <GenericSidebar
      isOpen={isOpen}
      onClose={onClose}
      navItems={NAV_ITEMS}
      navigationLabel="Barangay Member Navigation"
      footerText="Barangay Member Portal"
    />
  );
};
