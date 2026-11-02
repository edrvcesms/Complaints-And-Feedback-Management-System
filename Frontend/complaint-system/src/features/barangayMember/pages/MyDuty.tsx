import { useEffect, useState } from "react";
import { isAxiosError } from "axios";
import { CalendarClock, Clock3, Play, Square } from "lucide-react";
import { useMyBarangayDuty, useUpdateMyBarangayDuty } from "../../../hooks/useBarangays";

const toLocalDateTimeInput = (value: Date) => {
  const localValue = new Date(value.getTime() - value.getTimezoneOffset() * 60_000);
  return localValue.toISOString().slice(0, 16);
};

const getErrorMessage = (error: unknown) => {
  if (isAxiosError<{ detail?: string }>(error)) {
    return error.response?.data?.detail ?? error.message;
  }
  return error instanceof Error ? error.message : "Unable to update your duty schedule.";
};

export const MyDuty: React.FC = () => {
  const { duty, isLoading, error } = useMyBarangayDuty();
  const updateDuty = useUpdateMyBarangayDuty();
  const [start, setStart] = useState(() => toLocalDateTimeInput(new Date()));
  const [end, setEnd] = useState(() => toLocalDateTimeInput(new Date(Date.now() + 8 * 60 * 60_000)));
  const [message, setMessage] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (!duty) return;
    if (duty.start_of_duty) setStart(toLocalDateTimeInput(new Date(duty.start_of_duty)));
    if (duty.end_of_duty) setEnd(toLocalDateTimeInput(new Date(duty.end_of_duty)));
  }, [duty]);

  const submitSchedule = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormError(null);
    setMessage(null);

    const startDate = new Date(start);
    const endDate = new Date(end);
    if (!Number.isFinite(startDate.getTime()) || !Number.isFinite(endDate.getTime()) || endDate <= startDate) {
      setFormError("Choose a valid end time that is later than the start time.");
      return;
    }

    try {
      await updateDuty.mutateAsync({
        start_of_duty: startDate.toISOString(),
        end_of_duty: endDate.toISOString(),
      });
      setMessage("Your duty schedule has been saved.");
    } catch (updateError) {
      setFormError(getErrorMessage(updateError));
    }
  };

  const startDutyNow = async () => {
    setFormError(null);
    setMessage(null);
    try {
      await updateDuty.mutateAsync({
        start_of_duty: new Date().toISOString(),
        end_of_duty: null,
      });
      setMessage("You are now on duty. End duty when your shift is over.");
    } catch (updateError) {
      setFormError(getErrorMessage(updateError));
    }
  };

  const endDutyNow = async () => {
    if (!duty?.start_of_duty) return;
    setFormError(null);
    setMessage(null);
    try {
      await updateDuty.mutateAsync({
        start_of_duty: duty.start_of_duty,
        end_of_duty: new Date().toISOString(),
      });
      setMessage("Your duty has ended.");
    } catch (updateError) {
      setFormError(getErrorMessage(updateError));
    }
  };

  return (
    <section className="mx-auto max-w-3xl space-y-6">
      <header>
        <div className="flex items-center gap-3">
          <CalendarClock className="h-7 w-7 text-blue-700" />
          <div>
            <h1 className="text-2xl font-bold text-slate-900">My Duty</h1>
            <p className="mt-1 text-sm text-slate-600">Manage your Barangay duty status and shift schedule.</p>
          </div>
        </div>
      </header>

      {isLoading ? (
        <p className="rounded-xl bg-white p-5 text-sm text-slate-600 shadow-sm">Loading your duty status…</p>
      ) : error ? (
        <p role="alert" className="rounded-xl bg-red-50 p-5 text-sm text-red-800">
          {getErrorMessage(error)}
        </p>
      ) : (
        <>
          <div className={`rounded-xl border p-5 ${duty?.is_on_duty ? "border-green-200 bg-green-50" : "border-slate-200 bg-white"}`}>
            <div className="flex items-center gap-2">
              <Clock3 className={`h-5 w-5 ${duty?.is_on_duty ? "text-green-700" : "text-slate-500"}`} />
              <h2 className="font-semibold text-slate-900">
                {duty?.is_on_duty ? "You are currently on duty" : "You are currently off duty"}
              </h2>
            </div>
            <p className="mt-2 text-sm text-slate-600">
              {duty?.start_of_duty
                ? `Duty starts: ${new Date(duty.start_of_duty).toLocaleString()}`
                : "No duty start time is set."}
              {duty?.end_of_duty ? ` · Ends: ${new Date(duty.end_of_duty).toLocaleString()}` : duty?.is_on_duty ? " · No end time set" : ""}
            </p>
            <div className="mt-4 flex flex-wrap gap-3">
              {!duty?.is_on_duty && (
                <button
                  type="button"
                  onClick={startDutyNow}
                  disabled={updateDuty.isPending}
                  className="inline-flex items-center gap-2 rounded-lg bg-green-700 px-4 py-2 text-sm font-semibold text-white hover:bg-green-800 disabled:opacity-60"
                >
                  <Play className="h-4 w-4" /> Start duty now
                </button>
              )}
              {duty?.is_on_duty && (
                <button
                  type="button"
                  onClick={endDutyNow}
                  disabled={updateDuty.isPending}
                  className="inline-flex items-center gap-2 rounded-lg bg-slate-800 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-900 disabled:opacity-60"
                >
                  <Square className="h-4 w-4" /> End duty now
                </button>
              )}
            </div>
          </div>

          <form onSubmit={submitSchedule} className="space-y-4 rounded-xl bg-white p-5 shadow-sm">
            <div>
              <h2 className="font-semibold text-slate-900">Schedule a shift</h2>
              <p className="mt-1 text-sm text-slate-600">Set when you will be on duty. Your location is shared while you are signed in and the member portal is open.</p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="space-y-1 text-sm font-medium text-slate-700">
                Duty starts
                <input
                  type="datetime-local"
                  required
                  value={start}
                  onChange={(event) => setStart(event.target.value)}
                  className="block w-full rounded-lg border border-slate-300 px-3 py-2"
                />
              </label>
              <label className="space-y-1 text-sm font-medium text-slate-700">
                Duty ends
                <input
                  type="datetime-local"
                  required
                  value={end}
                  onChange={(event) => setEnd(event.target.value)}
                  className="block w-full rounded-lg border border-slate-300 px-3 py-2"
                />
              </label>
            </div>
            {formError && <p role="alert" className="text-sm text-red-700">{formError}</p>}
            {message && <p role="status" className="text-sm text-green-700">{message}</p>}
            <button
              type="submit"
              disabled={updateDuty.isPending}
              className="rounded-lg bg-blue-700 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-60"
            >
              {updateDuty.isPending ? "Saving…" : "Save schedule"}
            </button>
          </form>
        </>
      )}
    </section>
  );
};

export default MyDuty;
