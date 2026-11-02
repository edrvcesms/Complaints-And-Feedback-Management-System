import { incidentsApi } from "../axios/apiServices";
import { buildIncidentActionFormData } from "./incidentActionFormData";
import type { Incident } from "../../types/complaints/incident";
import type { Complaint, StatusFilter } from "../../types/complaints/complaint";
import type { PaginatedResponse, PaginationQueryParams } from "../../types/general/pagination";
import { buildQueryString } from "../../utils/buildQuery";

export interface IncidentQueryParams extends PaginationQueryParams {
  sort?: "priority" | "first_reported_at" | "last_reported_at";
  order?: "asc" | "desc";
  severity_level?: Exclude<StatusFilter, "all">;
  severity_score_min?: number;
  severity_score_max?: number;
  complaint_status?: string;
  category_name?: string;
  date_from?: string; // YYYY-MM-DD
  date_to?: string;   // YYYY-MM-DD
}

export const getIncidents = async (params?: IncidentQueryParams): Promise<PaginatedResponse<Incident>> => {
  try {
    const queryString = buildQueryString(params || {});
    return await incidentsApi.get(`/?${queryString}`);
  } catch (error) {
    console.error("Error fetching incidents:", error);
    throw error;
  };
};

export const getAllIncidents = async (params?: IncidentQueryParams): Promise<PaginatedResponse<Incident>> => {
  try {
    const queryString = buildQueryString(params || {});
    return await incidentsApi.get(`/archive?${queryString}`);
  } catch (error) {
    console.error("Error fetching all incidents:", error);
    throw error;
  };
};

export const getAssignedIncidents = async (params?: IncidentQueryParams): Promise<PaginatedResponse<Incident>> => {
  try {
    const queryString = buildQueryString(params || {});
    return await incidentsApi.get(`/assigned?${queryString}`);
  } catch (error) {
    console.error("Error fetching assigned incidents:", error);
    throw error;
  }
};

export const getIncidentById = async (incidentId: number): Promise<Incident> => {
  try {
    return await incidentsApi.get(`/${incidentId}`);
  } catch (error) {
    console.error("Error fetching incident by ID:", error);
    throw error;
  };
};

export const getComplaintsByIncidentId = async (incidentId: number, params: PaginationQueryParams): Promise<PaginatedResponse<Complaint>> => {
  try {
    const queryString = buildQueryString(params || {});

    return await incidentsApi.get(`/${incidentId}/complaints?${queryString}`);

  } catch (error) {
    console.error("Error fetching complaints for incident:", error);
    throw error;
  }
};

export const resolveIncident = async (
  incidentId: number,
  payload: { actions_taken: string; attachments?: File[]; barangay_member_ids?: number[] }
): Promise<void> => {
  try {
    const formData = buildIncidentActionFormData(payload.actions_taken, undefined, payload.attachments, payload.barangay_member_ids);
    await incidentsApi.patch(`/${incidentId}/resolve`, formData);
  } catch (error) {
    console.error("Error resolving incident:", error);
    throw error;
  }
};

export const markIncidentUnresolvable = async (incidentId: number): Promise<{ message: string }> => {
  try {
    return await incidentsApi.patch(`/${incidentId}/unresolvable`);
  } catch (error) {
    console.error("Error marking incident as unresolvable:", error);
    throw error;
  }
};

export const reviewIncident = async (
  incidentId: number,
  payload: { actions_taken: string; attachments?: File[]; barangay_member_ids?: number[] },
  signal?: AbortSignal
): Promise<void> => {
  try {
    const formData = buildIncidentActionFormData(payload.actions_taken, undefined, payload.attachments, payload.barangay_member_ids);
    await incidentsApi.patch(`/${incidentId}/review`, formData, { signal });
  } catch (error) {
    console.error("Error reviewing incident:", error);
    throw error;
  }
};

export const rejectIncident = async (
  incidentId: number,
  payload: { actions_taken: string; rejection_category_id?: number; attachments?: File[]; barangay_member_ids?: number[] }
): Promise<void> => {
  try {
    const formData = buildIncidentActionFormData(
      payload.actions_taken,
      payload.rejection_category_id,
      payload.attachments,
      payload.barangay_member_ids
    );
    const endpoint =
      typeof payload.rejection_category_id === "number"
        ? `/${incidentId}/reject`
        : `/${incidentId}/reject-incident`;

    await incidentsApi.patch(endpoint, formData);
  } catch (error) {
    console.error("Error rejecting incident:", error);
    throw error;
  }
};

export const markIncidentAsViewed = async (incidentId: number): Promise<void> => {
  try {
    await incidentsApi.post(`/${incidentId}/mark-viewed`);
  } catch (error) {
    console.error("Error marking incident as viewed:", error);
    throw error;
  }
};

export const notifyHearing = async (incidentId: number, hearingDate: FormData): Promise<void> => {
  try {
    await incidentsApi.post(`/notify-hearing/${incidentId}`, hearingDate);
  } catch (error) {
    console.error("Error notifying hearing for incident:", error);
    throw error;
  }
};

export const markHearingAsSuccessful = async (incidentId: number, isSuccessful: boolean): Promise<void> => {
  try {
    const formData = new FormData();
    formData.append('is_successful', String(isSuccessful));
    await incidentsApi.post(`/mark-hearing/${incidentId}`, formData);
  } catch (error) {
    console.error('Error marking hearing status:', error);
    throw error;
  }
};

export const rescheduleHearing = async (incidentId: number, hearingDate: FormData): Promise<void> => {
  try {
    await incidentsApi.post(`/reschedule-hearing/${incidentId}`, hearingDate);
  } catch (error) {
    console.error('Error rescheduling hearing:', error);
    throw error;
  }
};

export const getScheduledHearings = async (params?: IncidentQueryParams): Promise<PaginatedResponse<Incident>> => {
  try {
    const queryString = buildQueryString(params || {});
    return await incidentsApi.get(`/scheduled-hearings?${queryString}`);
  } catch (error) {
    console.error("Error fetching scheduled hearings:", error);
    throw error;
  }
};