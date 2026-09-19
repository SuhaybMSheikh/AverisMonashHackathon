import { FormEvent, KeyboardEvent, useEffect, useMemo, useState } from "react";

import { api, DocumentPreview, DocumentSummary, EmailCounts, EmailRecord, EmailSummary, Status } from "./api";

const PAGE_SIZE = 50;
const categoryLabels: Array<[string, string]> = [
  ["BL_COMPARISON", "BL comparison"],
  ["SI_REQUEST", "SI request"],
  ["INVOICE_QUERY", "Invoice query"],
  ["GENERAL", "General"],
  ["SPAM", "Spam"],
];

type Route = { kind: "inbox"; category?: string } | { kind: "email"; emailId: string };
type LoadState<T> = { data: T | null; loading: boolean; error: string | null };

function routeFromLocation(): Route {
  const segments = window.location.pathname.split("/").filter(Boolean);
  if (segments[0] === "email" && segments[1]) return { kind: "email", emailId: decodeURIComponent(segments[1]) };
  if (segments[0] === "category" && segments[1]) return { kind: "inbox", category: decodeURIComponent(segments[1]) };
  return { kind: "inbox" };
}

function statusClass(status: Status): string {
  return status ? `status-${status.toLowerCase()}` : "status-pending";
}

function attachmentIcon(format: string): string {
  return ({ ".pdf": "PDF", ".docx": "DOCX", ".xlsx": "XLSX", ".txt": "TXT" } as Record<string, string>)[format] ?? "FILE";
}

function formatBytes(size?: number): string {
  if (size === undefined) return "Unknown size";
  if (size < 1024) return `${size} B`;
  return `${(size / 1024).toFixed(size < 10 * 1024 ? 1 : 0)} KB`;
}

function PanelState({ label, state }: { label: string; state: LoadState<unknown> }) {
  if (state.loading) return <p className="panel-state">Loading {label}…</p>;
  if (state.error) return <p className="panel-state panel-error">Could not load {label}: {state.error}</p>;
  return null;
}

