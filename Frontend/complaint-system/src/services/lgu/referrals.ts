import { lguApi } from "../axios/apiServices";

export type ActiveDepartment = {
  id: number;
  name: string;
  abbreviation?: string | null;
  description?: string | null;
  office_address?: string | null;
  contact_number?: string | null;
  is_active: boolean;
};

export type CaseReferralRecord = {
  id: number;
  complaint_id: number;
  department_id: number;
  designated_officer?: string | null;
  designated_officer_position?: string | null;
  reason_for_referral?: string | null;
  requested_action?: string | null;
  reference_number?: string | null;
  receiving_officer?: string | null;
  receiving_officer_position?: string | null;
  letter_date?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  department?: ActiveDepartment | null;
};

export const getActiveDepartments = async (): Promise<ActiveDepartment[]> => {
  try {
    return await lguApi.get('/departments/active');
  } catch (error) {
    console.error('Error fetching active departments:', error);
    throw error;
  }
};

export const getComplaintReferrals = async (complaintId: number): Promise<CaseReferralRecord[]> => {
  try {
    return await lguApi.get(`/complaints/${complaintId}/referrals`);
  } catch (error) {
    console.error('Error fetching complaint referrals:', error);
    throw error;
  }
};

export const createCaseReferral = async (
  complaintId: number,
  payload: Partial<CaseReferralRecord>
): Promise<CaseReferralRecord> => {
  try {
    return await lguApi.post(`/complaints/${complaintId}/referrals`, payload);
  } catch (error) {
    console.error('Error creating referral:', error);
    throw error;
  }
};

export const downloadReferralDocument = async (referralId: number): Promise<Blob> => {
  try {
    return await lguApi.get<Blob>(`/referrals/${referralId}/document`, { responseType: 'blob' });
  } catch (error) {
    console.error('Error downloading referral document:', error);
    throw error;
  }
};
