import { create } from "zustand";
import type { BarangayAccountData } from "../types/barangay/barangayAccount";
import type { UserRole } from "../types/auth/userRole";
import { refreshToken } from "../services/authentication/token";
import { logoutBarangayAccount } from "../services/authentication/auth";

let refreshAccessTokenPromise: Promise<void> | null = null;

interface AuthState {
    accessToken: string | null;
    setAccessToken: (token: string | null) => void;
    isCheckingAuth: boolean;
    setIsCheckingAuth: (checking: boolean) => void;
    barangayAccountData: BarangayAccountData | null;
    setBarangayAccountData: (data: BarangayAccountData | null) => void;
    userRole: UserRole | null;
    setUserRole: (role: UserRole | null) => void;
    isLoading: boolean;
    setIsLoading: (loading: boolean) => void;
    isAuthenticated: boolean;
    mapDataFromBackend: (data: any) => void;
    clearAuth: () => Promise<void>;
    clearAuthLocal: () => void;
    refreshAccessToken: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
    accessToken: null,
    setAccessToken: (token) => set({ accessToken: token }),
    barangayAccountData: null,
    setBarangayAccountData: (data) => set({ barangayAccountData: data }),
    userRole: null,
    setUserRole: (role) => set({ userRole: role }),
    isCheckingAuth: true,
    setIsCheckingAuth: (checking) => set({ isCheckingAuth: checking }),
    isLoading: false,
    setIsLoading: (loading) => set({ isLoading: loading }),
    isAuthenticated: false,
    mapDataFromBackend: (data: any) => {
        
        let role = data.role || null;
        let barangayData = null;

        if (data.barangayAccountData) {
            barangayData = data.barangayAccountData;
        }
        

        const validRoles: UserRole[] = ['barangay_official', 'barangay_member', 'lgu_official', 'superadmin'];
        const isValidRole = role && validRoles.includes(role as UserRole);

        set({
            barangayAccountData: barangayData,
            userRole: role,
            isAuthenticated: isValidRole
        });
    },
    clearAuth: async () => {
        set({ isLoading: true });
        try {
            await logoutBarangayAccount();
        } catch (error) {
            console.warn("Logout failed, but clearing local auth anyway:", error);
        } finally {
            set({
                accessToken: null,
                barangayAccountData: null,
                userRole: null,
                isAuthenticated: false,
                isLoading: false
            });
        }
    },
    clearAuthLocal: () => {
        set({
            accessToken: null,
            barangayAccountData: null,
            userRole: null,
            isAuthenticated: false,
            isLoading: false
        });
    },
    refreshAccessToken: async () => {
        if (refreshAccessTokenPromise) {
            return refreshAccessTokenPromise;
        }

        set({ isCheckingAuth: true });

        refreshAccessTokenPromise = (async () => {
            try {
                const data = await refreshToken();

                if (data?.access_token) {
                    set({
                        accessToken: data.access_token,
                        isAuthenticated: true
                    });
                    
                    const store = useAuthStore.getState();
                    store.mapDataFromBackend(data);
                } else {
                    set({
                        accessToken: null,
                        barangayAccountData: null,
                        userRole: null,
                        isAuthenticated: false
                    });
                }
            } catch (error) {
                set({
                    accessToken: null,
                    barangayAccountData: null,
                    userRole: null,
                    isAuthenticated: false
                });
            } finally {
                set({ isCheckingAuth: false });
                refreshAccessTokenPromise = null;
            }
        })();

        return refreshAccessTokenPromise;
    }
}));

export const useBarangayStore = useAuthStore;