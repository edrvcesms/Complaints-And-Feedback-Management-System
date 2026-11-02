import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { MapContainer, Marker, Polyline, Popup, TileLayer, useMap } from "react-leaflet";
import type { Map as LeafletMap, LatLngExpression } from "leaflet";
import L from "leaflet";
import { ArrowLeft, LocateFixed, Navigation, Satellite, StopCircle } from "lucide-react";
import { useIncidentDetails } from "../../../hooks/useIncidents";
import { useOnDutyBarangayMembers } from "../../../hooks/useBarangays";
import { useUserRole } from "../../../hooks/useUserRole";
import LoadingIndicator from "./../LoadingIndicator";
import markerIcon2x from "leaflet/dist/images/marker-icon-2x.png";
import markerIcon from "leaflet/dist/images/marker-icon.png";
import markerShadow from "leaflet/dist/images/marker-shadow.png";
import "leaflet/dist/leaflet.css";

type Coordinates = { latitude: number; longitude: number };
type TrackingState = "requesting" | "tracking" | "denied" | "unavailable" | "error" | "stopped";

const ROUTE_REFRESH_DISTANCE_METERS = 100;
const DEVICE_LOCATION_REFRESH_INTERVAL_MS = 15_000;
const LOCATION_FRESHNESS_LIMIT_MS = 20 * 60_000;

L.Icon.Default.mergeOptions({ iconRetinaUrl: markerIcon2x, iconUrl: markerIcon, shadowUrl: markerShadow });

const responderIcon = L.divIcon({
  className: "responder-location-marker",
  html: '<div style="width:22px;height:22px;border-radius:50%;background:#2563eb;border:4px solid white;box-shadow:0 1px 6px rgba(0,0,0,.45)"></div>',
  iconSize: [22, 22],
  iconAnchor: [11, 11],
});

const getOnDutyMemberIcon = (name: string) => {
  const escapedName = name
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
  return L.divIcon({
    className: "on-duty-member-location-marker",
    html: `<div style="display:flex;align-items:center;gap:6px;width:max-content"><span style="display:block;width:20px;height:20px;flex:none;border-radius:50%;background:#16a34a;border:3px solid white;box-shadow:0 1px 6px rgba(0,0,0,.45)"></span><span style="display:block;max-width:180px;overflow:hidden;text-overflow:ellipsis;padding:3px 7px;border-radius:5px;background:#fff;color:#14532d;font-size:12px;font-weight:600;line-height:1.25;box-shadow:0 1px 5px rgba(0,0,0,.3);white-space:nowrap">${escapedName}</span></div>`,
    iconSize: [20, 20],
    iconAnchor: [10, 10],
  });
};

const toRadians = (value: number) => (value * Math.PI) / 180;
const distanceInMeters = (a: Coordinates, b: Coordinates) => {
  const earthRadius = 6371000;
  const latitudeDelta = toRadians(b.latitude - a.latitude);
  const longitudeDelta = toRadians(b.longitude - a.longitude);
  const haversine =
    Math.sin(latitudeDelta / 2) ** 2 +
    Math.cos(toRadians(a.latitude)) * Math.cos(toRadians(b.latitude)) * Math.sin(longitudeDelta / 2) ** 2;
  return earthRadius * 2 * Math.atan2(Math.sqrt(haversine), Math.sqrt(1 - haversine));
};

const formatDistance = (meters: number) => (meters < 1000 ? `${Math.round(meters)} m` : `${(meters / 1000).toFixed(1)} km`);

function MapViewport({ responder, incident, members, mapRef }: { responder: Coordinates | null; incident: Coordinates; members: Coordinates[]; mapRef: React.MutableRefObject<LeafletMap | null> }) {
  const map = useMap();
  const didFit = useRef(false);

  useEffect(() => {
    mapRef.current = map;
    if (!didFit.current) {
      const locations: [number, number][] = [
        [incident.latitude, incident.longitude],
        ...(responder ? [[responder.latitude, responder.longitude] as [number, number]] : []),
        ...members.map((member) => [member.latitude, member.longitude] as [number, number]),
      ];
      const bounds = L.latLngBounds(locations);
      map.fitBounds(bounds.pad(0.2), { maxZoom: 16 });
      didFit.current = true;
    }
    return () => {
      mapRef.current = null;
    };
  }, [incident, map, mapRef, members, responder]);

  return null;
}

