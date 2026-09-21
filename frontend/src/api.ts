export type Status = "OK" | "MISMATCH" | "NEEDS_REVIEW" | null;

export interface EmailSummary {
  email_id: string;
  from: string;
  subject: string;
  body_snippet: string;
  category: string;
  detected_category?: string;
  category_override?: string | null;
  category_conf: number | null;
  decided_by: "rule" | "llm" | null;
  status: Status;
  review_reason: string | null;
  defect_fields: string[];
  reviewer_confirmed: boolean;
  display_meta: { route?: string | null; reference?: string | null; missing_fields?: string[]; invoice_number?: string | null; topic?: string; notice_type?: string; summary?: string; why_flagged?: string[] };
  attachment_count: number;
  formats: string[];
}

export interface EmailRecord {
  email_id: string;
  from: string;
  subject: string;
  body: string;
  category: string;
  detected_category?: string;
  category_override?: string | null;
  category_conf?: number | null;
  category_reasons?: string | null;
  decided_by?: "rule" | "llm" | null;
  status: Status;
  documents: DocumentSummary[];
}

export interface DocumentSummary {
  doc_id: string;
  path?: string;
  ext: string;
  size?: number;
  sha256?: string;
  role_hint: string | null;
  role_detected?: string | null;
  convert_status: string | null;
}

export interface PreviewField {
  label: string;
  value: string;
}

export interface DocumentPreview {
  doc_id: string;
  filename: string;
  format: string;
  size: number;
  role_hint: string | null;
  error?: "unreadable";
  detail?: string;
  fields?: PreviewField[];
  metadata?: Record<string, string | number>;
  original?: {
    kind: "text" | "grid" | "document" | "page_images";
    text?: string;
    columns?: string[];
    rows?: string[][];
    paragraphs?: string[];
    tables?: string[][][];
    pages?: string[];
  };
}

export interface EmailCounts {
  all: number;
  uncertain: number;
  run_issues: number;
  categories: Record<string, number>;
  statuses: Record<Exclude<Status, null>, number>;
}

export interface EmailListResult {
  emails: EmailSummary[];
  total: number;
}

export interface FieldComparison {
  field: string;
  si_raw: string | null;
  bl_raw: string | null;
  si_norm: string | null;
  bl_norm: string | null;
  equal: boolean;
  diff_kind: "equal" | "format_only" | "value";
  confidence: number;
  severity?: "high";
  si_reviewed?: boolean;
  bl_reviewed?: boolean;
  si_original_raw?: string | null;
  bl_original_raw?: string | null;
  bl_diff_segments?: Array<{ text: string; changed: boolean }>;
  review_side?: "SI" | "BL" | "BOTH" | null;
}

export interface ReviewRecord {
  id: number;
  doc_role: "SI" | "BL";
  field: string;
  value: string | null;
  reviewer: string;
  note: string;
  disposition: "confirmed" | "cannot_determine" | "unreadable";
  created_at: string;
}

export interface ReviewContext {
  doc_id: string;
  doc_role: "SI" | "BL";
  convert_status: string;
  text_path: string | null;
  field: string | null;
  raw: string | null;
  normalized: string | null;
  line_no: number | null;
  confidence: number | null;
  status: string | null;
  source_text_url: string | null;
  source_page_url: string | null;
}

export interface ReviewQueueItem {
  email_id: string;
  from_addr: string;
  subject: string;
  status: "NEEDS_REVIEW";
  review_reason: Comparison["review_reason"];
  field_results: FieldComparison[];
  computed_at: string;
}

export interface BodyField {
  field: string;
  raw: string | null;
  normalized: string | null;
  line_no: number | null;
  status: string;
}

export interface StageRun {
  email_id: string;
  stage: "convert" | "classify" | "extract" | "compare";
  state: "pending" | "running" | "ok" | "failed" | "needs_review";
  error: string | null;
  duration_ms: number | null;
  updated_at: string;
  from_addr: string;
  subject: string;
}

