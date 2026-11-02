import { useMemo, useState } from "react";
import { SearchInput } from "../../general";
import { IncidentsTable } from "../components/IncidentsTable";
import { ComplaintStatusFilterDropdown, CategoryFilterDropdown, StatusFilterDropdown, DateFilter } from "../components/Filters";
import { BARANGAY_INCIDENT_STATUS_FILTERS } from "../../../types/complaints/complaint";
import type { ComplaintStatusFilter, StatusFilter } from "../../../types/complaints/complaint";
import { CATEGORY } from "../../../types/general/category";
import type { IncidentQueryParams } from "../../../services/incidents/incidents";
import { useAssignedIncidents } from "../../../hooks/useIncidents";

const PAGE_SIZE = 8;

export const AssignedIncidentsPage: React.FC = () => {
  const [search, setSearch] = useState("");
  const [submittedSearch, setSubmittedSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState<ComplaintStatusFilter>("all");
  const [filterCategory, setFilterCategory] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [filterSeverity, setFilterSeverity] = useState<StatusFilter>("all");

  const queryParams: IncidentQueryParams = useMemo(() => {
    const params: IncidentQueryParams = { page: currentPage, page_size: PAGE_SIZE };
    if (submittedSearch) params.search = submittedSearch;
    if (filterStatus !== "all") params.complaint_status = filterStatus;
    if (filterCategory) params.category_name = filterCategory;
    if (filterSeverity !== "all") params.severity_level = filterSeverity;
    if (dateFrom) params.date_from = dateFrom;
    if (dateTo) params.date_to = dateTo;
    return params;
  }, [currentPage, submittedSearch, filterStatus, filterCategory, filterSeverity, dateFrom, dateTo]);

  const { incidents, pagination, isLoading, isFetching, error } = useAssignedIncidents(queryParams);

  const handleSearch = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setSearch(value);
    if (!value.trim()) setSubmittedSearch("");
  };

  if (error) {
    return (
      <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        Failed to load your assigned incidents. Please refresh.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Assigned Incidents</h1>
        <p className="mt-1 text-sm text-gray-600">Review the incidents currently assigned to you.</p>
      </div>

      <div>
        <SearchInput value={search} onChange={handleSearch} onSearch={() => setSubmittedSearch(search.trim())} />
      </div>

      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="grid w-full gap-3 sm:grid-cols-3 lg:w-auto">
          <div className="flex min-w-0 flex-col gap-1.5">
            <label className="text-sm font-medium text-gray-700">Status</label>
            <ComplaintStatusFilterDropdown current={filterStatus} options={BARANGAY_INCIDENT_STATUS_FILTERS} onChange={setFilterStatus} />
          </div>
          <div className="flex min-w-0 flex-col gap-1.5">
            <label className="text-sm font-medium text-gray-700">Category</label>
            <CategoryFilterDropdown current={filterCategory} categories={Object.keys(CATEGORY)} onChange={setFilterCategory} />
          </div>
          <div className="flex min-w-0 flex-col gap-1.5">
            <label className="text-sm font-medium text-gray-700">Severity</label>
            <StatusFilterDropdown current={filterSeverity} onChange={setFilterSeverity} />
          </div>
        </div>

        <div className="w-full lg:w-auto">
          <label className="mb-1.5 block text-sm font-medium text-gray-700">Date Range</label>
          <DateFilter
            dateFrom={dateFrom}
            dateTo={dateTo}
            onDateFromChange={(e) => setDateFrom(e.target.value)}
            onDateToChange={(e) => setDateTo(e.target.value)}
            onClear={() => {
              setDateFrom("");
              setDateTo("");
            }}
          />
        </div>
      </div>

      <IncidentsTable
        incidents={incidents}
        isLoading={isLoading}
        isFetching={isFetching}
        currentPage={pagination?.page ?? 1}
        totalPages={pagination?.total_pages ?? 1}
        onPageChange={setCurrentPage}
      />

      {!isLoading && pagination && (
        <p className="text-left text-xs text-gray-500 sm:text-right">
          Showing {incidents.length} of {pagination.total_items} assigned incidents
        </p>
      )}
    </div>
  );
};
