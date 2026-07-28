const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface PreviewRequest {
  image_base64?: string | null;
  mime?: "png" | "jpeg" | "webp";
  age?: number | null;
  gender?: "female" | "male" | null;
  use_fixture?: "patient_dff3abf1" | null;
}

export interface PreviewPlan {
  id: string;
  title: string;
  target_zones: string[];
  problem_summary: string;
  instruction: string;
  after_image_base64: string;
  latency_sec: number;
  status: string;
  error?: string | null;
}

export interface DiagnosisZone {
  sub_area: string;
  primary_zone?: string;
  visible_evidence?: string;
  problem_types?: string[];
  severity_level?: string;
  direction_reasoning?: string;
  priority?: string;
  safety_gate?: {
    triggered?: boolean;
    rule?: string | null;
    unblock?: string | null;
  };
  [k: string]: unknown;
}

export interface DiagnosisPayload {
  case_level_judgment?: {
    case_summary?: string;
    output_style_guidance?: string;
    main_problem_axes?: string[];
  };
  professional_assessment?: DiagnosisZone[];
  [k: string]: unknown;
}

export interface PreviewResponse {
  diagnosis: DiagnosisPayload;
  diagnosis_latency_sec: number;
  diagnosis_model: string;
  before_image_base64: string;
  plans: PreviewPlan[];
  report_markdown: string;
}

export async function generatePreview(req: PreviewRequest): Promise<PreviewResponse> {
  const res = await fetch(`${API_BASE}/api/v1/treatment-preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`treatment-preview API ${res.status}: ${text.slice(0, 200)}`);
  }
  return res.json();
}
