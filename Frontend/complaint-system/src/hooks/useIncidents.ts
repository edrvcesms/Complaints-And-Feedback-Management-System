import { getIncidents, getAllIncidents, getAssignedIncidents, getScheduledHearings, getIncidentById, getComplaintsByIncidentId, resolveIncident, markIncidentUnresolvable, rejectIncident, reviewIncident, markIncidentAsViewed, notifyHearing } from "../services/incidents/incidents";
import { endorseIncidentToLgu } from "../services/endorsement/incidentEndorsement";
import { getForwardedIncidents, getAllForwardedIncidents } from "../services/lgu/forwardedIncidents";
import { fetchRejectionCategories } from "../services/category/rejectionCategory";
import { useQuery, useMutation, keepPreviousData } from "@tanstack/react-query";
import { queryClient } from "../main";
import type { Incident } from "../types/complaints/incident";
import type { Complaint } from "../types/complaints/complaint";
import { markHearingAsSuccessful, rescheduleHearing } from "../services/incidents/incidents";
import type { RejectionCategory } from "../types/general/category";
import type { PaginatedResponse, PaginationQueryParams } from "../types/general/pagination";
import type { IncidentQueryParams } from "../services/incidents/incidents";

const invalidateIncidentQueries = () => Promise.all([
  queryClient.invalidateQueries({ queryKey: ["incidents"] }),
  queryClient.invalidateQueries({ queryKey: ["assignedIncidents"] }),
  queryClient.invalidateQueries({ queryKey: ["complaints"] }),
  queryClient.invalidateQueries({ queryKey: ["complaint-stats"] }),
  queryClient.invalidateQueries({ queryKey: ["allForwardedIncidents"] }),
  queryClient.invalidateQueries({ queryKey: ["forwardedIncidents"] }),
  queryClient.invalidateQueries({ queryKey: ["archiveIncidents"] }),
  queryClient.invalidateQueries({ queryKey: ["scheduledHearings"] }),
]);

type ReviewIncidentPayload = {
  actions_taken: string;
  attachments?: File[];
  barangay_member_ids?: number[];
  signal?: AbortSignal;
};

export const useIncidents = (params: IncidentQueryParams) => {
  const { data, isLoading, isFetching, error } = useQuery<PaginatedResponse<Incident>>({
    queryKey: ["incidents", params.page,
      params.page_size,
      params.search,
      params.sort,
      params.order,
      params.severity_level,
      params.complaint_status,
      params.category_name,
      params.search,
      params.date_from,
      params.date_to,],
    queryFn: () => getIncidents(params),
    placeholderData: keepPreviousData,
  });

  return {
    incidents: data?.data ?? [],
    pagination: data?.pagination,
    isLoading,
    isFetching,
    error,
  };
};

export const useAllIncidents = (params: IncidentQueryParams) => {
  const { data, isLoading, isFetching, error } = useQuery<PaginatedResponse<Incident>>({
    queryKey: [
      "archiveIncidents",
      params.page,
      params.page_size,
      params.search,
      params.sort,
      params.order,
      params.complaint_status,
      params.category_name,
      params.date_from,
      params.date_to,
    ],
    queryFn: () => getAllIncidents(params),
    placeholderData: keepPreviousData,
  });

  return {
    incidents: data?.data ?? [],
    pagination: data?.pagination,
    isLoading,
    isFetching,
    error,
  };
};

export const useAssignedIncidents = (params: IncidentQueryParams) => {
  const { data, isLoading, isFetching, error } = useQuery<PaginatedResponse<Incident>>({
    queryKey: [
      "assignedIncidents",
      params.page,
      params.page_size,
      params.search,
      params.sort,
      params.order,
      params.complaint_status,
      params.category_name,
      params.severity_level,
      params.date_from,
      params.date_to,
    ],
    queryFn: () => getAssignedIncidents(params),
    placeholderData: keepPreviousData,
    refetchOnMount: "always",
    refetchOnWindowFocus: true,
  });

  return {
    incidents: data?.data ?? [],
    pagination: data?.pagination,
    isLoading,
    isFetching,
    error,
  };
};

export const useIncidentDetails = (incidentId: number) => {
  const { data, isLoading, error } = useQuery<Incident>({
    queryKey: ["incidents", incidentId],
    queryFn: () => getIncidentById(incidentId),
    refetchOnMount: "always",
    refetchOnWindowFocus: true,
  });

  return {
    incident: data,
    isLoading,
    error,
  };
};

export const useIncidentComplaints = (
  incidentId: number,
  enabled: boolean = false,
  params: PaginationQueryParams = { page: 1, page_size: 10 }
) => {
  const { data, isLoading, error, refetch } = useQuery<PaginatedResponse<Complaint>>({
    queryKey: ["incidents", incidentId, "complaints", params.page, params.page_size, params.search],
    queryFn: () => getComplaintsByIncidentId(incidentId, params),
    enabled,
  });

  return {
    complaints: data?.data ?? [],
    pagination: data?.pagination,
    isLoading,
    error,
    refetch,
  };
};