export function App() {
  const [route, setRoute] = useState<Route>(routeFromLocation);
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [page, setPage] = useState(1);
  const [counts, setCounts] = useState<LoadState<EmailCounts>>({ data: null, loading: true, error: null });
  const [list, setList] = useState<LoadState<{ emails: EmailSummary[]; total: number }>>({ data: null, loading: true, error: null });
  const [detail, setDetail] = useState<LoadState<{ email: EmailRecord; documents: DocumentSummary[] }>>({ data: null, loading: false, error: null });
  const [activeIndex, setActiveIndex] = useState(-1);

  const selectedCategory = route.kind === "inbox" ? route.category : undefined;
  const totalPages = Math.max(1, Math.ceil((list.data?.total ?? 0) / PAGE_SIZE));

  function navigate(path: string) {
    window.history.pushState({}, "", path);
    setRoute(routeFromLocation());
  }

  useEffect(() => {
    const onPopState = () => setRoute(routeFromLocation());
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    let cancelled = false;
    setCounts({ data: null, loading: true, error: null });
    api.counts().then(
      (data) => !cancelled && setCounts({ data, loading: false, error: null }),
      (error: Error) => !cancelled && setCounts({ data: null, loading: false, error: error.message }),
    );
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setList({ data: null, loading: true, error: null });
    api.emails({ category: selectedCategory, query: submittedQuery, page, pageSize: PAGE_SIZE }).then(
      (data) => {
        if (!cancelled) {
          setList({ data, loading: false, error: null });
          setActiveIndex(-1);
        }
      },
      (error: Error) => !cancelled && setList({ data: null, loading: false, error: error.message }),
    );
    return () => {
      cancelled = true;
    };
  }, [page, selectedCategory, submittedQuery]);

  useEffect(() => {
    if (route.kind !== "email") {
      setDetail({ data: null, loading: false, error: null });
      return;
    }
    let cancelled = false;
    setDetail({ data: null, loading: true, error: null });
    Promise.all([api.email(route.emailId), api.documents(route.emailId)]).then(
      ([email, documents]) => !cancelled && setDetail({ data: { email, documents }, loading: false, error: null }),
      (error: Error) => !cancelled && setDetail({ data: null, loading: false, error: error.message }),
    );
    return () => {
      cancelled = true;
    };
  }, [route]);

  useEffect(() => {
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return;
      const emails = list.data?.emails ?? [];
      if (event.key === "Escape" && route.kind === "email") {
        event.preventDefault();
        navigate("/");
      }
      if ((event.key === "ArrowDown" || event.key === "ArrowUp") && emails.length) {
        event.preventDefault();
        const nextIndex = event.key === "ArrowDown"
          ? Math.min(emails.length - 1, activeIndex + 1)
          : Math.max(0, activeIndex - 1);
        setActiveIndex(nextIndex);
        navigate(`/email/${encodeURIComponent(emails[nextIndex].email_id)}`);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [activeIndex, list.data, route.kind]);

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    setPage(1);
    setSubmittedQuery(query.trim());
  }

  const heading = useMemo(() => {
    if (selectedCategory) return categoryLabels.find(([value]) => value === selectedCategory)?.[1] ?? selectedCategory;
    return submittedQuery ? `Search: “${submittedQuery}”` : "All emails";
  }, [selectedCategory, submittedQuery]);

  return (
    <main className="app-shell">
      <aside className="sidebar" aria-label="Inbox sections">
        <div className="brand-row">
          <div>
            <p className="eyebrow">Averis × Monash</p>
            <h1>Document desk</h1>
          </div>
          <button className="icon-button" onClick={() => setTheme(theme === "light" ? "dark" : "light")} aria-label="Toggle colour theme">
            {theme === "light" ? "◐" : "◑"}
          </button>
        </div>
        <button className={`nav-item ${!selectedCategory ? "selected" : ""}`} onClick={() => navigate("/")}>
          <span>All</span><strong>{counts.data?.all ?? "—"}</strong>
        </button>
        <PanelState label="counts" state={counts} />
        <div className="nav-section">
          {categoryLabels.map(([value, label]) => (
            <div key={value}>
              <button className="nav-item placeholder" disabled title="Available after classification in Phase 5">
                <span>{label}</span><strong>{counts.data?.categories[value] ?? 0}</strong>
              </button>
              {value === "BL_COMPARISON" && (
                <div className="subfilters" aria-label="BL comparison status filters">
                  {(["MISMATCH", "NEEDS_REVIEW", "OK"] as const).map((status) => (
                    <button key={status} className={`subfilter placeholder ${statusClass(status)}`} disabled>
                      <span>{status === "NEEDS_REVIEW" ? "Needs review" : status[0] + status.slice(1).toLowerCase()}</span>
                      <strong>{counts.data?.statuses[status] ?? 0}</strong>
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
        <p className="sidebar-note">Classification and comparison filters unlock in later phases.</p>
      </aside>

      <section className="email-list-panel" aria-label="Email list">
        <div className="list-header">
          <div><p className="eyebrow">Inbox</p><h2>{heading}</h2></div>
          <span className="count-label">{list.data?.total ?? "—"}</span>
        </div>
        <form className="search-form" onSubmit={submitSearch}>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search sender, subject, or body" aria-label="Search emails" />
          <button type="submit">Search</button>
        </form>
        <PanelState label="emails" state={list} />
        {!list.loading && !list.error && list.data?.emails.length === 0 && <p className="panel-state">No emails match this filter.</p>}
        <div className="email-scroll" role="list">
          {list.data?.emails.map((email, index) => (
            <EmailCard
              key={email.email_id}
              email={email}
              active={route.kind === "email" && route.emailId === email.email_id}
              keyboardActive={activeIndex === index}
              onSelect={() => {
                setActiveIndex(index);
                navigate(`/email/${encodeURIComponent(email.email_id)}`);
              }}
            />
          ))}
        </div>
        <div className="pagination" aria-label="Email list pages">
          <button disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
          <span>Page {page} of {totalPages}</span>
          <button disabled={page >= totalPages} onClick={() => setPage(page + 1)}>Next</button>
        </div>
      </section>

      <section className="detail-panel" aria-label="Email viewer">
        {route.kind !== "email" && <Welcome />}
        {route.kind === "email" && <PanelState label="email" state={detail} />}
        {detail.data && <EmailDetail email={detail.data.email} documents={detail.data.documents} onClose={() => navigate("/")} />}
      </section>
    </main>
  );
}

function EmailCard({ email, active, keyboardActive, onSelect }: { email: EmailSummary; active: boolean; keyboardActive: boolean; onSelect: () => void }) {
  return (
    <button className={`email-card ${active ? "selected" : ""} ${keyboardActive ? "keyboard-active" : ""}`} onClick={onSelect} role="listitem">
      <div className="card-topline"><span className="sender">{email.from}</span><span className="attachment-total">{email.attachment_count || ""}</span></div>
      <strong className="subject">{email.subject || "(no subject)"}</strong>
      <p className="snippet">{email.body_snippet || "No message body"}</p>
      <div className="card-footer">
        <span className="category-badge">{email.category.replaceAll("_", " ")}</span>
        <span className="format-icons">{email.formats.map((format) => <span title={format} key={format}>{attachmentIcon(format)}</span>)}</span>
      </div>
    </button>
  );
}

function Welcome() {
  return <div className="welcome"><p className="eyebrow">Email viewer</p><h2>Select an email</h2><p>Choose a card to read the original message. Use ↑ and ↓ to move through this page of results.</p></div>;
}

function EmailDetail({ email, documents, onClose }: { email: EmailRecord; documents: DocumentSummary[]; onClose: () => void }) {
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(documents[0]?.doc_id ?? null);

  useEffect(() => {
    if (!documents.some((document) => document.doc_id === selectedDocumentId)) {
      setSelectedDocumentId(documents[0]?.doc_id ?? null);
    }
  }, [documents, selectedDocumentId]);

  const selectedDocument = documents.find((document) => document.doc_id === selectedDocumentId) ?? null;
  return (
    <article className="email-detail">
      <div className="detail-actions"><button className="back-button" onClick={onClose}>← Inbox</button><span className={`status-badge ${statusClass(email.status)}`}>{email.status ?? "Pending review"}</span></div>
      <p className="eyebrow">{email.email_id}</p>
      <h2>{email.subject || "(no subject)"}</h2>
      <p className="from-line"><span>From</span>{email.from}</p>
      <div className="email-body" aria-label="Email body"><pre>{email.body}</pre></div>
      <section className="attachments-section">
        <div><p className="eyebrow">Attachments</p><h3>{documents.length ? `${documents.length} file${documents.length === 1 ? "" : "s"}` : "No attachments"}</h3></div>
        {documents.length > 0 && <ul>{documents.map((document) => <li key={document.doc_id}><button className={`attachment-button ${document.doc_id === selectedDocumentId ? "selected" : ""}`} onClick={() => setSelectedDocumentId(document.doc_id)} aria-pressed={document.doc_id === selectedDocumentId}><span className="file-chip">{attachmentIcon(document.ext)}</span><span>{document.path?.split("/").at(-1) ?? document.doc_id}</span><small>{document.role_hint ?? "Unknown role"}</small></button></li>)}</ul>}
      </section>
      {selectedDocument && <DocPanel document={selectedDocument} />}
    </article>
  );
}

function DocPanel({ document }: { document: DocumentSummary }) {
  const [tab, setTab] = useState<"formatted" | "original">("formatted");
  const [preview, setPreview] = useState<LoadState<DocumentPreview>>({ data: null, loading: true, error: null });

  useEffect(() => {
    let cancelled = false;
    setTab("formatted");
    setPreview({ data: null, loading: true, error: null });
    api.preview(document.doc_id).then(
      (data) => !cancelled && setPreview({ data, loading: false, error: null }),
      (error: Error) => !cancelled && setPreview({ data: null, loading: false, error: error.message }),
    );
    return () => { cancelled = true; };
  }, [document.doc_id]);

  const filename = document.path?.split("/").at(-1) ?? document.doc_id;
  const downloadUrl = `/api/documents/${encodeURIComponent(document.doc_id)}/original?download=1`;
  const current = preview.data;

  return (
    <section className="doc-panel" aria-label={`Attachment preview for ${filename}`}>
      <div className="doc-header">
        <div><p className="eyebrow">Attachment preview</p><h3>{filename}</h3></div>
        <a className="download-link" href={downloadUrl}>Download original</a>
      </div>
      <div className="doc-meta">
        <span>{attachmentIcon(document.ext)}</span><span>{formatBytes(document.size)}</span><span>{document.role_hint ?? "Unknown role"}</span>
        {current?.metadata && Object.entries(current.metadata).map(([key, value]) => <span key={key}>{key.replaceAll("_", " ")}: {String(value).replaceAll("_", " ")}</span>)}
      </div>
      <PanelState label="attachment" state={preview} />
      {current?.error && <div className="unreadable-card"><h4>This file cannot be opened</h4><p>{current.detail}</p><a className="download-link" href={downloadUrl}>Download original</a></div>}
      {current && !current.error && <>
        <div className="doc-tabs" role="tablist" aria-label="Document views">
          <button role="tab" aria-selected={tab === "formatted"} className={tab === "formatted" ? "selected" : ""} onClick={() => setTab("formatted")}>Formatted</button>
          <button role="tab" aria-selected={tab === "original"} className={tab === "original" ? "selected" : ""} onClick={() => setTab("original")}>Original</button>
        </div>
        {tab === "formatted" ? <FormattedPreview preview={current} /> : <OriginalPreview preview={current} />}
      </>}
    </section>
  );
}

function FormattedPreview({ preview }: { preview: DocumentPreview }) {
  const fields = preview.fields ?? [];
  if (!fields.length && preview.metadata?.classification === "scan") {
    return <p className="preview-note">This PDF is a scan with no embedded text. Its page images are available in Original.</p>;
  }
  if (!fields.length) return <p className="preview-note">No label/value rows were found. Choose Original to inspect the source content.</p>;
  return <div className="formatted-table-wrap"><table className="formatted-table"><thead><tr><th>Label</th><th>Value</th></tr></thead><tbody>{fields.map((field, index) => <tr key={`${field.label}-${index}`}><th>{field.label}</th><td>{field.value}</td></tr>)}</tbody></table></div>;
}

function OriginalPreview({ preview }: { preview: DocumentPreview }) {
  const original = preview.original;
  if (!original) return null;
  if (original.kind === "text") return <pre className="original-text">{original.text}</pre>;
  if (original.kind === "grid") return <div className="formatted-table-wrap"><table className="formatted-table original-grid"><thead><tr>{original.columns?.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{original.rows?.map((row, rowIndex) => <tr key={rowIndex}>{row.map((value, columnIndex) => <td key={columnIndex}>{value}</td>)}</tr>)}</tbody></table></div>;
  if (original.kind === "document") return <div className="word-preview">{original.paragraphs?.map((paragraph, index) => <p key={index}>{paragraph}</p>)}{original.tables?.map((table, tableIndex) => <div className="formatted-table-wrap" key={tableIndex}><table className="formatted-table"><tbody>{table.map((row, rowIndex) => <tr key={rowIndex}>{row.map((value, columnIndex) => <td key={columnIndex}>{value}</td>)}</tr>)}</tbody></table></div>)}</div>;
  if (original.kind === "page_images") return <div className="pdf-pages">{original.pages?.map((page, index) => <figure key={page}><img src={page} alt={`Page ${index + 1} of ${preview.filename}`} /><figcaption>Page {index + 1}</figcaption></figure>)}</div>;
  return null;
}
