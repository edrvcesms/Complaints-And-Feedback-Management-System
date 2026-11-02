import { usersApi } from "../axios/apiServices";

export interface UserLocationUpdateResponse {
  message: string;
  location_updated_at: string;
}

export const updateCurrentUserLocation = (
  latitude: number,
  longitude: number,
): Promise<UserLocationUpdateResponse> =>
  usersApi.put("/update-current-location", {
    latitude: String(latitude),
    longitude: String(longitude),
  });
