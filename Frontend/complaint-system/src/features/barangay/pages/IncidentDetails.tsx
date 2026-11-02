import { useTranslation } from 'react-i18next';
import { useState, useEffect } from 'react';
import { useParams, useNavigate } from "react-router-dom";
import { format } from "date-fns";
import { useIncidentDetails, useRejectionCategories, useMarkIncidentUnresolvable } from "../../../hooks/useIncidents";
import { ArrowLeft, AlertCircle, MapPin, Users, UserRound, Clock, CalendarIcon, Play, X, Image as ImageIcon, FileText } from "lucide-react";
import { formatCategoryName } from "../../../utils/categoryFormatter";
import { formatDate, formatDateTime } from "../../../utils/dateUtils";
import LoadingIndicator from "../../general/LoadingIndicator";
import { useResolveIncident, useReviewIncident, useForwardIncidentToLgu, useNotifyHearing, useRejectIncident, useRescheduleHearing, useMarkHearingSuccess } from '../../../hooks/useIncidents';
import { ActionsTakenModal } from "../../general/ActionsTakenModal";
import { useActionsTakenModal } from "../../../hooks/useActionsTakenModal";
import { ConfirmationModal } from "../../general/ConfirmationModal";
import { useConfirmationModal } from "../../../hooks/useConfirmationModal";
import { SuccessModal } from "../../general/SuccessModal";
import { ErrorModal } from "../../general/ErrorModal";
import { isAbortError } from "../../../utils/axiosException";
import { CustomDateTimePicker } from '../../general/CustomDateTimePicker';
import type { ComplaintStatus } from '../../../types/complaints/complaint';
import { validateAttachments } from '../../../utils/attachmentHelper';
import { RejectIncidentModal } from "../components/RejectIncidentModal";
import { startOfTomorrow } from "date-fns";
import { useBarangayMembers } from "../../../hooks/useBarangays";
import { useUserRole } from "../../../hooks/useUserRole";

const btnBase =
  "inline-flex items-center justify-center gap-1.5 px-3 py-2 text-sm font-medium rounded-md border transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 disabled:opacity-40 disabled:cursor-not-allowed";
const btnOutline = `${btnBase} bg-gray-50 text-gray-700 border-gray-400 hover:bg-gray-200`;
const btnYellow = `${btnBase} bg-yellow-500 text-white border-yellow-400 hover:bg-yellow-700`;
const btnBlue = `${btnBase} bg-blue-500 text-white border-blue-400 hover:bg-blue-700`;
const btnGreen = `${btnBase} bg-green-500 text-white border-green-400 hover:bg-green-700`;
const btnDanger = `${btnBase} bg-red-500 text-white border-red-400 hover:bg-red-700`;
const btnSolid = `${btnBase} bg-green-600 text-white border-green-600 hover:bg-green-700`;

// Shared card style used by each section
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

const getHearingDateLabel = (count: number) => {
  if (count <= 0) {
    return 'Hearing Date';
  }

  if (count === 1) {
    return 'First Hearing Date';
  }

  if (count === 2) {
    return 'Second Hearing Date';
  }

  return 'Last Hearing Date';
};

