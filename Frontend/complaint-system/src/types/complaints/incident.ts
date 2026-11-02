import type { Category } from "../general/category";
import type { BarangayData } from "../barangay/barangayAccount";
import type { ComplaintCluster } from "./complaintCluster";
import type { ResponseData } from "./response";

export interface Incident {
  id: number;
  title: string;
  description: string;
  barangay_id: number;
  category_id: number;
  severity_level: string;
  status: string;
  complaint_count: number;
  severity_score: number;
  first_reported_at: Date;
  last_reported_at: Date;
  category: Category;
  barangay: BarangayData;
  complaint_clusters: ComplaintCluster[];
  has_new_complaints?: boolean;
  new_complaint_count?: number;
  longitude: number;
  latitude: number;
  hearing_date?: string | null;
  hearing_count?: number | null;
  is_hearing_successful?: boolean | null;
  is_resolvable?: boolean | null;
  responses?: ResponseData[];
}