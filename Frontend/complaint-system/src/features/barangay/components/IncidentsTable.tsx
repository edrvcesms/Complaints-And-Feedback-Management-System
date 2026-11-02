import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate } from "react-router-dom";
import type { Incident } from "../../../types/complaints/incident";
import { Pagination } from "./Pagination";
import { TableSkeleton } from "./Skeletons";
import { formatCategoryName } from "../../../utils/categoryFormatter";

interface IncidentTableRowProps {
  incident: Incident;
}

const getSeverityColor = (severity: string) => {
  switch (severity) {
    case "LOW":
      return "bg-green-100 text-green-800";
    case "MODERATE":
      return "bg-yellow-100 text-yellow-800";
    case "HIGH":
      return "bg-red-100 text-red-800";
    case "VERY_HIGH":
      return "bg-black-100 text-black-800";
    default:
      return "bg-gray-100 text-gray-800";
  }
};

const getStatusColor = (status: string) => {
  switch (status.toLowerCase()) {
    case "resolved":
    case "resolved_by_barangay":
      return "bg-green-100 text-green-800";
    case "under_review":
    case "reviewed_by_barangay":
      return "bg-yellow-100 text-yellow-800";
    case "submitted":
      return "bg-gray-100 text-gray-800";
    case "under_review_by_lgu":
      return "bg-yellow-100 text-yellow-800";
    case "forwarded_to_lgu":
      return "bg-blue-100 text-blue-800";
    case "rejected_by_lgu":
      return "bg-red-100 text-red-800";
    default:
      return "bg-gray-100 text-gray-800";
  }
};

const formatStatus = (status: string, t: (key: string) => string) => {
  if (!status) return t('common.na');
  const lowerStatus = status.toLowerCase();

  if (lowerStatus === 'forwarded_to_lgu') {
    return t('status.forwarded');
  }

  if (lowerStatus === 'resolved_by_barangay') {
    return t('status.resolved');
  }

  if (lowerStatus === 'reviewed_by_barangay') {
    return t('status.underReview');
  }

  if (lowerStatus === 'submitted') return t('status.submitted');
  if (lowerStatus === 'rejected') return t('status.rejected');
  return t('status.unknown');
};

export const IncidentTableRow: React.FC<IncidentTableRowProps> = ({
  incident,
}) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();

  const handleView = () => {
    const basePath = location.pathname.startsWith('/member') ? '/member' : '/dashboard';
    navigate(`${basePath}/incidents/${incident.id}`);
  };

  const hasNewComplaints = incident.has_new_complaints || (incident.new_complaint_count ?? 0) > 0;
  const newComplaintCount = Number(incident.new_complaint_count ?? 0);

  return (
    <tr className="hover:bg-gray-50 transition-colors">
      <td className="px-4 py-3 text-xs text-gray-500 font-mono text-center">#{incident.id}</td>

      <td className="px-4 py-3 text-sm text-gray-600 hidden md:table-cell text-center">
        {formatCategoryName(incident.category?.category_name)}
      </td>

      <td className="px-4 py-3 text-sm font-medium text-gray-900 text-center">
        <div className="truncate max-w-[11rem] sm:max-w-sm md:max-w-md mx-auto" title={incident.title}>{incident.title}</div>
      </td>

      <td className="px-4 py-3 text-center">
        <span
          className={`inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium ${getSeverityColor(incident.severity_level)}`}
        >
          {incident.severity_level === "LOW" ? t('incidents.severity.low') : incident.severity_level === "MODERATE" ? t('incidents.severity.moderate') : incident.severity_level === "HIGH" ? t('incidents.severity.high') : t('incidents.severity.veryHigh')}
        </span>
      </td>

      <td className="px-4 py-3 text-center">
        <span
          className={`inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium ${getStatusColor(incident.complaint_clusters[0]?.complaint?.status || "")}`}
        >
          {formatStatus(incident.complaint_clusters[0]?.complaint?.status || "", t)}
        </span>
      </td>

      <td className="px-4 py-3 text-sm text-gray-700 font-semibold hidden sm:table-cell text-center">
        {incident.complaint_count}
      </td>

      <td className="px-4 py-3 text-center">
        <button
          onClick={handleView}
          className="relative inline-flex min-h-9 items-center justify-center px-3 py-1 bg-primary-100 text-primary-800 rounded-md text-xs font-medium hover:bg-primary-200 transition-colors"
          title={hasNewComplaints && newComplaintCount > 0 ? `${newComplaintCount} ${t('incidents.newComplaint')}` : undefined}
        >
          {t('incidents.view')}
          {hasNewComplaints && (
            <span className="absolute -top-2 -right-2 flex min-w-5 h-5 items-center justify-center rounded-full bg-orange-500 px-1 text-[10px] font-bold leading-none text-white shadow-sm ring-2 ring-white">
              {newComplaintCount > 0 ? newComplaintCount : ''}
            </span>
          )}
        </button>
      </td>
    </tr>
  );
};

interface IncidentsTableProps {
  incidents: Incident[];
  isLoading: boolean;
  isFetching?: boolean;
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

export const IncidentsTable: React.FC<IncidentsTableProps> = ({
  incidents,
  isLoading,
  isFetching = false,
  currentPage,
  totalPages,
  onPageChange,
}) => {
  const { t } = useTranslation();

  const TABLE_HEADERS = [
    { label: t('incidents.columns.incidentId'), className: "text-center" },
    { label: t('incidents.columns.category'), className: "hidden md:table-cell text-center" },
    { label: t('incidents.columns.title'), className: "text-center" },
    { label: t('incidents.columns.severity'), className: "text-center" },
    { label: t('incidents.columns.status'), className: "text-center" },
    { label: t('incidents.columns.complaintCounts'), className: "hidden sm:table-cell text-center" },
    { label: t('incidents.columns.view'), className: "text-center" },
  ];

  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      <div className="px-3 pt-2 text-[11px] text-gray-500 sm:hidden">
        {t('incidents.swipeHint')}
      </div>
      <div className="overflow-x-auto -mx-2 sm:mx-0">
        <div className="inline-block min-w-full align-middle">
          <div className="overflow-hidden">
            <table className="w-full min-w-[680px]">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200 text-center">
                  {TABLE_HEADERS.map(({ label, className }) => (
                    <th
                      key={label}
                      className={`px-4 py-3 text-xs font-semibold text-gray-600 uppercase tracking-wide ${className}`}
                    >
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>

              <tbody className="divide-y divide-gray-100">
                {isLoading || isFetching ? (
                  <TableSkeleton columns={7} rows={5} />
                ) : incidents.length === 0 ? (
                  <tr>
                    <td
                      colSpan={7}
                      className="px-4 py-16 text-center text-sm text-gray-500"
                    >
                      {t('incidents.noResults')}
                    </td>
                  </tr>
                ) : (
                  incidents.map((incident) => (
                    <IncidentTableRow key={incident.id} incident={incident} />
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <Pagination
        currentPage={currentPage}
        totalPages={totalPages}
        onPageChange={onPageChange}
      />
    </div>
  );
};
