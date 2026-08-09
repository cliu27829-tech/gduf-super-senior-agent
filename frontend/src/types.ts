export type User = {
  id: string;
  email: string;
  username: string;
  nickname: string;
  role: "user" | "admin";
  campus_id: string | null;
  grade: string;
  major: string;
  preferred_name: string;
  address_style: "同学" | "师弟" | "师妹" | "兄弟" | "名字";
  preferred_location_id: string | null;
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
  coordinate_source: string;
  coordinate_accuracy: "exact" | "approximate" | "area_only" | "unknown";
  coordinate_verified_at: string | null;
  coordinate_verified_by: string;
  coordinate_note: string;
  amap_poi_id: string;
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
  location: Location | null;
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
  location_id: string | null;
  course: string;
  task_type: string;
  materials: string[];
  submission_target: string;
  submission_method: string;
  file_naming: string;
  conditions: string[];
  evidence_requirements: string[];
  is_expired: boolean;
  source_title: string;
  source_text: string;
  source_url: string;
  status: "pending" | "completed";
  needs_confirmation: boolean;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type Reminder = {
  id: string;
  user_id: string;
  task_id: string | null;
  note_id: string | null;
  location_id: string | null;
  location_name: string;
  title: string;
  body: string;
  remind_at: string;
  timezone: "Asia/Shanghai";
  repeat_rule: string;
  status: "scheduled" | "triggered" | "dismissed" | "completed" | "cancelled";
  channels: ("in_app" | "browser")[];
  created_at: string;
  updated_at: string;
  triggered_at: string | null;
  dismissed_at: string | null;
};

export type Note = {
  id: string;
  user_id: string;
  title: string;
  content: string;
  tags: string[];
  pinned: boolean;
  source_message_id: string | null;
  created_at: string;
  updated_at: string;
};

export type CampusProcess = {
  id: string;
  campus_id: string | null;
  title: string;
  category: string;
  steps: { order?: number; text?: string; title?: string }[];
  materials: string[];
  contact: string;
  audience: string;
  location: string;
  opening_hours: string;
  online_url: string;
  notes: string;
  verification_status: string;
  verified_at: string | null;
  confidence: number;
  data_status: string;
  is_active: boolean;
  source: Source | null;
};

export type NotificationNotice = {
  title: string;
  notice_date_text: string;
  notice_date: string | null;
  publisher: string;
  campuses: string[];
  audience: string[];
  category: string;
  summary: string;
};

export type NotificationActionItem = {
  title: string;
  action: string;
  audience: string[];
  conditions: string[];
  deadline_text: string;
  deadline: string | null;
  location: string;
  materials: string[];
  evidence_requirements: string[];
  submission_target: string;
  submission_method: string;
  file_naming: string;
  notes: string[];
  source_text: string;
  source_title: string;
  source_url: string;
  needs_confirmation: boolean;
  is_expired: boolean;
  confidence: number;
  date_explanation: string;
};

export type NotificationParseResult = {
  notice: NotificationNotice;
  rules: string[];
  action_items: NotificationActionItem[];
  deadlines: {
    text: string;
    deadline: string | null;
    action_title: string;
    is_expired: boolean;
    needs_confirmation: boolean;
  }[];
  warnings: string[];
  extraction_mode: "llm" | "rules" | "none";
};

export type KnowledgeSource = {
  id: string;
  campus_id: string | null;
  title: string;
  publisher: string;
  url: string;
  visibility: "private" | "public";
  review_status: string;
  source_type: string;
  original_filename: string;
  content_hash: string;
  chunk_count: number;
  extracted_metadata: Record<string, unknown>;
  data_status: string;
  content?: string;
  created_at: string;
  updated_at: string;
};

export type ImportResult = {
  job_id: string;
  imported: number;
  duplicates: number;
  failed: number;
  document_ids: string[];
  errors: string[];
};

export type KnowledgeSearchResult = {
  document_id: string;
  title: string;
  snippet: string;
  score: number;
  publisher: string;
  url: string;
  visibility: "private" | "public";
  source_type: string;
  created_at: string;
};
