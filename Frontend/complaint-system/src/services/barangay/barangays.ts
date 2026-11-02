import { barangayApi } from "../axios/apiServices";
import type { BarangayAccountData } from "../../types/barangay/barangayAccount";
import type { PaginatedResponse } from "../../types/general/pagination";
import type { PaginationQueryParams } from "../../types/general/pagination";
import { buildQueryString } from "../../utils/buildQuery";

export interface BarangayMember {
  id: number;
  barangay_id: number;
  name: string;
  position: string;
}

export interface OnDutyBarangayMember extends BarangayMember {
  user_id?: number | null;
  user: {
    latitude?: string | null;
    longitude?: string | null;
    location_updated_at?: string | null;
  } | null;
}

export interface BarangayMemberDuty {
  name: string;
  position: string;
  start_of_duty: string | null;
  end_of_duty: string | null;
  is_on_duty: boolean;
}

export interface BarangayDutyUpdate {
  start_of_duty: string;
  end_of_duty: string | null;
}

export const getAllBarangays = async (params?: PaginationQueryParams): Promise<PaginatedResponse<BarangayAccountData>> => {
  try {
    const queryString = buildQueryString(params || {});
    return await barangayApi.get(`/all?${queryString}`);
  } catch (error) {
    console.error("Error fetching barangays:", error);
    throw error;
  }
};

export const getBarangayById = async (barangayId: number): Promise<BarangayAccountData> => {
  try {
    return await barangayApi.get(`/${barangayId}`);
  } catch (error) {
    console.error("Error fetching barangay by ID:", error);
    throw error;
  }
};

export const markBarangayIncidentsViewed = async (barangayId: number): Promise<{message: string; viewed_at: string}> => {
  try {
    return await barangayApi.post(`/${barangayId}/mark-viewed`);
  } catch (error) {
    console.error("Error marking barangay incidents as viewed:", error);
    throw error;
  }
};

export const getBarangayMembers = async (barangayId: number, onDutyOnly = false): Promise<BarangayMember[]> => {
  try {
    const query = onDutyOnly ? "?on_duty_only=true" : "";
    return await barangayApi.get(`/${barangayId}/members${query}`);
  } catch (error) {
    console.error("Error fetching barangay members:", error);
    throw error;
  }
};

export const getOnDutyBarangayMembers = async (barangayId: number): Promise<OnDutyBarangayMember[]> => {
  try {
    return await barangayApi.get(`/${barangayId}/members/current-location`);
  } catch (error) {
    console.error("Error fetching on-duty barangay member locations:", error);
    throw error;
  }
};

export const getMyBarangayDuty = async (): Promise<BarangayMemberDuty> =>
  barangayApi.get("/members/me/duty");

export const updateMyBarangayDuty = async (duty: BarangayDutyUpdate): Promise<BarangayMemberDuty> =>
  barangayApi.put("/members/me/duty", duty);

export const addBarangayMember = async (barangayId: number, payload: { name: string; position: string; email: string; password: string }) => {
  return await barangayApi.post(`/${barangayId}/add-member`, payload);
};

export const removeBarangayMember = async (barangayId: number, memberId: number) => {
  return await barangayApi.delete(`/${barangayId}/remove-member/${memberId}`);
};