import { useState, useCallback } from "react";

interface ActionsTakenModalState {
  isOpen: boolean;
  title: string;
  description?: string;
  confirmText: string;
  confirmColor: "red" | "green" | "yellow" | "blue";
  onConfirm: (actionsTaken: string, attachments: File[], barangayMemberIds: number[]) => void;
  onCancel?: () => void;
  isLoading: boolean;
  showBarangayMembers: boolean;
}

export function useActionsTakenModal() {
  const [state, setState] = useState<ActionsTakenModalState>({
    isOpen: false,
    title: "",
    description: "",
    confirmText: "",
    confirmColor: "green",
    onConfirm: () => {},
    onCancel: undefined,
    isLoading: false,
    showBarangayMembers: true,
  });

  const openModal = useCallback(
    ({
      title,
      confirmText,
      confirmColor = "green",
      onConfirm,
      onCancel,
      description,
      showBarangayMembers = true,
    }: {
      title: string;
      confirmText: string;
      confirmColor?: "red" | "green" | "yellow" | "blue";
      onConfirm: (actionsTaken: string, attachments: File[], barangayMemberIds: number[]) => void;
      onCancel?: () => void;
      description?: string;
      showBarangayMembers?: boolean;
    }) => {
      setState((prev) => ({
        ...prev,
        isOpen: true,
        title,
        confirmText,
        confirmColor,
        onConfirm,
        onCancel,
        description,
        showBarangayMembers,
      }));
    },
    []
  );

  const closeModal = useCallback(() => {
    setState((prev) => ({
      ...prev,
      isOpen: false,
      isLoading: false,
    }));
  }, []);

  const cancelModal = useCallback(() => {
    if (state.onCancel) {
      state.onCancel();
    }
    setState((prev) => ({
      ...prev,
      isOpen: false,
      isLoading: false,
    }));
  }, [state.onCancel]);

  const setIsLoading = useCallback((value: boolean) => {
    setState((prev) => ({
      ...prev,
      isLoading: value,
    }));
  }, []);

  return {
    isOpen: state.isOpen,
    title: state.title,
    confirmText: state.confirmText,
    confirmColor: state.confirmColor,
    isLoading: state.isLoading,
    description: state.description,
    showBarangayMembers: state.showBarangayMembers,

    setIsLoading,
    openModal,
    closeModal,
    cancelModal,
    onConfirm: state.onConfirm, // ✅ unchanged API
  };
}