import { useQuery, useMutation, keepPreviousData } from "@tanstack/react-query";
import { addBarangayMember, getAllBarangays, getBarangayById, getBarangayMembers, getMyBarangayDuty, getOnDutyBarangayMembers, markBarangayIncidentsViewed, removeBarangayMember, updateMyBarangayDuty } from "../services/barangay/barangays";
import type { BarangayDutyUpdate, BarangayMember, BarangayMemberDuty, OnDutyBarangayMember } from "../services/barangay/barangays";
import type { BarangayAccountData } from "../types/barangay/barangayAccount";
import type { PaginatedResponse } from "../types/general/pagination";
import type { PaginationQueryParams } from "../types/general/pagination";
import { queryClient } from "../main";

export const useAllBarangays = (params: PaginationQueryParams) => {
  const { data, isLoading, isFetching, error } = useQuery<PaginatedResponse<BarangayAccountData>>({
    queryKey: ["barangays", params.page, params.page_size, params.search],
    queryFn: () => getAllBarangays(params),
    placeholderData: keepPreviousData,
    refetchOnMount: true,
    refetchOnWindowFocus: false,
  });

  return {
    barangays: data?.data ?? [],
    pagination: data?.pagination,
    isLoading,
    isFetching,
    error,
  };
};

export const useBarangayById = (barangayId: number) => {
  const { data, isLoading, error } = useQuery<BarangayAccountData>({
    queryKey: ["barangays", barangayId],
    queryFn: () => getBarangayById(barangayId),
    enabled: !!barangayId,
  });

  return {
    barangay: data,
    isLoading,
    error,
  };
};

export const useMarkBarangayViewed = () => {
  return useMutation({
    mutationFn: (barangayId: number) => markBarangayIncidentsViewed(barangayId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["barangays"] });
    },
  });
};

export const useBarangayMembers = (barangayId?: number, onDutyOnly = false) => {
  const { data, isLoading, error, refetch } = useQuery<BarangayMember[]>({
    queryKey: ["barangayMembers", barangayId, onDutyOnly],
    queryFn: () => getBarangayMembers(barangayId as number, onDutyOnly),
    enabled: !!barangayId,
    refetchInterval: onDutyOnly ? 60_000 : false,
  });

  return {
    members: data ?? [],
    isLoading,
    error,
    refetch,
  };
};

export const useOnDutyBarangayMembers = (barangayId?: number) => {
  const { data, isLoading, error, refetch } = useQuery<OnDutyBarangayMember[]>({
    queryKey: ["onDutyBarangayMembers", barangayId],
    queryFn: () => getOnDutyBarangayMembers(barangayId as number),
    enabled: !!barangayId,
    staleTime: 30_000,
    refetchInterval: 60_000,
    refetchOnWindowFocus: false,
  });

  return {
    members: data ?? [],
    isLoading,
    error,
    refetch,
  };
};

export const useMyBarangayDuty = (enabled = true) => {
  const { data, isLoading, error } = useQuery<BarangayMemberDuty>({
    queryKey: ["myBarangayDuty"],
    queryFn: getMyBarangayDuty,
    enabled,
    refetchOnMount: "always",
  });

  return { duty: data, isLoading, error };
};

export const useUpdateMyBarangayDuty = () => useMutation({
  mutationFn: (duty: BarangayDutyUpdate) => updateMyBarangayDuty(duty),
  onSuccess: (duty) => {
    queryClient.setQueryData(["myBarangayDuty"], duty);
    queryClient.invalidateQueries({ queryKey: ["onDutyBarangayMembers"] });
    queryClient.invalidateQueries({ queryKey: ["barangayMembers"] });
  },
});

export const useAddBarangayMember = (barangayId: number) => useMutation({
  mutationFn: (payload: { name: string; position: string; email: string; password: string }) => addBarangayMember(barangayId, payload),
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ["barangayMembers", barangayId] }),
});

export const useRemoveBarangayMember = (barangayId: number) => useMutation({
  mutationFn: (memberId: number) => removeBarangayMember(barangayId, memberId),
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ["barangayMembers", barangayId] }),
});
