import { useAuthStore } from "../store/authStore";
import type { UserRole } from "../types/auth/userRole";

export type { UserRole };

export const useUserRole = () => {
  const userRole = useAuthStore(state => state.userRole);
  const barangayAccountData = useAuthStore(state => state.barangayAccountData);
  const isAuthenticated = useAuthStore(state => state.isAuthenticated);

  const isBarangayOfficial = userRole === 'barangay_official';
  const isBarangayMember = userRole === 'barangay_member';
  const isLguOfficial = userRole === 'lgu_official';
  const isSuperAdmin = userRole === 'superadmin';
  
  const isValidRole = isBarangayOfficial || isBarangayMember || isLguOfficial || isSuperAdmin;
  const hasInvalidRole = !isValidRole;

  const getUserData = () => {
    if (isBarangayOfficial) return barangayAccountData;
    return null;
  };

  const getUserEmail = () => {
    if (isBarangayOfficial) return barangayAccountData?.barangay_account?.user?.email;
    return null;
  };

  const getDisplayName = () => {
    if (isBarangayOfficial) {
      const user = barangayAccountData?.barangay_account?.user;
      return user?.first_name 
        ? `${user.first_name} ${user.last_name || ''}`.trim()
        : barangayAccountData?.barangay_name || 'Barangay Official';
    }
    if (isBarangayMember) {
      return 'Barangay Member';
    }
    if (isLguOfficial) {
      return 'LGU Official';
    }
    if (isSuperAdmin) {
      return 'Super Admin';
    }
    return 'User';
  };

  return {
    userRole,
    isBarangayOfficial,
    isBarangayMember,
    isLguOfficial,
    isSuperAdmin,
    isAuthenticated,
    isValidRole,
    hasInvalidRole,
    getUserData,
    getUserEmail,
    getDisplayName,
  };
};
