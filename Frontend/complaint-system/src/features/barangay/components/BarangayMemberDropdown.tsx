import React, { useState } from "react";

interface BarangayMemberDropdownProps {
  members: Array<{ id: number; name: string; position: string }>;
  selectedMemberIds: string[];
  onChange: (memberIds: string[]) => void;
  disabled?: boolean;
}

export const BarangayMemberDropdown: React.FC<BarangayMemberDropdownProps> = ({
  members,
  selectedMemberIds,
  onChange,
  disabled = false,
}) => {
  const [isOpen, setIsOpen] = useState(false);

  const toggleMember = (memberId: string) => {
    onChange(
      selectedMemberIds.includes(memberId)
        ? selectedMemberIds.filter((id) => id !== memberId)
        : [...selectedMemberIds, memberId]
    );
  };

  const selectedMembers = members.filter((member) =>
    selectedMemberIds.includes(String(member.id))
  );

  return (
    <div className="relative w-full">
      {/* Dropdown Button */}
      <button
        type="button"
        onClick={() => setIsOpen((open) => !open)}
        disabled={disabled}
        className={`
          flex min-h-[44px] w-full items-center justify-between
          rounded-lg border bg-white px-3 py-2
          text-left text-sm transition-all duration-150
          ${
            isOpen
              ? "border-primary-500 ring-2 ring-primary-500/20"
              : "border-gray-300 hover:border-gray-400"
          }
          disabled:cursor-not-allowed disabled:bg-gray-50 disabled:opacity-60
        `}
      >
        <div className="flex min-w-0 flex-1 items-center gap-2">
          {selectedMembers.length > 0 ? (
            <div className="flex min-w-0 flex-wrap gap-1">
              {selectedMembers.slice(0, 2).map((member) => (
                <span
                  key={member.id}
                  className="inline-flex items-center rounded-md bg-primary-50 px-2 py-1 text-xs font-medium text-primary-700"
                >
                  {member.name} · {member.position}
                </span>
              ))}

              {selectedMembers.length > 2 && (
                <span className="inline-flex items-center rounded-md bg-gray-100 px-2 py-1 text-xs font-medium text-gray-600">
                  +{selectedMembers.length - 2} more
                </span>
              )}
            </div>
          ) : (
            <span className="text-gray-500">
              Select barangay members
            </span>
          )}
        </div>

        {/* Chevron */}
        <svg
          className={`ml-2 h-4 w-4 shrink-0 text-gray-400 transition-transform duration-200 ${
            isOpen ? "rotate-180" : ""
          }`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="m19 9-7 7-7-7"
          />
        </svg>
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <>
          {/* Optional backdrop for mobile */}
          <div
            className="fixed inset-0 z-10"
            onClick={() => setIsOpen(false)}
          />

          <div className="absolute left-0 right-0 z-20 mt-2 overflow-hidden rounded-lg border border-gray-200 bg-white shadow-xl">
            {/* Header */}
            <div className="flex items-center justify-between border-b border-gray-100 px-3 py-2.5">
              <div>
                <p className="text-sm font-semibold text-gray-800">
                  Barangay Members
                </p>
                <p className="text-xs text-gray-500">
                  Select members to assign
                </p>
              </div>

              {selectedMemberIds.length > 0 && (
                <span className="rounded-full bg-primary-50 px-2 py-1 text-xs font-medium text-primary-700">
                  {selectedMemberIds.length} selected
                </span>
              )}
            </div>

            {/* Members */}
            <div className="max-h-60 overflow-y-auto p-1.5">
              {members.length > 0 ? (
                members.map((member) => {
                  const memberId = String(member.id);
                  const isSelected = selectedMemberIds.includes(memberId);

                  return (
                    <button
                      key={member.id}
                      type="button"
                      onClick={() => toggleMember(memberId)}
                      className={`
                        flex w-full items-center gap-3 rounded-md px-2.5 py-2.5
                        text-left transition-colors
                        ${
                          isSelected
                            ? "bg-primary-50"
                            : "hover:bg-gray-50"
                        }
                      `}
                    >
                      {/* Checkbox */}
                      <div
                        className={`
                          flex h-5 w-5 shrink-0 items-center justify-center
                          rounded border transition-all
                          ${
                            isSelected
                              ? "border-primary-600 bg-primary-600"
                              : "border-gray-300 bg-white"
                          }
                        `}
                      >
                        {isSelected && (
                          <svg
                            className="h-3.5 w-3.5 text-white"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                            strokeWidth={3}
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              d="m5 12 4 4L19 7"
                            />
                          </svg>
                        )}
                      </div>

                      {/* Member Avatar */}
                      <div
                        className={`
                          flex h-9 w-9 shrink-0 items-center justify-center
                          rounded-full text-xs font-semibold
                          ${
                            isSelected
                              ? "bg-primary-100 text-primary-700"
                              : "bg-gray-100 text-gray-600"
                          }
                        `}
                      >
                        {member.name
                          .split(" ")
                          .slice(0, 2)
                          .map((name) => name.charAt(0))
                          .join("")
                          .toUpperCase()}
                      </div>

                      {/* Member Information */}
                      <div className="min-w-0 flex-1">
                        <p
                          className={`truncate text-sm font-medium ${
                            isSelected
                              ? "text-primary-900"
                              : "text-gray-800"
                          }`}
                        >
                          {member.name}
                        </p>

                        <p className="truncate text-xs text-gray-500">
                          {member.position}
                        </p>
                      </div>
                    </button>
                  );
                })
              ) : (
                <div className="px-4 py-8 text-center">
                  <div className="mx-auto mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-gray-100">
                    <svg
                      className="h-5 w-5 text-gray-400"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={1.5}
                        d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m8-8a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm10 8v-2a4 4 0 0 0-3-3.87m-1-8a4 4 0 0 1 0 7.75"
                      />
                    </svg>
                  </div>

                  <p className="text-sm font-medium text-gray-700">
                    No members available
                  </p>

                  <p className="mt-1 text-xs text-gray-500">
                    Add barangay members first.
                  </p>
                </div>
              )}
            </div>

            {/* Footer */}
            {members.length > 0 && (
              <div className="flex items-center justify-between border-t border-gray-100 bg-gray-50 px-3 py-2">
                <span className="text-xs text-gray-500">
                  {selectedMemberIds.length === 0
                    ? "No members selected"
                    : `${selectedMemberIds.length} member${
                        selectedMemberIds.length === 1 ? "" : "s"
                      } selected`}
                </span>

                <button
                  type="button"
                  onClick={() => setIsOpen(false)}
                  className="rounded-md px-3 py-1.5 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-200 hover:text-gray-900"
                >
                  Done
                </button>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
};