export interface Comparison {
  email_id: string;
  status: Exclude<Status, null>;
  review_reason: "missing_attachment" | "unreadable" | "wrong_doc_type" | "missing_value" | null;
  has_defect: boolean;
  defect_fields: string[];
  field_results: FieldComparison[];
  explanations: string[];
  reviews: ReviewRecord[];
}

async function request<T>(path: string): Promise<{ data: T; response: Response }> {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`Request failed (${response.status})`);
  }
  return { data: (await response.json()) as T, response };
}

async function write<T>(path: string, payload: unknown): Promise<T> {
  const response = await fetch(path, { method: "POST", headers: { Accept: "application/json", "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return response.json() as Promise<T>;
}

export const api = {
  async counts(): Promise<EmailCounts> {
    return (await request<EmailCounts>("/api/emails/counts")).data;
  },
  async emails(options: { category?: string; status?: Exclude<Status, null>; sort?: "mismatch_first"; uncertain?: boolean; query?: string; page: number; pageSize: number }): Promise<EmailListResult> {
    const parameters = new URLSearchParams({ page: String(options.page), page_size: String(options.pageSize) });
    if (options.category) parameters.set("category", options.category);
    if (options.status) parameters.set("status", options.status);
    if (options.sort) parameters.set("sort", options.sort);
    if (options.uncertain) parameters.set("uncertain", "1");
    if (options.query) parameters.set("q", options.query);
    const { data, response } = await request<EmailSummary[]>(`/api/emails?${parameters}`);
    return { emails: data, total: Number(response.headers.get("X-Total-Count") ?? data.length) };
  },
  async email(emailId: string): Promise<EmailRecord> {
    return (await request<EmailRecord>(`/api/emails/${encodeURIComponent(emailId)}`)).data;
  },
  async documents(emailId: string): Promise<DocumentSummary[]> {
    return (await request<DocumentSummary[]>(`/api/emails/${encodeURIComponent(emailId)}/documents`)).data;
  },
  async preview(documentId: string): Promise<DocumentPreview> {
    return (await request<DocumentPreview>(`/api/documents/${encodeURIComponent(documentId)}/preview`)).data;
  },
  async comparison(emailId: string): Promise<Comparison> {
    return (await request<Comparison>(`/api/emails/${encodeURIComponent(emailId)}/comparison`)).data;
  },
  async text(documentId: string): Promise<string> {
    const response = await fetch(`/api/documents/${encodeURIComponent(documentId)}/text`, { headers: { Accept: "text/plain" } });
    if (!response.ok) throw new Error(`Request failed (${response.status})`);
    return response.text();
  },
  async reviewQueue(): Promise<ReviewQueueItem[]> {
    return (await request<ReviewQueueItem[]>("/api/review-queue")).data;
  },
  async reviewContext(emailId: string): Promise<ReviewContext[]> {
    return (await request<ReviewContext[]>(`/api/emails/${encodeURIComponent(emailId)}/review-context`)).data;
  },
  async saveReview(emailId: string, review: { field: string; doc_role: "SI" | "BL"; value?: string; reviewer: string; note: string; disposition: "confirmed" | "cannot_determine" | "unreadable" }): Promise<Comparison> {
    return write<Comparison>(`/api/emails/${encodeURIComponent(emailId)}/review`, review);
  },
  async changeCategory(emailId: string, category: string): Promise<{ email_id: string; category: string; category_override: string | null }> {
    return write(`/api/emails/${encodeURIComponent(emailId)}/category`, { category });
  },
  async bodyFields(emailId: string): Promise<BodyField[]> {
    return (await request<BodyField[]>(`/api/emails/${encodeURIComponent(emailId)}/body-fields`)).data;
  },
  async runs(): Promise<StageRun[]> {
    return (await request<StageRun[]>("/api/runs?failed=1")).data;
  },
  async retry(emailId: string): Promise<unknown> {
    return write(`/api/emails/${encodeURIComponent(emailId)}/retry`, {});
  },
  async retryFailed(): Promise<{ retried: string[] }> {
    return write<{ retried: string[] }>("/api/retry-failed", {});
  },
};
