import { useTranslation } from 'react-i18next';
import { useParams, useNavigate } from "react-router-dom";
import { useIncidentDetails } from "../../../hooks/useIncidents";
import { ArrowLeft, AlertCircle, MapPin, Users, Play, X, Image as ImageIcon, FileText, Building2, Download, Save } from "lucide-react";
import { formatCategoryName } from "../../../utils/categoryFormatter";
import { formatDate, formatDateTime } from "../../../utils/dateUtils";
import LoadingIndicator from "../../general/LoadingIndicator";
import { useState, useEffect } from "react";
import { ActionsTakenModal } from "../../general/ActionsTakenModal";
import { useActionsTakenModal } from "../../../hooks/useActionsTakenModal";
import { useReviewIncident, useResolveIncident, useRejectIncident } from '../../../hooks/useIncidents';
import { useToast } from "../../../hooks/useToast";
import { ToastContainer } from "../../../components/Toast";
import { isAbortError } from "../../../utils/axiosException";
import { SuccessModal } from "../../general/SuccessModal";
import { ErrorModal } from "../../general/ErrorModal";
import { validateAttachments } from '../../../utils/attachmentHelper';
import { createCaseReferral, downloadReferralDocument, getActiveDepartments, getComplaintReferrals, type ActiveDepartment, type CaseReferralRecord } from "../../../services/lgu/referrals";
import { useAuthStore } from "../../../store/authStore";

const glassButtonBase = "inline-flex items-center justify-center gap-1.5 px-3 py-2 text-sm font-medium rounded-md border backdrop-blur-md shadow-lg transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 disabled:opacity-40 disabled:cursor-not-allowed";
const glassOutlineButton = `${glassButtonBase} bg-gray-50/70 text-gray-700 border-gray-400/70 hover:bg-gray-200/80`;
const glassYellowButton = `${glassButtonBase} bg-yellow-500/75 text-white border-yellow-400/70 hover:bg-yellow-700/80`;
const glassGreenButton = `${glassButtonBase} bg-green-600/80 text-white border-green-600/80 hover:bg-green-700/80`;
const glassBlueButton = `${glassButtonBase} bg-blue-600/80 text-white border-blue-600/80 hover:bg-blue-700/80`;
const glassDangerButton = `${glassButtonBase} bg-red-500/75 text-white border-red-400/70 hover:bg-red-700/80`;
const card = "bg-white border border-gray-200 rounded-xl shadow-sm p-5";

const getResponseAuthorName = (response: any, incident: any) => {
  if (response?.user) {
    const fullName = [response.user.first_name, response.user.last_name].filter(Boolean).join(' ').trim();
    if (fullName) return fullName;
  }

  if (response?.user?.role === 'lgu_official') return 'Local Government Unit';
  if (incident?.barangay?.barangay_name) return `Barangay ${incident.barangay.barangay_name}`;
  return 'Barangay Official';
};

const emptyReferralForm = {
  department_id: '',
  designated_officer: '',
  designated_officer_position: '',
  reason_for_referral: '',
  requested_action: '',
  receiving_officer: '',
  receiving_officer_position: '',
};

const ResponseMediaAction: React.FC<{ attachment: { file_url: string; media_type?: string }; onClick: () => void }> = ({ attachment, onClick }) => {
  const isVideo = attachment.media_type?.startsWith('video');
  const isDocument = attachment.media_type?.startsWith('application');

  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-700 bg-gray-50 border border-gray-200 rounded-md hover:bg-gray-100 transition-colors"
      aria-label={isVideo ? 'View video response attachment' : isDocument ? 'Open document response attachment' : 'View image response attachment'}
    >
      {isVideo ? <Play className="w-3.5 h-3.5" /> : isDocument ? <FileText className="w-3.5 h-3.5" /> : <ImageIcon className="w-3.5 h-3.5" />}
      {isDocument ? 'Open document' : 'View media'}
    </button>
  );
};

