export type User = {
  id: string;
  email: string;
  username: string;
  nickname: string;
  role: "user" | "admin";
  campus_id: string | null;
  grade: string;
  major: string;
  is_active: boolean;
  created_at: string;
};

export type Campus = {
  id: string;
  slug: string;
  name: string;
  address: string;
  data_notice: string;
  is_active: boolean;
  updated_at: string;
};

export type Source = {
  id: string;
  title: string;
  url: string;
  publisher: string;
  source_type: string;
  published_at: string | null;
  fetched_at: string | null;
  verified_at: string | null;
  confidence: number;
  is_official: boolean;
};

export type Location = {
  id: string;
  campus_id: string;
  name: string;
  aliases: string[];
  category: string;
  description: string;
  address: string;
  area: string;
  floor: string;
  latitude: number | null;
  longitude: number | null;
  map_x: number | null;
  map_y: number | null;
  opening_hours: string;
  services: string[];
  verification_status: string;
  verification_method: string;
  verified_at: string | null;
  confidence: number;
  freshness_status: string;
  data_status: string;
  is_active: boolean;
  updated_at: string;
  sources: Source[];
};

export type Stall = {
  id: string;
  canteen_id: string;
  name: string;
  floor: string;
  food_type: string;
  common_items: string[];
  price_range: string;
  meal_periods: string[];
  opening_hours: string;
  payment_methods: string[];
  is_operating: boolean | null;
  verification_status: string;
  data_status: string;
  verified_at: string | null;
  confidence: number;
};

export type Canteen = {
  id: string;
  campus_id: string;
  location_id: string | null;
  name: string;
  floors: string[];
  opening_hours: string;
  payment_methods: string[];
  verification_status: string;
  data_status: string;
  verified_at: string | null;
  confidence: number;
  source: Source | null;
  stalls: Stall[];
  today_menu_available: false;
  today_menu_message: string;
};

export type Task = {
  id: string;
  title: string;
  description: string;
  deadline: string | null;
  location: string;
  course: string;
  task_type: string;
  materials: string[];
  submission_target: string;
  submission_method: string;
  file_naming: string;
  source_text: string;
  source_url: string;
  status: "pending" | "completed";
  needs_confirmation: boolean;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type NotificationDraft = {
  title: string;
  deadline: string | null;
  location: string;
  materials: string[];
  submission_target: string;
  submission_method: string;
  file_naming: string;
  notes: string;
  source_text: string;
  source_url: string;
  needs_confirmation: boolean;
  confidence: number;
  date_explanation: string;
};