export const IncidentDetails: React.FC = () => {
  const { t } = useTranslation();
  const { incidentId } = useParams<{ incidentId: string }>();
  const navigate = useNavigate();

  const { incident, isLoading, error } = useIncidentDetails(Number(incidentId));
  const { isBarangayMember } = useUserRole();
  const { members: barangayMembers } = useBarangayMembers(isBarangayMember ? undefined : incident?.barangay?.id, true);

  const resolveIncidentMutation = useResolveIncident(Number(incidentId));
  const unresolvableMutation = useMarkIncidentUnresolvable(Number(incidentId));
  const reviewIncidentMutation = useReviewIncident(Number(incidentId));
  const forwardToLguMutation = useForwardIncidentToLgu(Number(incidentId));
  const rejectIncidentMutation = useRejectIncident(Number(incidentId));
  const { rejectionCategories, isLoading: isLoadingRejectionCategories, error: rejectionCategoriesError } = useRejectionCategories();
  const notifyHearingMutation = useNotifyHearing();
  const rescheduleHearingMutation = useRescheduleHearing(Number(incidentId));
  const markHearingMutation = useMarkHearingSuccess(Number(incidentId));
  const [hearingDate, setHearingDate] = useState('');
  const [hearingActionMode, setHearingActionMode] = useState<'notify' | 'reschedule'>('notify');
  const [isHearingModalOpen, setIsHearingModalOpen] = useState(false);
  const [additionalRespondents, setAdditionalRespondents] = useState<Array<{ name: string; email: string }>>([]);
  const isHearingMutationPending = notifyHearingMutation.isPending || rescheduleHearingMutation.isPending;
  const [isRejectModalOpen, setIsRejectModalOpen] = useState(false);
  const [attachmentError, setAttachmentError] = useState('');

  const confirmationModal = useConfirmationModal();
  const actionsTakenModal = useActionsTakenModal();
  const [successModal, setSuccessModal] = useState<{ isOpen: boolean; title: string; message: string; shouldNavigateOnClose?: boolean }>({
    isOpen: false,
    title: '',
    message: '',
  });

  const [errorModal, setErrorModal] = useState<{ isOpen: boolean; title: string; message: string }>({
    isOpen: false,
    title: '',
    message: '',
  });
  const [lightboxAttachment, setLightboxAttachment] = useState<{ url: string; type: string } | null>(null);

  useEffect(() => {
    if (!actionsTakenModal.isOpen) {
      setAttachmentError('');
    }
  }, [actionsTakenModal.isOpen]);

  useEffect(() => {
    if (!isRejectModalOpen) {
      setAttachmentError('');
    }
  }, [isRejectModalOpen]);

  // Handle successful resolve
  useEffect(() => {
    if (resolveIncidentMutation.isSuccess) {
      confirmationModal.closeModal();
      actionsTakenModal.closeModal();
      setErrorModal({ isOpen: false, title: '', message: '' });
      setSuccessModal({
        isOpen: true,
        title: 'Success!',
        message: 'The incident has been resolved successfully.',
      });
    }
  }, [resolveIncidentMutation.isSuccess]);

  // Handle successful review
  useEffect(() => {
    if (reviewIncidentMutation.isSuccess) {
      confirmationModal.closeModal();
      actionsTakenModal.closeModal();
      setErrorModal({ isOpen: false, title: '', message: '' });
      setSuccessModal({
        isOpen: true,
        title: 'Success!',
        message: 'The incident has been marked for review successfully.',
      });
    }
  }, [reviewIncidentMutation.isSuccess]);

  // Handle successful forward to LGU
  useEffect(() => {
    if (forwardToLguMutation.isSuccess) {
      confirmationModal.closeModal();
      actionsTakenModal.closeModal();
      setErrorModal({ isOpen: false, title: '', message: '' });
      setSuccessModal({
        isOpen: true,
        title: 'Success!',
        message: 'The incident has been endorsed to LGU successfully.',
      });
    }
  }, [forwardToLguMutation.isSuccess]);

  // Handle successful reject
  useEffect(() => {
    if (rejectIncidentMutation.isSuccess) {
      setIsRejectModalOpen(false);
      setErrorModal({ isOpen: false, title: '', message: '' });
      setSuccessModal({
        isOpen: true,
        title: 'Success!',
        message: 'The incident has been rejected successfully.',
      });
      rejectIncidentMutation.reset();
    }
  }, [rejectIncidentMutation.isSuccess]);

  // Handle successful hearing notification
  useEffect(() => {
    if (notifyHearingMutation.isSuccess) {
      confirmationModal.closeModal();
      setIsHearingModalOpen(false);
      setHearingDate('');
      setErrorModal({ isOpen: false, title: '', message: '' });
      setSuccessModal({
        isOpen: true,
        title: 'Success!',
        message: 'Users have been notified for the hearing successfully.',
        shouldNavigateOnClose: false,
      });
    }
  }, [notifyHearingMutation.isSuccess]);

  // Handle resolve error
  useEffect(() => {
    if (resolveIncidentMutation.isError) {
      confirmationModal.closeModal();
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

  // Handle review error
  useEffect(() => {
    if (reviewIncidentMutation.isError) {
      confirmationModal.closeModal();
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

  // Handle forward to LGU error
  useEffect(() => {
    if (forwardToLguMutation.isError) {
      confirmationModal.closeModal();
      actionsTakenModal.closeModal();
      setSuccessModal({ isOpen: false, title: '', message: '' });
      const error = forwardToLguMutation.error as any;
      const errorMessage = error?.response?.data?.detail || 'Failed to endorse incident to LGU. Please try again.';
      setErrorModal({
        isOpen: true,
        title: 'Error',
        message: errorMessage,
      });
    }
  }, [forwardToLguMutation.isError]);

  // Handle reject error
  useEffect(() => {
    if (rejectIncidentMutation.isError) {
      setIsRejectModalOpen(false);
      setSuccessModal({ isOpen: false, title: '', message: '' });
      const error = rejectIncidentMutation.error as any;
      const errorMessage = error?.response?.data?.detail || 'Failed to reject incident. Please try again.';
      setErrorModal({
        isOpen: true,
        title: 'Error',
        message: errorMessage,
      });
      rejectIncidentMutation.reset();
    }
  }, [rejectIncidentMutation.isError]);

  // Handle hearing notification error
  useEffect(() => {
    if (notifyHearingMutation.isError) {
      confirmationModal.closeModal();
      setSuccessModal({ isOpen: false, title: '', message: '' });
      const error = notifyHearingMutation.error as any;
      const errorMessage = error?.response?.data?.detail || 'Failed to notify users for hearing. Please try again.';
      setErrorModal({
        isOpen: true,
        title: 'Error',
        message: errorMessage,
      });
    }
  }, [notifyHearingMutation.isError]);

  // Handle successful hearing reschedule
  useEffect(() => {
    if (rescheduleHearingMutation.isSuccess) {
      confirmationModal.closeModal();
      setIsHearingModalOpen(false);
      setHearingDate('');
      setErrorModal({ isOpen: false, title: '', message: '' });
      setSuccessModal({
        isOpen: true,
        title: 'Success!',
        message: 'Hearing has been rescheduled successfully.',
        shouldNavigateOnClose: false,
      });
    }
  }, [rescheduleHearingMutation.isSuccess]);

  // Handle hearing reschedule error
  useEffect(() => {
    if (rescheduleHearingMutation.isError) {
      confirmationModal.closeModal();
      setSuccessModal({ isOpen: false, title: '', message: '' });
      const error = rescheduleHearingMutation.error as any;
      const errorMessage = error?.response?.data?.detail || 'Failed to reschedule hearing. Please try again.';
      setErrorModal({
        isOpen: true,
        title: 'Error',
        message: errorMessage,
      });
    }
  }, [rescheduleHearingMutation.isError]);

  // Handle successful mark hearing
  useEffect(() => {
    if (markHearingMutation.isSuccess) {
      confirmationModal.closeModal();
      const isSuccessful = markHearingMutation.variables === true;
      if (isSuccessful) {
        navigate('/dashboard/incidents');
        return;
      }
      setSuccessModal({
        isOpen: true,
        title: 'Success!',
        message: isSuccessful
          ? 'Hearing marked successful. The incident has been resolved.'
          : 'Hearing marked unsuccessful. You can schedule a new hearing.',
        shouldNavigateOnClose: false,
      });
    }
  }, [markHearingMutation.isSuccess, markHearingMutation.variables, navigate]);

  // Handle mark hearing error
  useEffect(() => {
    if (markHearingMutation.isError) {
      confirmationModal.closeModal();
      const error = markHearingMutation.error as any;
      const errorMessage = error?.response?.data?.detail || 'Failed to update hearing status.';
      setErrorModal({ isOpen: true, title: 'Error', message: errorMessage });
    }
  }, [markHearingMutation.isError]);

  const handleViewAllComplaints = () => {
    navigate(`${isBarangayMember ? "/member" : "/dashboard"}/incidents/${incidentId}/complaints`);
  };

  const handleResolve = () => {
    actionsTakenModal.openModal({
      title: "Resolve Incident",
      description: "Please describe the actions taken to resolve this incident. This will be recorded and visible to complainants.",
      confirmText: "Resolve",
      confirmColor: "green",
      onConfirm: async (actionsTaken: string, attachments: File[], barangayMemberIds: number[]) => {
        const validationError = validateAttachments(attachments);
        if (validationError) {
          setAttachmentError(validationError);
          return;
        }

        actionsTakenModal.setIsLoading(true);
        try {
          await resolveIncidentMutation.mutateAsync({
            actions_taken: actionsTaken,
            attachments,
            ...(isBarangayMember ? {} : { barangay_member_ids: barangayMemberIds }),
          });
        } finally {
          actionsTakenModal.setIsLoading(false);
        }
      },
    });
  };

  const handleMarkUnresolvable = () => {
    confirmationModal.openModal({
      title: "Mark Incident Unresolvable?",
      message: "This will mark the assigned incident as not resolvable and return it to the Barangay Official for further action.",
      confirmText: "Mark Unresolvable",
      confirmColor: "red",
      onConfirm: async () => {
        try {
          await unresolvableMutation.mutateAsync();
          confirmationModal.closeModal();
          setSuccessModal({
            isOpen: true,
            title: "Incident Updated",
            message: "The incident has been marked as unresolvable.",
            shouldNavigateOnClose: false,
          });
        } catch (mutationError) {
          confirmationModal.closeModal();
          const apiError = mutationError as { response?: { data?: { detail?: string } } };
          setErrorModal({
            isOpen: true,
            title: "Unable to Update Incident",
            message: apiError.response?.data?.detail || "Failed to mark the incident as unresolvable. Please try again.",
          });
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
      onConfirm: async (actionsTaken: string, attachments: File[], barangayMemberIds: number[]) => {
        try {
          const validationError = validateAttachments(attachments);
          if (validationError) {
            setAttachmentError(validationError);
            return;
          }
          actionsTakenModal.setIsLoading(true);
          await reviewIncidentMutation.mutateAsync({
            actions_taken: actionsTaken,
            attachments,
            barangay_member_ids: barangayMemberIds,
            signal: abortController.signal,
          });
        } catch (err) {
          if (!isAbortError(err)) {
            console.error(err);
          }
        } finally {
          actionsTakenModal.setIsLoading(false);
        }
      },
      onCancel: () => {
        abortController.abort();
        reviewIncidentMutation.reset();
      },
    });
  };

  const handleForwardToLgu = () => {
    actionsTakenModal.openModal({
      title: "Escalate to LGU",
      description: "Please provide any relevant notes or instructions for the LGU when endorsing this incident.",
      confirmText: "Escalate",
      confirmColor: "blue",
      onConfirm: async (actionsTaken: string, attachments: File[]) => {
        actionsTakenModal.setIsLoading(true);
        try {
          const validationError = validateAttachments(attachments);
          if (validationError) {
            setAttachmentError(validationError);
            return;
          }
          await forwardToLguMutation.mutateAsync({ actions_taken: actionsTaken, attachments });
        } catch (err) {
          console.error(err);
          actionsTakenModal.setIsLoading(false);
        } finally {
          actionsTakenModal.setIsLoading(false); // ✅ always runs
        }
      }
    });
  };

  const handleReject = () => {
    setIsRejectModalOpen(true);
  };

  const handleMarkHearingOutcome = async (isSuccessful: boolean) => {
    confirmationModal.openModal({
      title: isSuccessful ? 'Mark Hearing Successful?' : 'Mark Hearing Unsuccessful?',
      message: isSuccessful
        ? 'This will resolve the incident and its related complaints. Continue?'
        : 'This will record the hearing as unsuccessful and allow a new hearing to be scheduled. Continue?',
      confirmText: isSuccessful ? 'Mark Successful' : 'Mark Unsuccessful',
      confirmColor: isSuccessful ? 'green' : 'red',
      onConfirm: async () => {
        await markHearingMutation.mutateAsync(isSuccessful);
      },
    });
  };

  const handleOpenHearingModal = (mode: 'notify' | 'reschedule' = 'notify') => {
    setHearingActionMode(mode);
    if (mode === 'reschedule' && incidentHearingDate) {
      const existingDate = new Date(incidentHearingDate);
      if (!Number.isNaN(existingDate.getTime())) {
        const localDateTime = new Date(existingDate.getTime() - existingDate.getTimezoneOffset() * 60000)
          .toISOString()
          .slice(0, 16);
        setHearingDate(localDateTime);
      }
    } else {
      setHearingDate('');
      setAdditionalRespondents([]);
    }
    setIsHearingModalOpen(true);
  };

  const handleNotifyHearing = async () => {
    if (!hearingDate) {
      setSuccessModal({ isOpen: false, title: '', message: '' });
      setErrorModal({
        isOpen: true,
        title: 'Missing Hearing Date',
        message: 'Please select a hearing date and time before notifying users.',
      });
      return;
    }

    try {
      if (hearingActionMode === 'reschedule') {
        const formData = new FormData();
        formData.append('hearing_date', format(new Date(hearingDate), "yyyy-MM-dd'T'HH:mm"));
        await rescheduleHearingMutation.mutateAsync(formData);
      } else {
        const hearingDateFormData = new FormData();
        hearingDateFormData.append("hearing_date", hearingDate);
        const respondents = additionalRespondents
          .map(({ name, email }) => ({ name: name.trim(), email: email.trim() }))
          .filter(({ name, email }) => name || email);

        if (respondents.some(({ name, email }) => !name || !email)) {
          setErrorModal({
            isOpen: true,
            title: 'Incomplete Person Details',
            message: 'Please provide both a name and email address for each additional person.',
          });
          return;
        }

        hearingDateFormData.append('respondents', JSON.stringify(respondents));
        await notifyHearingMutation.mutateAsync({
          incidentId: Number(incidentId),
          hearingDate: hearingDateFormData,
        });
      }
      setIsHearingModalOpen(false);
      setHearingDate('');
      setAdditionalRespondents([]);
    } catch (err) {
      console.error(err);
      const error = err as any;
      const errorMessage = error?.response?.data?.detail || 'Failed to notify/reschedule hearing.';
      setErrorModal({ isOpen: true, title: 'Error', message: errorMessage });
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

  // Check for valid coordinates
  const hasLocation =
    typeof incident.latitude === 'number' &&
    typeof incident.longitude === 'number' &&
    !isNaN(incident.latitude) &&
    !isNaN(incident.longitude);

  const incidentStatus = incident.complaint_clusters[0]?.complaint.status as ComplaintStatus;
  const isSubmitted = incidentStatus === "submitted";
  const isUnderReviewByBarangay = incidentStatus === "reviewed_by_barangay";
  const isUnderReviewByLgu = incidentStatus === "reviewed_by_lgu";
  const isResolved = incidentStatus === "resolved_by_barangay" || incidentStatus === "resolved_by_lgu";
  const isForwardedToLgu = incidentStatus === "forwarded_to_lgu";
  const isRejectedByLgu = incident.complaint_clusters[0]?.complaint?.is_rejected_by_lgu === true;
  const isRejected = incident.complaint_clusters[0]?.complaint?.status === "rejected"
  const isResolvable = incident.is_resolvable !== false;
  const isAssignedAwaitingMemberDecision = !isBarangayMember
    && isResolvable
    && incident.complaint_clusters.some((cluster) => cluster.complaint?.status === "reviewed_by_barangay");

  const incidentHearingDateRaw = (incident as any)?.hearing_date ?? (incident as any)?.hearingDate ?? null;
  const incidentHearingDate =
    typeof incidentHearingDateRaw === "string"
      ? incidentHearingDateRaw.trim() || null
      : incidentHearingDateRaw;
  const hasScheduledHearingDate = Boolean(incidentHearingDate);
  const hearingCount = Number(incident.hearing_count ?? 0);
  const hearingOutcome = incident.is_hearing_successful ?? null;
  const canScheduleFollowUpHearing = hasScheduledHearingDate && hearingOutcome === false;
  const shouldShowHearingControls = !isResolved && !isRejected && !isForwardedToLgu;
  const hearingDateLabel = getHearingDateLabel(hearingCount);
  const showNewComplaintBadge = Boolean(incident.has_new_complaints) || Number(incident.new_complaint_count ?? 0) > 0;
  const severityLabel = String(incident.severity_level ?? '').replace(/_/g, ' ');
  const titleStatusBadge = isResolved
    ? { label: 'Resolved', className: 'bg-green-50 text-green-700 border-green-200', dotClassName: 'bg-green-600' }
    : isRejected 
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

  // Helper to format hearing date as 'Month day, Year at Time'
  const formatHearingDate = (dateString: string) => {
    if (!dateString) return '';
    const date = new Date(dateString);
    if (Number.isNaN(date.getTime())) return dateString;
    return format(date, "M/d/yyyy 'at' hh:mm a");
  };

  return (
    <div className="space-y-6">
      {/* Top bar */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => navigate(isBarangayMember ? "/member/assigned-incidents" : "/dashboard/incidents")}
          className="inline-flex items-center gap-1.5 text-sm border border-green-300 bg-green-500 rounded-md px-3 py-2 text-white hover:text-white-900 hover:bg-green-600 transition-colors cursor-pointer"
        >
          <ArrowLeft size={16} />
          {t('incidents.details.backToIncidents')}
        </button>
        <span className="text-sm text-slate-500">Incident #{incident.id}</span>
      </div>

      {/* Title, badges, location (card) */}
      <div className={`${card} col-span-1 sm:col-span-2 lg:col-span-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4`}>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-semibold text-gray-900 wrap-break-word">{incident.title}</h1>
            {titleStatusBadge && (
              <div className={`inline-flex items-center gap-2 px-2.5 py-1 rounded-full border text-sm font-medium ${titleStatusBadge.className}`}>
                <span className={`w-1.5 h-1.5 rounded-full ${titleStatusBadge.dotClassName}`} />
                {titleStatusBadge.label}
              </div>
            )}
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-primary-50 text-sm font-medium text-primary-700 border border-primary-100">
              <AlertCircle size={14} />
              Category: {formatCategoryName(incident.category?.category_name)}
            </span>
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-orange-50 text-sm font-medium text-orange-700 border border-orange-100 capitalize">
              <AlertCircle size={14} />
              severity: {severityLabel}
            </span>
            
          </div>
          {hasScheduledHearingDate && (
              <span className="mt-4 inline-flex items-center gap-2 px-3 py-1.5 rounded-md bg-gray-100 text-sm text-gray-700">
                <CalendarIcon size={14} className="text-gray-500" />
                {hearingDateLabel}: <span className="font-medium">{formatHearingDate(incidentHearingDate as string)}</span>
              </span>
            )}
        </div>

        {hasLocation && (
          <button onClick={() => navigate(`${isBarangayMember ? "/member" : "/dashboard"}/incidents/${incident.id}/tracking`)} className={btnGreen}>
            <MapPin size={15} />
            View Incident Location
          </button>
        )}
      </div>

      {/* Metadata cards */}
      <dl className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="flex items-center gap-3 p-4 bg-white border border-gray-200 rounded-xl shadow-sm hover:shadow-md transition-shadow">
          <div className="w-11 h-11 rounded-lg bg-purple-50 text-purple-600 flex items-center justify-center shrink-0">
            <MapPin size={20} />
          </div>
          <div className="min-w-0">
            <dt className="text-sm font-medium text-slate-500">Barangay</dt>
            <dd className="mt-0.5 text-base font-semibold text-slate-900 truncate">
              {incident.barangay?.barangay_name || "N/A"}
            </dd>
          </div>
        </div>

        <div className="flex items-center gap-3 p-4 bg-white border border-gray-200 rounded-xl shadow-sm hover:shadow-md transition-shadow">
          <div className="w-11 h-11 rounded-lg bg-primary-50 text-primary-700 flex items-center justify-center shrink-0">
            <Users size={20} />
          </div>
          <div className="min-w-0">
            <dt className="text-sm font-medium text-slate-500">{t('incidents.details.totalComplaints')}</dt>
            <dd className="mt-0.5 text-base font-semibold text-primary-700">{incident.complaint_count}</dd>
          </div>
        </div>

        <div className="flex items-center gap-3 p-4 bg-white border border-gray-200 rounded-xl shadow-sm hover:shadow-md transition-shadow">
          <div className="w-11 h-11 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center shrink-0">
            <CalendarIcon size={20} />
          </div>
          <div className="min-w-0">
            <dt className="text-sm font-medium text-slate-500">{t('incidents.details.firstReported')}</dt>
            <dd className="mt-0.5 text-base font-semibold text-slate-900">
              {formatDate(incident.first_reported_at, { year: 'numeric', month: 'numeric', day: 'numeric' })}
            </dd>
          </div>
        </div>

        <div className="flex items-center gap-3 p-4 bg-white border border-gray-200 rounded-xl shadow-sm hover:shadow-md transition-shadow">
          <div className="w-11 h-11 rounded-lg bg-orange-50 text-orange-600 flex items-center justify-center shrink-0">
            <Clock size={20} />
          </div>
          <div className="min-w-0">
            <dt className="text-sm font-medium text-slate-500">{t('incidents.details.lastReported')}</dt>
            <dd className="mt-0.5 text-base font-semibold text-slate-900">
              {formatDate(incident.last_reported_at, { year: 'numeric', month: 'numeric', day: 'numeric' })}
            </dd>
          </div>
        </div>
      </dl>

      {/* Description + remarks */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6 items-start">
        <div className="lg:col-span-3 space-y-6">
          {/* Description card */}
          <section className={card}>
            <h2 className="text-base font-semibold text-primary-700 mb-2">{t('incidents.details.description')}</h2>
            <p className="text-base text-slate-800 leading-relaxed whitespace-pre-wrap">
              {incident.description}
            </p>
          </section>

          {/* Related complaints card */}
          <section className={`${card} flex items-center justify-between gap-3`}>
            <div className="min-w-0">
              <h3 className="text-base font-semibold text-primary-700">
                {t('incidents.details.relatedComplaints')} ({incident.complaint_count})
              </h3>
              <p className="text-sm text-slate-600">View all complaints associated with this incident.</p>
            </div>
            <button onClick={handleViewAllComplaints} className={`${btnOutline} relative shrink-0`}>
              <Users size={15} />
              {t('incidents.details.viewAllComplaints')}
              {showNewComplaintBadge && (
                <span className="absolute -top-2 -right-2 flex items-center justify-center">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-50" />
                  <span className="relative flex items-center justify-center min-w-5 h-5 px-1 rounded-full bg-orange-500 text-white text-xs font-bold">
                    {incident.complaint_count}
                  </span>
                </span>
              )}
            </button>
          </section>
        </div>

        {/* Remarks card */}
        <section className={`${card} lg:col-span-2`}>
          <h2 className="text-base font-semibold text-primary-700 mb-2">{t('incidents.details.remarks')}</h2>

          {sortedResponses.length === 0 ? (
            <p className="text-base text-slate-500">No responses yet.</p>
          ) : (
            <div className={`${sortedResponses.length > 2 ? 'max-h-80 overflow-y-auto' : ''} space-y-3 pr-1`}>
              {sortedResponses.map((response) => {
                const attachments = response.response_attachments ?? [];
                const assignedMembers = response.barangay_members ?? [];

                return (
                  <div key={response.id} className="rounded-lg border border-gray-300 bg-slate-50 p-4 shadow-sm">
                    <p className="text-base text-slate-800 whitespace-pre-wrap leading-6">
                      {response.actions_taken}
                    </p>

                    {attachments.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {attachments.map((attachment: any, idx: number) => (
                          <ResponseMediaAction
                            key={attachment.id ?? idx}
                            attachment={attachment}
                            onClick={() => {
                              if (attachment.media_type?.startsWith('application')) {
                                window.open(attachment.file_url, '_blank', 'noopener,noreferrer');
                                return;
                              }
                              setLightboxAttachment({ url: attachment.file_url, type: attachment.media_type ?? 'image' });
                            }}
                          />
                        ))}
                      </div>
                    )}
                    
                    {assignedMembers.length > 0 && (
                      <p className="mt-2 flex items-center gap-1.5 text-sm text-slate-600">
                        <UserRound className="h-4 w-4 shrink-0" aria-hidden="true" />
                        {t('incidents.details.assignedTo')}: {assignedMembers.map((member: any) => `${member.name} (${member.position})`).join(", ")}
                      </p>
                    )}
                    {response.user?.role === "barangay_member" ? (
                      <div className="mt-1 flex items-center justify-between gap-3">
                        <p className="flex items-center gap-1.5 text-sm text-slate-600">
                          <MapPin className="h-4 w-4 shrink-0" aria-hidden="true" />
                          {incident.barangay?.barangay_name
                            ? `Barangay ${incident.barangay.barangay_name}`
                            : "Barangay"}
                        </p>
                        <p className="text-xs text-slate-400">
                          {formatDateTime(response.response_date, {
                            year: 'numeric',
                            month: 'numeric',
                            day: 'numeric',
                          })}
                        </p>
                      </div>
                    ) : (
                      <div className="mt-2 flex items-center justify-between gap-3">
                        <p className="flex items-center gap-1.5 text-sm font-medium text-slate-600">
                          <MapPin className="h-4 w-4 shrink-0" aria-hidden="true" />
                          {getResponseAuthorName(response, incident)}
                        </p>
                        <p className="text-xs text-slate-400">
                          {formatDateTime(response.response_date, {
                            year: 'numeric',
                            month: 'numeric',
                            day: 'numeric',
                          })}
                        </p>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </div>

      {/* Action bar card: incident actions and hearing controls in one place */}
      {shouldShowHearingControls && (
        <div className={`${card} flex flex-col gap-3`}>
          {isAssignedAwaitingMemberDecision && (
            <p className="text-sm text-amber-800">
              This incident has been assigned to a Barangay Member. Please wait for their decision on whether it can be resolved.
            </p>
          )}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              {isBarangayMember ? (
                <>
                  {isResolvable ? (
                    <>
                      <button
                        onClick={handleResolve}
                        disabled={resolveIncidentMutation.isPending}
                        className={btnSolid}
                      >
                        {resolveIncidentMutation.isPending ? "Resolving..." : "Resolve incident"}
                      </button>
                      <button
                        onClick={handleMarkUnresolvable}
                        disabled={unresolvableMutation.isPending}
                        className={btnDanger}
                      >
                        {unresolvableMutation.isPending ? "Updating..." : "Unresolvable"}
                      </button>
                    </>
                  ) : (
                    <p className="text-sm text-slate-600">This incident has been marked as unresolvable.</p>
                  )}
                </>
              ) : (
                <>
                  <button
                    onClick={handleReview}
                    disabled={isUnderReviewByBarangay || isUnderReviewByLgu || reviewIncidentMutation.isPending || isForwardedToLgu || isResolved || isRejectedByLgu}
                    className={btnYellow}
                  >
                    {reviewIncidentMutation.isPending ? "Reviewing..." : "Mark for review"}
                  </button>
                  <button
                    onClick={handleForwardToLgu}
                    disabled={forwardToLguMutation.isPending || isSubmitted || isResolved || isUnderReviewByLgu || isForwardedToLgu || isRejectedByLgu || isRejected || isAssignedAwaitingMemberDecision}
                    className={btnBlue}
                  >
                    {forwardToLguMutation.isPending ? "Forwarding..." : "Escalate to LGU"}
                  </button>
                  <button
                    onClick={handleReject}
                    disabled={!isUnderReviewByBarangay || isForwardedToLgu || rejectIncidentMutation.isPending || isResolved || isRejected || isAssignedAwaitingMemberDecision}
                    className={btnDanger}
                  >
                    {rejectIncidentMutation.isPending ? "Rejecting..." : "Reject"}
                  </button>

                  <button
                    onClick={handleResolve}
                    disabled={isUnderReviewByLgu || resolveIncidentMutation.isPending || isSubmitted || isResolved || isForwardedToLgu || isRejected || isAssignedAwaitingMemberDecision}
                    className={btnSolid}
                  >
                    {resolveIncidentMutation.isPending ? "Resolving..." : "Resolve"}
                  </button>
                </>
              )}
            </div>
            {!isBarangayMember && (
              <div className="flex flex-wrap items-center justify-end gap-2">
                {hasScheduledHearingDate && (
                  <>
                    <button
                      onClick={() => handleMarkHearingOutcome(true)}
                      disabled={markHearingMutation.isPending || hearingOutcome !== null}
                      className={btnOutline}
                    >
                      {markHearingMutation.isPending ? 'Updating...' : 'Hearing successful'}
                    </button>
                    <button
                      onClick={() => handleMarkHearingOutcome(false)}
                      disabled={markHearingMutation.isPending || hearingOutcome !== null}
                      className={btnDanger}
                    >
                      {markHearingMutation.isPending ? 'Updating...' : 'Hearing unsuccessful'}
                    </button>
                  </>
                )}

                {!hasScheduledHearingDate && (
                  <button
                    onClick={() => handleOpenHearingModal('notify')}
                    disabled={isHearingMutationPending || isSubmitted || isResolved || isUnderReviewByLgu || isForwardedToLgu || isRejected || isAssignedAwaitingMemberDecision}
                    className={btnOutline}
                  >
                    <CalendarIcon size={15} />
                    {isHearingMutationPending ? 'Notifying...' : 'Notify for hearing'}
                  </button>
                )}

                {canScheduleFollowUpHearing && (
                  <button
                    onClick={() => handleOpenHearingModal('reschedule')}
                    disabled={isHearingMutationPending || isSubmitted || isResolved || isUnderReviewByLgu || isForwardedToLgu || isRejected || isAssignedAwaitingMemberDecision}
                    className={btnOutline}
                  >
                    <CalendarIcon size={15} />
                    {isHearingMutationPending ? 'Rescheduling...' : 'Schedule new hearing'}
                  </button>
                )}
              </div>
            )}
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
        externalError={attachmentError}
        barangayMembers={isBarangayMember ? [] : barangayMembers}
      />

      <RejectIncidentModal
        isOpen={isRejectModalOpen}
        title="Reject Incident"
        description="Please choose a rejection reason and explain why this incident is being rejected. This will be recorded and visible to complainants."
        confirmText="Reject"
        confirmColor="red"
        onCancel={() => {
          setIsRejectModalOpen(false);
          rejectIncidentMutation.reset();
        }}
        isLoading={rejectIncidentMutation.isPending}
        rejectionCategories={rejectionCategories ?? []}
        isLoadingCategories={isLoadingRejectionCategories}
        categoryError={rejectionCategoriesError ? 'Failed to load rejection reasons. Please try again.' : undefined}
        barangayMembers={barangayMembers}
        onConfirm={async (actionsTaken: string, rejectionCategoryId: number, attachments: File[], barangayMemberIds: number[]) => {
          await rejectIncidentMutation.mutateAsync({
            actions_taken: actionsTaken,
            rejection_category_id: rejectionCategoryId,
            attachments,
            barangay_member_ids: barangayMemberIds,
          });
        }}
      />

      {/* Modal */}
      {isHearingModalOpen && (
        <div
          className="fixed inset-0 flex items-center justify-center z-50 p-4 bg-black bg-opacity-50"
          onClick={(e) => e.target === e.currentTarget && setIsHearingModalOpen(false)}
        >
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm w-full max-w-sm overflow-hidden">

            {/* Header */}
            <div className="px-6 pt-5 pb-4 border-b border-gray-100 flex items-start justify-between gap-3">
              <div>
                <h3 className="text-base font-medium text-gray-900">
                  {hearingActionMode === 'reschedule' ? 'Reschedule Hearing Date' : hasScheduledHearingDate ? 'Schedule a New Hearing' : 'Notify Complainants for Hearing'}
                </h3>
                <p className="text-xs text-gray-400 mt-0.5 leading-relaxed">
                  Select a date and time to notify all complainants.
                </p>
              </div>
              <button
                onClick={() => setIsHearingModalOpen(false)}
                className="w-7 h-7 flex items-center justify-center rounded-lg border border-gray-200 text-gray-400 hover:bg-gray-50 transition-colors text-sm"
              >
                ✕
              </button>
            </div>

            <div className="px-6 pt-5 pb-6">
              <label className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-widest text-primary-700 mb-2.5">
                <CalendarIcon className="w-3.5 h-3.5" />
                Date &amp; Time
              </label>

              <div className="mb-4">
                <CustomDateTimePicker
                  value={hearingDate ? new Date(hearingDate) : null}
                  onChange={(date) => setHearingDate(format(date, "yyyy-MM-dd'T'HH:mm"))}
                  minDate={startOfTomorrow()}
                />
              </div>

              {hearingActionMode === 'notify' && (
                <div className="mb-5 space-y-3">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium text-gray-800">Additional people to notify</p>
                      <p className="text-xs text-gray-500">Add another person involved in the complaint.</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setAdditionalRespondents((current) => [...current, { name: '', email: '' }])}
                      className="shrink-0 px-3 py-1.5 text-xs font-medium text-primary-700 border border-primary-200 rounded-lg hover:bg-primary-50 transition-colors"
                    >
                      Add person
                    </button>
                  </div>

                  {additionalRespondents.map((respondent, index) => (
                    <div key={index} className="flex items-start gap-2">
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 flex-1">
                        <input
                          type="text"
                          value={respondent.name}
                          onChange={(event) => setAdditionalRespondents((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, name: event.target.value } : item))}
                          placeholder="Full name"
                          className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                          aria-label={`Additional person's name ${index + 1}`}
                        />
                        <input
                          type="email"
                          value={respondent.email}
                          onChange={(event) => setAdditionalRespondents((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, email: event.target.value } : item))}
                          placeholder="Email address"
                          className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                          aria-label={`Additional person's email ${index + 1}`}
                        />
                      </div>
                      <button
                        type="button"
                        onClick={() => setAdditionalRespondents((current) => current.filter((_, itemIndex) => itemIndex !== index))}
                        className="p-2 text-gray-400 hover:text-red-600 transition-colors"
                        aria-label={`Remove additional person ${index + 1}`}
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {hearingDate && (
                <div className="inline-flex items-center justify-center gap-2 px-3 py-1.5 bg-primary-50 rounded-full text-xs text-primary-800 mb-5">
                  <span className="w-1.5 h-1.5 rounded-full bg-primary-400 shrink-0" />
                  {new Date(hearingDate).toLocaleDateString("en-US", {
                    weekday: "short", month: "short", day: "numeric", year: "numeric"
                  }) + " · " + new Date(hearingDate).toLocaleTimeString("en-US", {
                    hour: "numeric", minute: "2-digit"
                  })}
                </div>
              )}

              <div className="flex items-center gap-2.5">
                <button
                  type="button"
                  onClick={() => setIsHearingModalOpen(false)}
                  disabled={isHearingMutationPending}
                  className="px-4 py-2.5 text-sm text-gray-500 border border-gray-200 rounded-xl hover:bg-gray-50 hover:text-gray-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleNotifyHearing}
                  disabled={isHearingMutationPending || !hearingDate}
                  className="flex-1 flex items-center justify-center gap-2 py-2.5 text-sm font-medium text-white bg-primary-600 rounded-xl hover:bg-primary-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <span className="w-4 h-4 rounded-full border border-primary-300 flex items-center justify-center text-[9px]">✓</span>
                  {isHearingMutationPending
                    ? hearingActionMode === 'reschedule' ? 'Rescheduling...' : 'Notifying...'
                    : hearingActionMode === 'reschedule'
                      ? 'Confirm & Reschedule'
                      : 'Confirm & Notify'}
                </button>
              </div>
            </div>

          </div>
        </div>
      )}

      <ConfirmationModal
        isOpen={confirmationModal.isOpen}
        title={confirmationModal.title}
        message={confirmationModal.message}
        confirmText={confirmationModal.confirmText}
        confirmColor={confirmationModal.confirmColor}
        onConfirm={confirmationModal.confirm}
        onCancel={confirmationModal.closeModal}
        isLoading={confirmationModal.isLoading}
      />

      <SuccessModal
        isOpen={successModal.isOpen}
        title={successModal.title}
        message={successModal.message}
        onClose={() => {
          if (successModal.shouldNavigateOnClose !== false) {
            navigate(isBarangayMember ? "/member/assigned-incidents" : "/dashboard/incidents");
          }
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