const ResponseMediaLightbox: React.FC<{ media: { url: string; type: string }; onClose: () => void }> = ({ media, onClose }) => {
  const isVideo = media.type?.startsWith('video');

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4" onClick={onClose}>
      <button
        type="button"
        onClick={onClose}
        className="absolute right-4 top-4 p-2 text-white/80 transition-colors hover:text-white"
        aria-label="Close"
      >
        <X className="h-6 w-6" />
      </button>

      <div className="flex max-h-[85vh] max-w-3xl items-center justify-center" onClick={(e) => e.stopPropagation()}>
        {isVideo ? (
          <video src={media.url} controls autoPlay className="max-h-[85vh] max-w-full rounded-lg" />
        ) : (
          <img src={media.url} alt="Response attachment" className="max-h-[85vh] max-w-full rounded-lg object-contain" />
        )}
      </div>
    </div>
  );
};

export const LguIncidentDetails: React.FC = () => {
  const actionsTakenModal = useActionsTakenModal();
  const { t } = useTranslation();
  const { incidentId } = useParams<{ incidentId: string }>();
  const navigate = useNavigate();

  const { incident, isLoading, error } = useIncidentDetails(Number(incidentId));
  const { toasts } = useToast();

  const reviewIncidentMutation = useReviewIncident(Number(incidentId));
  const resolveIncidentMutation = useResolveIncident(Number(incidentId));
  const rejectIncidentMutation = useRejectIncident(Number(incidentId));
  const [successModal, setSuccessModal] = useState<{ isOpen: boolean; title: string; message: string }>(
    { isOpen: false, title: '', message: '' }
  );
  const [errorModal, setErrorModal] = useState<{ isOpen: boolean; title: string; message: string }>(
    { isOpen: false, title: '', message: '' }
  );
  const [lightboxAttachment, setLightboxAttachment] = useState<{ url: string; type: string } | null>(null);
  const [isReferralModalOpen, setIsReferralModalOpen] = useState(false);
  const [referralForm, setReferralForm] = useState(emptyReferralForm);
  const [departments, setDepartments] = useState<ActiveDepartment[]>([]);
  const [referrals, setReferrals] = useState<CaseReferralRecord[]>([]);
  const [isReferralListLoading, setIsReferralListLoading] = useState(true);
  const [referralListError, setReferralListError] = useState<string | null>(null);
  const [referralReloadKey, setReferralReloadKey] = useState(0);
  const [isReferralLoading, setIsReferralLoading] = useState(false);
  const [isSavingReferral, setIsSavingReferral] = useState(false);
  const [referralError, setReferralError] = useState<string | null>(null);
  const [referralDownloadError, setReferralDownloadError] = useState<string | null>(null);

  const userRole = useAuthStore((state) => state.userRole);
  const referralComplaintId = incident?.complaint_clusters?.[0]?.complaint?.id ?? null;
  const canManageReferrals = ['lgu_official', 'superadmin', 'barangay_official'].includes(String(userRole ?? ''));

  useEffect(() => {
    if (!referralComplaintId) {
      setIsReferralListLoading(false);
      setReferrals([]);
      setReferralListError(null);
      return;
    }

    let isMounted = true;
    const loadReferrals = async () => {
      setIsReferralListLoading(true);
      setReferralListError(null);
      try {
        const referralData = await getComplaintReferrals(referralComplaintId);

        if (isMounted) {
          setReferrals(referralData);
        }
      } catch (loadError) {
        console.error('Failed to load referrals:', loadError);
        if (isMounted) {
          setReferralListError('Unable to check whether this case has already been referred. Please try again.');
        }
      } finally {
        if (isMounted) {
          setIsReferralListLoading(false);
        }
      }
    };

    loadReferrals();
    return () => { isMounted = false; };
  }, [referralComplaintId, referralReloadKey]);

  useEffect(() => {
    if (!isReferralModalOpen || !referralComplaintId) return;

    let isMounted = true;
    const loadDepartments = async () => {
      setIsReferralLoading(true);
      setReferralError(null);
      try {
        const departmentData = await getActiveDepartments();
        if (isMounted) {
          setDepartments(departmentData);
        }
      } catch (loadError) {
        console.error('Failed to load departments:', loadError);
        if (isMounted) {
          setReferralError('Unable to load departments. Please try again.');
        }
      } finally {
        if (isMounted) {
          setIsReferralLoading(false);
        }
      }
    };

    loadDepartments();
    return () => { isMounted = false; };
  }, [isReferralModalOpen, referralComplaintId]);

  useEffect(() => {
    if (resolveIncidentMutation.isSuccess) {
      actionsTakenModal.closeModal();
      setErrorModal({ isOpen: false, title: '', message: '' });
      setSuccessModal({
        isOpen: true,
        title: 'Success!',
        message: 'The incident has been resolved successfully.',
      });
    }
  }, [resolveIncidentMutation.isSuccess]);

  useEffect(() => {
    if (reviewIncidentMutation.isSuccess) {
      actionsTakenModal.closeModal();
      setErrorModal({ isOpen: false, title: '', message: '' });
      setSuccessModal({
        isOpen: true,
        title: 'Success!',
        message: 'The incident has been marked for review successfully.',
      });
    }
  }, [reviewIncidentMutation.isSuccess]);

  useEffect(() => {
    if (rejectIncidentMutation.isSuccess) {
      actionsTakenModal.closeModal();
      setErrorModal({ isOpen: false, title: '', message: '' });
      setSuccessModal({
        isOpen: true,
        title: 'Success!',
        message: 'The incident has been rejected successfully.',
      });
    }
  }, [rejectIncidentMutation.isSuccess]);

  useEffect(() => {
    if (resolveIncidentMutation.isError) {
      actionsTakenModal.closeModal();
      setSuccessModal({ isOpen: false, title: '', message: '' });
      const error = resolveIncidentMutation.error as any;
      const errorMessage = error?.response?.data?.detail || 'Failed to resolve incident. Please try again.';
      setErrorModal({
        isOpen: true,
        title: 'Error',
        message: errorMessage,
      });
    }
  }, [resolveIncidentMutation.isError]);

  useEffect(() => {
    if (reviewIncidentMutation.isError) {
      actionsTakenModal.closeModal();
      const error = reviewIncidentMutation.error as any;
      if (isAbortError(error)) {
        return;
      }
      setSuccessModal({ isOpen: false, title: '', message: '' });
      const errorMessage = error?.response?.data?.detail || 'Failed to mark incident for review. Please try again.';
      setErrorModal({
        isOpen: true,
        title: 'Error',
        message: errorMessage,
      });
    }
  }, [reviewIncidentMutation.error, reviewIncidentMutation.isError]);

  useEffect(() => {
    if (rejectIncidentMutation.isError) {
      actionsTakenModal.closeModal();
      setSuccessModal({ isOpen: false, title: '', message: '' });
      const error = rejectIncidentMutation.error as any;
      const errorMessage = error?.response?.data?.detail || 'Failed to reject incident. Please try again.';
      setErrorModal({
        isOpen: true,
        title: 'Error',
        message: errorMessage,
      });
    }
  }, [rejectIncidentMutation.isError]);


  const handleViewAllComplaints = () => {
    navigate(`/lgu/incidents/${incidentId}/complaints`);
  };

  // Add actions taken modal logic for resolve/review
  const handleResolve = () => {
    actionsTakenModal.openModal({
      title: "Resolve Incident",
      description: "Please describe the actions taken to resolve this incident. This will be recorded and visible to complainants.",
      confirmText: "Resolve",
      confirmColor: "green",
      onConfirm: async (actionsTaken: string, attachments: File[]) => {
        try {
          const validationError = validateAttachments(attachments);
          if (validationError) {
            return;
          }
          actionsTakenModal.setIsLoading(true);
          await resolveIncidentMutation.mutateAsync({ actions_taken: actionsTaken, attachments });
        } catch (err) {
          console.error(err);
        } finally {
          actionsTakenModal.setIsLoading(false);
        }
      },
    });
  };

  const handleReview = () => {
    const abortController = new AbortController();
    actionsTakenModal.openModal({
      title: "Mark for Review",
      description: "Please describe the actions taken or the reason this incident is being flagged for further review.",
      confirmText: "Confirm",
      confirmColor: "yellow",
      onConfirm: async (actionsTaken: string, attachments: File[]) => {
        try {
          const validationError = validateAttachments(attachments);
          if (validationError) {
            return;
          }
          actionsTakenModal.setIsLoading(true);
          await reviewIncidentMutation.mutateAsync({
            actions_taken: actionsTaken,
            attachments,
            signal: abortController.signal,
          });
        } catch (err) {
          if (!isAbortError(err)) {
            console.error(err);
          }
        } finally { actionsTakenModal.setIsLoading(false); }
      },
      onCancel: () => {
        abortController.abort();
        reviewIncidentMutation.reset();
      },
    });
  };

  const handleReject = () => {
    actionsTakenModal.openModal({
      title: "Reject Incident",
      description: "Please provide the reason for rejecting this incident. This will be recorded and visible to complainants.",
      confirmText: "Reject",
      confirmColor: "red",
      onConfirm: async (actionsTaken: string, attachments: File[]) => {
        const validationError = validateAttachments(attachments);
        if (validationError) {
          return;
        }

        try {
          actionsTakenModal.setIsLoading(true);
          await rejectIncidentMutation.mutateAsync({ actions_taken: actionsTaken, attachments });
        } catch (err) {
          console.error(err);
        } finally {
          actionsTakenModal.setIsLoading(false);
        }
      },
    });
  };

  const handleReferralChange = (field: keyof typeof referralForm, value: string) => {
    setReferralForm((prev) => ({ ...prev, [field]: value }));
  };

  const handleSaveReferral = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!referralComplaintId) {
      setReferralError('No complaint record is available for this incident.');
      return;
    }

    if (!referralForm.department_id) {
      setReferralError('Please select a department to refer the case to.');
      return;
    }

    setIsSavingReferral(true);
    setReferralError(null);

    try {
      const payload = {
        complaint_id: referralComplaintId,
        department_id: Number(referralForm.department_id),
        designated_officer: referralForm.designated_officer.trim() || null,
        designated_officer_position: referralForm.designated_officer_position.trim() || null,
        reason_for_referral: referralForm.reason_for_referral.trim() || null,
        requested_action: referralForm.requested_action.trim() || null,
        receiving_officer: referralForm.receiving_officer.trim() || null,
        receiving_officer_position: referralForm.receiving_officer_position.trim() || null,
      };

      const createdReferral = await createCaseReferral(referralComplaintId, payload);
      setReferrals((prev) => [createdReferral, ...prev]);
      setReferralListError(null);
      setReferralForm(emptyReferralForm);
      setIsReferralModalOpen(false);
    } catch (error: any) {
      console.error('Failed to save referral:', error);
      setReferralError(error?.response?.data?.detail || 'Unable to save referral. Please try again.');
    } finally {
      setIsSavingReferral(false);
    }
  };

  const handleDownloadReferral = async (referralId: number) => {
    setReferralDownloadError(null);
    try {
      const documentBlob = await downloadReferralDocument(referralId);
      const downloadUrl = window.URL.createObjectURL(documentBlob);
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = `referral-${referralId}.docx`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(downloadUrl);
    } catch (error: any) {
      console.error('Failed to download referral:', error);
      setReferralDownloadError(error?.response?.data?.detail || 'Unable to download referral letter. Please try again.');
    }
  };

  if (isLoading) {
    return (
      <LoadingIndicator />
    );
  }

  if (error || !incident) {
    return (
      <div className="p-4 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">
        <AlertCircle className="inline mr-2" size={18} />
        Failed to load incident details. Please try again.
      </div>
    );
  }
  
  const incidentStatus = incident.complaint_clusters[0]?.complaint?.status ?? "submitted";
  const isSubmitted = incidentStatus === "submitted";
  const isUnderReviewByBarangay = incidentStatus === "reviewed_by_barangay";
  const isUnderReviewByLgu = incidentStatus === "reviewed_by_lgu";
  const isResolved = incidentStatus === "resolved_by_barangay" || incidentStatus === "resolved_by_lgu";
  const isRejectedByLgu = incident.complaint_clusters[0]?.complaint?.is_rejected_by_lgu === true;
  const isRejected = incidentStatus === "rejected" || incidentStatus === "rejected_by_lgu" || isRejectedByLgu;
  const isForwardedToLgu = incidentStatus === "forwarded_to_lgu";
  const shouldShowActions = !isResolved && !isRejected && ( isUnderReviewByLgu || isForwardedToLgu);
  const titleStatusBadge = isResolved
    ? { label: 'Resolved', className: 'bg-green-50 text-green-700 border-green-200', dotClassName: 'bg-green-600' }
    : isRejected || isRejectedByLgu
      ? { label: 'Rejected', className: 'bg-red-50 text-red-700 border-red-200', dotClassName: 'bg-red-600' }
      : isUnderReviewByBarangay || isUnderReviewByLgu
        ? { label: 'Under Review', className: 'bg-yellow-50 text-yellow-700 border-yellow-200', dotClassName: 'bg-yellow-600' }
        : isForwardedToLgu
          ? { label: 'Forwarded', className: 'bg-blue-50 text-blue-700 border-blue-200', dotClassName: 'bg-blue-600' }
          : null;

  const responses = incident.responses ?? [];
  const sortedResponses = [...responses].sort((a, b) => {
    const aTime = new Date(a.response_date).getTime();
    const bTime = new Date(b.response_date).getTime();
    return bTime - aTime;
  });

  const hasLocation =
    typeof incident.latitude === 'number' &&
    typeof incident.longitude === 'number' &&
    !Number.isNaN(incident.latitude) &&
    !Number.isNaN(incident.longitude);
  const severityLabel = String(incident.severity_level ?? '').replace(/_/g, ' ');


  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <button onClick={() => navigate("/lgu/incidents")} className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-900 transition-colors cursor-pointer">
          <ArrowLeft size={16} />
          {t('incidents.details.backToIncidents')}
        </button>
        <span className="text-sm text-slate-500">Incident #{incident.id}</span>
      </div>

      <div className={`${card} flex flex-wrap items-start justify-between gap-3`}>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-semibold text-gray-900 wrap-break-word">{incident.title}</h1>
            {titleStatusBadge && <div className={`inline-flex items-center gap-2 px-2.5 py-1 rounded-full border text-sm font-medium ${titleStatusBadge.className}`}><span className={`w-1.5 h-1.5 rounded-full ${titleStatusBadge.dotClassName}`} />{titleStatusBadge.label}</div>}
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-primary-50 text-sm font-medium text-primary-700 border border-primary-100"><AlertCircle size={14} />{formatCategoryName(incident.category?.category_name)}</span>
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-orange-50 text-sm font-medium text-orange-700 border border-orange-100 capitalize"><AlertCircle size={14} />severity: {severityLabel}</span>
          </div>
        </div>
        {hasLocation &&         <button onClick={() => navigate(`/lgu/incidents/${incident.id}/tracking`)} className={glassGreenButton}><MapPin size={15} />Start live tracking</button>}
      </div>

      <dl className={`${card} grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-4`}>
        <div className="flex items-center gap-3"><div className="w-10 h-10 rounded-lg bg-purple-50 text-purple-600 flex items-center justify-center shrink-0"><MapPin size={20} /></div><div className="min-w-0"><dt className="text-sm font-medium text-slate-500">Barangay</dt><dd className="mt-0.5 text-base font-semibold text-slate-900">{incident.barangay?.barangay_name || "N/A"}</dd></div></div>
        <div className="flex items-center gap-3"><div className="w-10 h-10 rounded-lg bg-primary-50 text-primary-700 flex items-center justify-center shrink-0"><Users size={20} /></div><div className="min-w-0"><dt className="text-sm font-medium text-slate-500">{t('incidents.details.totalComplaints')}</dt><dd className="mt-0.5 text-base font-semibold text-primary-700">{incident.complaint_count}</dd></div></div>
        <div className="flex items-center gap-3"><div className="w-10 h-10 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center shrink-0"><AlertCircle size={20} /></div><div className="min-w-0"><dt className="text-sm font-medium text-slate-500">{t('incidents.details.firstReported')}</dt><dd className="mt-0.5 text-base font-semibold text-slate-900">{formatDate(incident.first_reported_at, { year: 'numeric', month: 'numeric', day: 'numeric' })}</dd></div></div>
        <div className="flex items-center gap-3"><div className="w-10 h-10 rounded-lg bg-orange-50 text-orange-600 flex items-center justify-center shrink-0"><AlertCircle size={20} /></div><div className="min-w-0"><dt className="text-sm font-medium text-slate-500">{t('incidents.details.lastReported')}</dt><dd className="mt-0.5 text-base font-semibold text-slate-900">{formatDate(incident.last_reported_at, { year: 'numeric', month: 'numeric', day: 'numeric' })}</dd></div></div>
      </dl>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-8">
        <section className={`${card} lg:col-span-3`}><h2 className="text-base font-semibold text-primary-700 mb-2">{t('incidents.details.description')}</h2><p className="text-base text-slate-800 leading-relaxed whitespace-pre-wrap">{incident.description}</p><div className="mt-6 pt-4 border-t border-gray-400 flex items-center justify-between gap-3"><div className="min-w-0"><h3 className="text-base font-semibold text-primary-700">{t('incidents.details.relatedComplaints')} ({incident.complaint_count})</h3><p className="text-sm text-slate-600">View all complaints associated with this incident.</p></div><button onClick={handleViewAllComplaints} className={glassOutlineButton}><Users size={15} />{t('incidents.details.viewAllComplaints')}</button></div></section>
        <section className={`${card} lg:col-span-2`}><h2 className="text-base font-semibold text-primary-700 mb-2">{t('incidents.details.remarks')}</h2>{sortedResponses.length === 0 ? <p className="text-base text-slate-500">No responses yet.</p> : <div className={`${sortedResponses.length > 2 ? 'max-h-80 overflow-y-auto' : ''} space-y-3 pr-1`}>{sortedResponses.map((response) => { const attachments = response.response_attachments ?? []; const assignedMembers = response.barangay_members ?? []; return <div key={response.id} className="rounded-lg border border-gray-200 bg-slate-50 p-4 shadow-sm"><p className="text-base text-slate-800 whitespace-pre-wrap leading-6">{response.actions_taken}</p>{attachments.length > 0 && <div className="mt-2 flex flex-wrap gap-2">{attachments.map((attachment: any, idx: number) => <ResponseMediaAction key={attachment.id ?? idx} attachment={attachment} onClick={() => { if (attachment.media_type?.startsWith('application')) { window.open(attachment.file_url, '_blank', 'noopener,noreferrer'); return; } setLightboxAttachment({ url: attachment.file_url, type: attachment.media_type ?? 'image' }); }} />)}</div>}{assignedMembers.length > 0 && <p className="mt-2 text-sm text-slate-600">Assigned to: {assignedMembers.map((member: any) => `${member.name} (${member.position})`).join(", ")}</p>}<div className="mt-2 flex items-center justify-between gap-3"><p className="text-sm font-medium text-slate-600">{getResponseAuthorName(response, incident)}</p><p className="text-xs text-slate-400">{formatDateTime(response.response_date, { year: 'numeric', month: 'numeric', day: 'numeric' })}</p></div></div>; })}</div>}</section>
      </div>

      {shouldShowActions && (
        <div className={`${card} flex flex-wrap items-center justify-end gap-2`}>
          {canManageReferrals && referrals.length === 0 && (
            <button type="button" onClick={() => setIsReferralModalOpen(true)} disabled={isReferralListLoading || Boolean(referralListError)} className={glassBlueButton}>
              <Building2 size={15} />Refer Case
            </button>
          )}
          <button onClick={handleReview} disabled={reviewIncidentMutation.isPending || isSubmitted || isUnderReviewByLgu || isResolved || isUnderReviewByBarangay} className={glassYellowButton}>{reviewIncidentMutation.isPending ? "Reviewing..." : "Mark for review"}</button>
          <button onClick={handleReject} disabled={rejectIncidentMutation.isPending || isSubmitted || isResolved || isUnderReviewByBarangay} className={glassDangerButton}>{rejectIncidentMutation.isPending ? "Rejecting..." : "Reject"}</button>
          <button onClick={handleResolve} disabled={resolveIncidentMutation.isPending || isSubmitted || isResolved || isUnderReviewByBarangay} className={glassGreenButton}>{resolveIncidentMutation.isPending ? "Resolving..." : "Resolve"}</button>
        </div>
      )}

      {canManageReferrals && referralListError && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700" role="alert">
          <span>{referralListError}</span>
          <button type="button" onClick={() => setReferralReloadKey((key) => key + 1)} disabled={isReferralListLoading} className="font-semibold underline disabled:opacity-50">
            {isReferralListLoading ? 'Checking...' : 'Try again'}
          </button>
        </div>
      )}

      {canManageReferrals && referrals.length > 0 && (
        <section className={`${card} flex flex-wrap items-center justify-between gap-4 border-blue-200 bg-blue-50/60`}>
          <div className="flex min-w-0 items-start gap-3">
            <Building2 size={20} className="mt-0.5 shrink-0 text-blue-700" />
            <div>
              <h2 className="font-semibold text-blue-900">This case has already been referred.</h2>
              <p className="mt-1 text-sm text-blue-800">
                Download the referral document{referrals.length > 1 ? 's' : ''} below.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {referrals.map((referral) => (
              <button key={referral.id} type="button" onClick={() => handleDownloadReferral(referral.id)} className={glassBlueButton}>
                <Download size={15} />
                Download {referral.department?.abbreviation || referral.department?.name || 'Referral'}
              </button>
            ))}
          </div>
          {referralDownloadError && (
            <p className="w-full text-sm text-red-700" role="alert">{referralDownloadError}</p>
          )}
        </section>
      )}

      {isReferralModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm">
          <div className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-2xl bg-white shadow-2xl border border-gray-200">
            <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
              <div>
                <h3 className="text-xl font-semibold text-gray-900">Referral Workflow</h3>
                <p className="text-sm text-gray-500">Refer this complaint to an active department.</p>
              </div>
              <button type="button" onClick={() => { setIsReferralModalOpen(false); setReferralError(null); }} className="rounded-md p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-700" aria-label="Close referral workflow">
                <X size={18} />
              </button>
            </div>

            <div className="px-6 py-5">
              {isReferralLoading ? (
                <div className="flex min-h-[200px] items-center justify-center text-sm text-gray-500">Loading referral data...</div>
              ) : (
                <form onSubmit={handleSaveReferral} className="space-y-5">
                  {referralError && <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{referralError}</div>}

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="md:col-span-2">
                      <label className="mb-1 block text-sm font-medium text-gray-700">Department</label>
                      <select
                        value={referralForm.department_id}
                        onChange={(event) => handleReferralChange('department_id', event.target.value)}
                        className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-200"
                        required
                      >
                        <option value="">Select department</option>
                        {departments.map((department) => (
                          <option key={department.id} value={department.id}>{department.name}</option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label className="mb-1 block text-sm font-medium text-gray-700">Designated Officer</label>
                      <input value={referralForm.designated_officer} onChange={(event) => handleReferralChange('designated_officer', event.target.value)} className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm" placeholder="e.g. Maria Santos" />
                    </div>

                    <div>
                      <label className="mb-1 block text-sm font-medium text-gray-700">Officer Position</label>
                      <input value={referralForm.designated_officer_position} onChange={(event) => handleReferralChange('designated_officer_position', event.target.value)} className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm" placeholder="e.g. Social Welfare Officer" />
                    </div>

                    <div>
                      <label className="mb-1 block text-sm font-medium text-gray-700">Receiving Officer</label>
                      <input value={referralForm.receiving_officer} onChange={(event) => handleReferralChange('receiving_officer', event.target.value)} className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm" placeholder="Receiving officer" />
                    </div>

                    <div>
                      <label className="mb-1 block text-sm font-medium text-gray-700">Receiving Officer Position</label>
                      <input value={referralForm.receiving_officer_position} onChange={(event) => handleReferralChange('receiving_officer_position', event.target.value)} className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm" placeholder="Position" />
                    </div>

                    <div className="md:col-span-2">
                      <label className="mb-1 block text-sm font-medium text-gray-700">Reason for Referral</label>
                      <textarea value={referralForm.reason_for_referral} onChange={(event) => handleReferralChange('reason_for_referral', event.target.value)} className="min-h-[90px] w-full rounded-md border border-gray-300 px-3 py-2 text-sm" placeholder="State the reason for the referral" required />
                    </div>

                    <div className="md:col-span-2">
                      <label className="mb-1 block text-sm font-medium text-gray-700">Requested Action</label>
                      <textarea value={referralForm.requested_action} onChange={(event) => handleReferralChange('requested_action', event.target.value)} className="min-h-[90px] w-full rounded-md border border-gray-300 px-3 py-2 text-sm" placeholder="Describe the requested action" required />
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center justify-between gap-3 border-t border-gray-200 pt-4">
                    <div className="flex items-center gap-2">
                      <button type="button" onClick={() => { setIsReferralModalOpen(false); setReferralError(null); }} className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">Cancel</button>
                      <button type="submit" disabled={isSavingReferral} className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60">
                        <Save size={15} />{isSavingReferral ? 'Saving...' : 'Save Referral'}
                      </button>
                    </div>
                  </div>
                </form>
              )}
            </div>
          </div>
        </div>
      )}

      {lightboxAttachment && (
        <ResponseMediaLightbox
          media={lightboxAttachment}
          onClose={() => setLightboxAttachment(null)}
        />
      )}

      <ActionsTakenModal
        isOpen={actionsTakenModal.isOpen}
        title={actionsTakenModal.title}
        description={actionsTakenModal.description}
        confirmText={actionsTakenModal.confirmText}
        confirmColor={actionsTakenModal.confirmColor as any}
        onConfirm={actionsTakenModal.onConfirm}
        onCancel={actionsTakenModal.cancelModal}
        isLoading={actionsTakenModal.isLoading}
      />

      <ToastContainer toasts={toasts} />

      <SuccessModal
        isOpen={successModal.isOpen}
        title={successModal.title}
        message={successModal.message}
        onClose={() => {
          navigate("/lgu/incidents");
          setSuccessModal({ isOpen: false, title: '', message: '' });
        }}
      />

      <ErrorModal
        isOpen={errorModal.isOpen}
        title={errorModal.title}
        message={errorModal.message}
        onClose={() => setErrorModal({ isOpen: false, title: '', message: '' })}
      />
    </div>
  );
};