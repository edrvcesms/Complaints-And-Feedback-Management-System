import { useEffect, useRef } from "react";
import { updateCurrentUserLocation } from "../../../services/users/location";

const LOCATION_SYNC_INTERVAL_MS = 10 * 60_000;

export const MemberLocationReporter: React.FC = () => {
  const syncInFlight = useRef(false);

  useEffect(() => {
    if (!navigator.geolocation) {
      console.error("This browser does not support location sharing.");
      return;
    }

    const syncPosition = async (position: GeolocationPosition) => {
      if (syncInFlight.current) return;
      syncInFlight.current = true;
      try {
        await updateCurrentUserLocation(position.coords.latitude, position.coords.longitude);
      } catch (error) {
        console.error("Unable to update Barangay Member location:", error);
      } finally {
        syncInFlight.current = false;
      }
    };

    const handlePositionError = (error: GeolocationPositionError) => {
      console.error("Unable to obtain Barangay Member location:", error.message);
    };

    const requestLocationUpdate = () => {
      navigator.geolocation.getCurrentPosition(syncPosition, handlePositionError, {
        enableHighAccuracy: true,
        timeout: 15_000,
        maximumAge: 5_000,
      });
    };

    requestLocationUpdate();
    const heartbeatId = window.setInterval(requestLocationUpdate, LOCATION_SYNC_INTERVAL_MS);

    return () => {
      window.clearInterval(heartbeatId);
    };
  }, []);

  return null;
};