export const useResolveIncident = (incidentId: number) => {
  const mutation = useMutation({
    mutationKey: ["resolveIncident", incidentId],
    mutationFn: (payload: { actions_taken: string; attachments?: File[]; barangay_member_ids?: number[] }) =>
      resolveIncident(incidentId, payload),
    onSuccess: invalidateIncidentQueries,
  });
  return mutation;
};

export const useMarkIncidentUnresolvable = (incidentId: number) =>
  useMutation({
    mutationKey: ["markIncidentUnresolvable", incidentId],
    mutationFn: () => markIncidentUnresolvable(incidentId),
    onSuccess: invalidateIncidentQueries,
  });

export const useReviewIncident = (incidentId: number) => {
  const mutation = useMutation({
    mutationKey: ["reviewIncident", incidentId],
    mutationFn: (payload: ReviewIncidentPayload) =>
      reviewIncident(
        incidentId,
        { actions_taken: payload.actions_taken, attachments: payload.attachments, barangay_member_ids: payload.barangay_member_ids },
        payload.signal
      ),
    onSuccess: invalidateIncidentQueries,
  });
  return mutation;
};

export const useForwardIncidentToLgu = (incidentId: number) => {
  const mutation = useMutation({
    mutationKey: ["forwardIncidentToLgu", incidentId],
    mutationFn: (payload: { actions_taken: string; attachments?: File[] }) =>
      endorseIncidentToLgu(incidentId, payload),
    onSuccess: invalidateIncidentQueries,
  });
  return mutation;
};

export const useRejectIncident = (incidentId: number) => {
  const mutation = useMutation({
    mutationKey: ["rejectIncident", incidentId],
    mutationFn: (payload: { actions_taken: string; rejection_category_id?: number; attachments?: File[]; barangay_member_ids?: number[] }) =>
      rejectIncident(incidentId, payload),
    onSuccess: invalidateIncidentQueries,
  });
  return mutation;
}

export const useRejectionCategories = () => {
  const { data, isLoading, error } = useQuery<RejectionCategory[]>({
    queryKey: ["rejectionCategories"],
    queryFn: fetchRejectionCategories,
  });

  return {
    rejectionCategories: data,
    isLoading,
    error,
  };
};

export const useForwardedIncidents = (barangayId: number, params: IncidentQueryParams) => {
  const { data, isLoading, isFetching, error } = useQuery<PaginatedResponse<Incident>>({
    queryKey: ["forwardedIncidents", barangayId, params.page, params.page_size, params.search, params.complaint_status, params.category_name, params.severity_level, params.date_from, params.date_to],
    queryFn: () => getForwardedIncidents(barangayId, params),
    placeholderData: keepPreviousData,
    enabled: !!barangayId,
  });

  return {
    incidents: data?.data ?? [],
    pagination: data?.pagination,
    isLoading,
    isFetching,
    error,
  };
};

export const useAllForwardedIncidents = (params: IncidentQueryParams) => {
  const { data, isLoading, isFetching, error } = useQuery<PaginatedResponse<Incident>>({
    queryKey: ["allForwardedIncidents", params.page, params.page_size, params.search, params.complaint_status, params.category_name, params.severity_level, params.date_from, params.date_to],
    queryFn: () => getAllForwardedIncidents(params),
    placeholderData: keepPreviousData,
  });

  return {
    incidents: data?.data ?? [],
    pagination: data?.pagination,
    isLoading,
    isFetching,
    error,
  };
};

export const useMarkIncidentAsViewed = () => {
  const mutation = useMutation({
    mutationFn: (incidentId: number) => markIncidentAsViewed(incidentId),
    onSuccess: invalidateIncidentQueries,
  });
  return mutation;
};

export const useNotifyHearing = () => {
  const mutation = useMutation({
    mutationFn: ({ incidentId, hearingDate }: { incidentId: number; hearingDate: FormData }) => notifyHearing(incidentId, hearingDate),
    onSuccess: invalidateIncidentQueries,
  });
  return mutation;
};

export const useMarkHearingSuccess = (incidentId: number) => {
  const mutation = useMutation({
    mutationKey: ["markHearing", incidentId],
    mutationFn: (isSuccessful: boolean) => markHearingAsSuccessful(incidentId, isSuccessful),
    onSuccess: invalidateIncidentQueries,
  });
  return mutation;
};

export const useRescheduleHearing = (incidentId: number) => {
  const mutation = useMutation({
    mutationKey: ["rescheduleHearing", incidentId],
    mutationFn: (hearingFormData: FormData) => rescheduleHearing(incidentId, hearingFormData),
    onSuccess: invalidateIncidentQueries,
  });
  return mutation;
};

export const useScheduledHearings = (params: IncidentQueryParams) => {
  const { data, isLoading, isFetching, error } = useQuery<PaginatedResponse<Incident>>({
    queryKey: [
      "scheduledHearings",
      params.page,
      params.page_size,
      params.search,
      params.order,
      params.date_from,
      params.date_to,
    ],
    queryFn: () => getScheduledHearings(params),
    placeholderData: keepPreviousData,
  });

  return {
    incidents: data?.data ?? [],
    pagination: data?.pagination,
    isLoading,
    isFetching,
    error,
  };
};