export const IncidentTrackingPage: React.FC = () => {
  const { incidentId } = useParams<{ incidentId: string }>();
  const navigate = useNavigate();
  const { incident, isLoading, error } = useIncidentDetails(Number(incidentId));
  const { isBarangayOfficial, isBarangayMember } = useUserRole();
  const { members: onDutyMembers, isLoading: areOnDutyMembersLoading, error: onDutyMembersError } = useOnDutyBarangayMembers(
    isBarangayOfficial ? incident?.barangay_id : undefined,
  );
  const shouldTrackCurrentLocation = !isBarangayOfficial
    || (!areOnDutyMembersLoading && !onDutyMembersError && onDutyMembers.length === 0);
  const [responder, setResponder] = useState<Coordinates | null>(null);
  const [trackingState, setTrackingState] = useState<TrackingState>("requesting");
  const [message, setMessage] = useState("Requesting access to your device location…");
  const [route, setRoute] = useState<LatLngExpression[]>([]);
  const [routeLoading, setRouteLoading] = useState(false);
  const [nearestMemberRoute, setNearestMemberRoute] = useState<LatLngExpression[]>([]);
  const [nearestMemberRouteLoading, setNearestMemberRouteLoading] = useState(false);
  const [satellite, setSatellite] = useState(false);
  const [trackingAttempt, setTrackingAttempt] = useState(0);
  const [freshnessClock, setFreshnessClock] = useState(() => Date.now());
  const watchId = useRef<number | null>(null);
  const heartbeatId = useRef<number | null>(null);
  const lastRoutedLocation = useRef<Coordinates | null>(null);
  const mapRef = useRef<LeafletMap | null>(null);

  useEffect(() => {
    const intervalId = window.setInterval(() => setFreshnessClock(Date.now()), 60_000);
    return () => window.clearInterval(intervalId);
  }, []);

  const destination = useMemo(
    () => (incident && Number.isFinite(incident.latitude) && Number.isFinite(incident.longitude)
      ? { latitude: incident.latitude, longitude: incident.longitude }
      : null),
    [incident],
  );

  const onDutyLocations = useMemo(
    () => onDutyMembers.map((member) => {
      const latitudeValue = member.user?.latitude;
      const longitudeValue = member.user?.longitude;
      const latitude = latitudeValue == null || latitudeValue.trim() === "" ? Number.NaN : Number(latitudeValue);
      const longitude = longitudeValue == null || longitudeValue.trim() === "" ? Number.NaN : Number(longitudeValue);
      return Number.isFinite(latitude) && Number.isFinite(longitude)
        && latitude >= -90 && latitude <= 90
        && longitude >= -180 && longitude <= 180
        ? {
            member,
            coordinates: { latitude, longitude },
            freshness: member.user?.location_updated_at
              ? freshnessClock - new Date(member.user.location_updated_at).getTime()
              : Number.POSITIVE_INFINITY,
          }
        : { member, coordinates: null, freshness: Number.POSITIVE_INFINITY };
    }),
    [freshnessClock, onDutyMembers],
  );

  const membersByDistance = useMemo(
    () => destination
      ? onDutyLocations
          .map((entry) => ({
            ...entry,
            isFresh: entry.freshness >= 0 && entry.freshness <= LOCATION_FRESHNESS_LIMIT_MS,
            distance: entry.coordinates && entry.freshness >= 0 && entry.freshness <= LOCATION_FRESHNESS_LIMIT_MS
              ? distanceInMeters(entry.coordinates, destination)
              : null,
          }))
          .sort((a, b) => (a.distance ?? Number.POSITIVE_INFINITY) - (b.distance ?? Number.POSITIVE_INFINITY))
      : onDutyLocations.map((entry) => ({
          ...entry,
          isFresh: entry.freshness >= 0 && entry.freshness <= LOCATION_FRESHNESS_LIMIT_MS,
          distance: null,
        })),
    [destination, onDutyLocations],
  );
  const closestMember = membersByDistance.find((entry) => entry.coordinates && entry.isFresh && entry.distance !== null);

  useEffect(() => {
    const origin = closestMember?.coordinates;
    if (!isBarangayOfficial || !origin || !destination) {
      setNearestMemberRoute([]);
      setNearestMemberRouteLoading(false);
      return;
    }

    const controller = new AbortController();
    setNearestMemberRoute([]);
    setNearestMemberRouteLoading(true);

    const fetchNearestMemberRoute = async () => {
      try {
        const url = `https://router.project-osrm.org/route/v1/driving/${origin.longitude},${origin.latitude};${destination.longitude},${destination.latitude}?overview=full&geometries=geojson`;
        const response = await fetch(url, { signal: controller.signal });
        if (!response.ok) throw new Error("Route request failed");
        const data = await response.json();
        const coordinates = data.routes?.[0]?.geometry?.coordinates;
        if (!Array.isArray(coordinates)) throw new Error("No route was returned");
        setNearestMemberRoute(coordinates.map(([longitude, latitude]: [number, number]) => [latitude, longitude]));
      } catch (routeError) {
        if (!controller.signal.aborted) {
          console.error("Unable to update nearest member route:", routeError);
        }
      } finally {
        if (!controller.signal.aborted) setNearestMemberRouteLoading(false);
      }
    };

    void fetchNearestMemberRoute();
    return () => controller.abort();
  }, [
    closestMember?.coordinates?.latitude,
    closestMember?.coordinates?.longitude,
    destination?.latitude,
    destination?.longitude,
    isBarangayOfficial,
  ]);

  const fetchRoute = useCallback(async (origin: Coordinates, target: Coordinates) => {
    setRouteLoading(true);
    try {
      const url = `https://router.project-osrm.org/route/v1/driving/${origin.longitude},${origin.latitude};${target.longitude},${target.latitude}?overview=full&geometries=geojson`;
      const response = await fetch(url);
      if (!response.ok) throw new Error("Route request failed");
      const data = await response.json();
      const coordinates = data.routes?.[0]?.geometry?.coordinates;
      if (!Array.isArray(coordinates)) throw new Error("No route was returned");
      setRoute(coordinates.map(([longitude, latitude]: [number, number]) => [latitude, longitude]));
      lastRoutedLocation.current = origin;
    } catch (routeError) {
      console.error("Unable to update incident route:", routeError);
      setMessage("Live location is active, but the route could not be updated.");
    } finally {
      setRouteLoading(false);
    }
  }, []);

  const handlePosition = useCallback((position: GeolocationPosition) => {
    const next = { latitude: position.coords.latitude, longitude: position.coords.longitude };
    setResponder(next);

    if (isBarangayMember) {
      setTrackingState("tracking");
      setMessage("Your current location is shared while you are signed in and the member portal is open.");
    } else {
      setTrackingState("tracking");
      setMessage("Live location is active");
    }

    if (destination && (!lastRoutedLocation.current || distanceInMeters(lastRoutedLocation.current, next) >= ROUTE_REFRESH_DISTANCE_METERS)) {
      void fetchRoute(next, destination);
    }
  }, [destination, fetchRoute, isBarangayMember]);

  const stopTracking = useCallback(() => {
    if (watchId.current !== null) navigator.geolocation.clearWatch(watchId.current);
    if (heartbeatId.current !== null) window.clearInterval(heartbeatId.current);
    watchId.current = null;
    heartbeatId.current = null;
    setTrackingState("stopped");
    setMessage("Live tracking is paused.");
  }, []);

  useEffect(() => {
    if (!destination) return;
    if (!shouldTrackCurrentLocation) {
      setResponder(null);
      setRoute([]);
      lastRoutedLocation.current = null;
      if (isBarangayOfficial) {
        if (areOnDutyMembersLoading) {
          setTrackingState("requesting");
          setMessage("Checking for on-duty members…");
        } else if (onDutyMembersError) {
          setTrackingState("error");
          setMessage("Unable to check on-duty members. Your location was not requested.");
        } else {
          setTrackingState("tracking");
          setMessage("On-duty members are shown. Your location is not being requested.");
        }
      }
      return;
    }

    if (!navigator.geolocation) {
      setTrackingState("unavailable");
      setMessage("This browser does not support location access. Live tracking requires device location.");
      return;
    }

    let isActive = true;
    const handleError = (positionError: GeolocationPositionError) => {
      if (!isActive) return;
      if (positionError.code === positionError.PERMISSION_DENIED) {
        setTrackingState("denied");
        setMessage("Location access is required for live tracking. Allow location access in your browser settings and try again.");
      } else if (positionError.code === positionError.POSITION_UNAVAILABLE) {
        setTrackingState("unavailable");
        setMessage("Location services are unavailable. Enable your device location services and try again.");
      } else {
        setTrackingState("error");
        setMessage("We could not obtain your current location. Check location services and try again.");
      }
    };
    const handleActivePosition = (position: GeolocationPosition) => {
      if (isActive) handlePosition(position);
    };

    navigator.geolocation.getCurrentPosition(handleActivePosition, handleError, { enableHighAccuracy: true, timeout: 15000, maximumAge: 5000 });
    watchId.current = navigator.geolocation.watchPosition(handleActivePosition, handleError, { enableHighAccuracy: true, timeout: 15000, maximumAge: 5000 });
    heartbeatId.current = window.setInterval(() => {
      navigator.geolocation.getCurrentPosition(handleActivePosition, handleError, {
        enableHighAccuracy: true,
        timeout: 15000,
        maximumAge: 5000,
      });
    }, DEVICE_LOCATION_REFRESH_INTERVAL_MS);
    return () => {
      if (watchId.current !== null) navigator.geolocation.clearWatch(watchId.current);
      if (heartbeatId.current !== null) window.clearInterval(heartbeatId.current);
      watchId.current = null;
      heartbeatId.current = null;
      isActive = false;
    };
  }, [
    areOnDutyMembersLoading,
    destination,
    handlePosition,
    isBarangayOfficial,
    onDutyMembers.length,
    onDutyMembersError,
    shouldTrackCurrentLocation,
    trackingAttempt,
  ]);

  if (isLoading) return <LoadingIndicator />;
  if (error || !incident || !destination) return <div className="flex min-h-screen items-center justify-center p-6 text-center text-red-700">Unable to load this incident.</div>;

  const currentLocation = shouldTrackCurrentLocation ? responder : null;
  const distance = currentLocation ? distanceInMeters(currentLocation, destination) : null;
  const initialCenter: LatLngExpression = currentLocation ? [currentLocation.latitude, currentLocation.longitude] : [destination.latitude, destination.longitude];
  const canRetry = shouldTrackCurrentLocation && trackingState !== "tracking" && trackingState !== "requesting";
  const canFitMap = trackingState !== "requesting" && (!isBarangayOfficial || !areOnDutyMembersLoading);
  const showResponderOnMap = shouldTrackCurrentLocation;

  const retryTracking = () => {
    setTrackingState("requesting");
    setMessage("Requesting access to your device location…");
    setTrackingAttempt((attempt) => attempt + 1);
  };

  return (
    <div className="fixed inset-0 z-[3000] bg-slate-100">
      <MapContainer center={initialCenter} zoom={15} minZoom={2} maxZoom={19} className="h-full w-full">
        <TileLayer
          url={satellite ? "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}" : "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"}
          attribution={satellite ? "Tiles © Esri" : "&copy; OpenStreetMap contributors"}
        />
        {canFitMap && <MapViewport responder={showResponderOnMap ? responder : null} incident={destination} members={onDutyLocations.flatMap(({ coordinates, freshness }) => coordinates && freshness >= 0 && freshness <= LOCATION_FRESHNESS_LIMIT_MS ? [coordinates] : [])} mapRef={mapRef} />}
        {currentLocation && showResponderOnMap && <Marker position={[currentLocation.latitude, currentLocation.longitude]} icon={responderIcon} />}
        <Marker position={[destination.latitude, destination.longitude]} />
        {isBarangayOfficial && nearestMemberRoute.length > 0 && (
          <Polyline positions={nearestMemberRoute} pathOptions={{ color: "#dc2626", weight: 5, opacity: 0.85 }} />
        )}
        {isBarangayOfficial && membersByDistance.map(({ member, coordinates, distance, isFresh }) => coordinates && isFresh && (
          <Marker key={member.id} position={[coordinates.latitude, coordinates.longitude]} icon={getOnDutyMemberIcon(member.name)}>
            <Popup>
              <strong>{member.name}</strong>
              <br />
              {member.position}
              {distance !== null && <><br />{formatDistance(distance)} from incident</>}
            </Popup>
          </Marker>
        ))}
        {route.length > 0 && showResponderOnMap && <Polyline positions={route} pathOptions={{ color: "#dc2626", weight: 5, opacity: 0.85 }} />}
      </MapContainer>
      <style>{".leaflet-div-icon.on-duty-member-location-marker{background:transparent;border:0}"}</style>

      <div className="absolute left-4 top-4 z-[1000] flex w-[min(92vw,420px)] flex-col gap-3">
        <div className="flex items-start gap-3 rounded-xl bg-white/95 p-3 shadow-lg backdrop-blur">
          <button type="button" onClick={() => navigate(-1)} className="rounded-lg p-2 text-slate-700 hover:bg-slate-100" aria-label="Back">
            <ArrowLeft size={20} />
          </button>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-slate-900">{incident.title}</p>
            <p className={`mt-1 text-xs ${trackingState === "tracking" ? "text-green-700" : "text-amber-700"}`}>{message}</p>
            {distance !== null && <p className="mt-1 text-sm font-semibold text-slate-900">Distance: {formatDistance(distance)}</p>}
          </div>
        </div>

        {isBarangayOfficial && (
        <div className="max-h-[38vh] overflow-y-auto rounded-xl bg-white/95 p-3 shadow-lg backdrop-blur">
          <h2 className="text-sm font-semibold text-slate-900">Members currently on duty</h2>
          <p className="mt-1 text-xs text-slate-500">Positions refresh every 60 seconds. Stale positions are not shown as live markers.</p>
          {areOnDutyMembersLoading ? (
            <p className="mt-2 text-xs text-slate-600">Loading on-duty members…</p>
          ) : onDutyMembersError ? (
            <p className="mt-2 text-xs text-red-700">On-duty member locations could not be loaded.</p>
          ) : membersByDistance.length === 0 ? (
            <p className="mt-2 text-xs text-slate-600">No members are currently on duty.</p>
          ) : (
            <ul className="mt-2 space-y-2">
              {membersByDistance.map(({ member, coordinates, distance, isFresh, freshness }, index) => (
                <li key={member.id} className="flex items-start justify-between gap-3 border-t border-slate-100 pt-2 text-xs">
                  <span className="font-medium text-slate-800">
                    {member.name} <span className="font-normal text-slate-500">({member.position})</span>
                    {index === 0 && distance !== null && <span className="ml-1 text-green-700">Closest</span>}
                    {isFresh && <span className="ml-1 text-green-700">Live</span>}
                  </span>
                  <span className="shrink-0 text-slate-600">
                    {distance !== null
                      ? formatDistance(distance)
                      : !coordinates
                        ? "Location unavailable"
                        : !Number.isFinite(freshness)
                          ? "Timestamp unavailable"
                          : freshness > LOCATION_FRESHNESS_LIMIT_MS
                          ? "Location stale"
                          : "Clock is ahead"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
        )}
      </div>

      <div className="absolute bottom-5 right-4 z-[1000] flex flex-col gap-2">
        <button type="button" onClick={() => setSatellite((value) => !value)} className="rounded-full bg-white p-3 shadow-lg" aria-label="Toggle satellite map">
          <Satellite size={20} />
        </button>
        {showResponderOnMap && <button type="button" onClick={() => responder && mapRef.current?.setView([responder.latitude, responder.longitude], 17)} disabled={!responder} className="rounded-full bg-white p-3 shadow-lg disabled:opacity-50" aria-label="Recenter on responder">
          <LocateFixed size={20} />
        </button>}
        {shouldTrackCurrentLocation && trackingState === "tracking" ? (
          <button type="button" onClick={stopTracking} className="flex items-center gap-2 rounded-full bg-red-600 px-4 py-3 text-sm font-semibold text-white shadow-lg">
            <StopCircle size={18} /> Stop tracking
          </button>
        ) : canRetry ? (
          <button type="button" onClick={retryTracking} className="flex items-center gap-2 rounded-full bg-blue-600 px-4 py-3 text-sm font-semibold text-white shadow-lg">
            <Navigation size={18} /> Try again
          </button>
        ) : null}
      </div>
      {(routeLoading || nearestMemberRouteLoading) && (
        <div className="absolute bottom-5 left-4 z-[1000] rounded-full bg-white/95 px-3 py-2 text-xs text-slate-700 shadow">
          Updating {nearestMemberRouteLoading ? "nearest member route" : "route"}…
        </div>
      )}
    </div>
  );
};

export default IncidentTrackingPage;
