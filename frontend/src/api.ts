export type Status = "OK" | "MISMATCH" | "NEEDS_REVIEW" | null;

export interface EmailSummary {
  email_id: string;
  from: string;
  subject: string;
  body_snippet: string;
  category: string;
  status: Status;
  attachment_count: number;
  formats: string[];
}

export interface EmailRecord {
  email_id: string;
  from: string;
  subject: string;
  body: string;
  category: string;
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
  categories: Record<string, number>;
  statuses: Record<Exclude<Status, null>, number>;
}

export interface EmailListResult {
  emails: EmailSummary[];
  total: number;
}

async function request<T>(path: string): Promise<{ data: T; response: Response }> {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`Request failed (${response.status})`);
  }
  return { data: (await response.json()) as T, response };
}

export const api = {
  async counts(): Promise<EmailCounts> {
    return (await request<EmailCounts>("/api/emails/counts")).data;
  },
  async emails(options: { category?: string; query?: string; page: number; pageSize: number }): Promise<EmailListResult> {
    const parameters = new URLSearchParams({ page: String(options.page), page_size: String(options.pageSize) });
    if (options.category) parameters.set("category", options.category);
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
};
