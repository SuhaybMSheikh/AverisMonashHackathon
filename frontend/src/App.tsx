import { FormEvent, KeyboardEvent, RefObject, UIEventHandler, useEffect, useMemo, useRef, useState } from "react";

import { api, BodyField, Comparison, DocumentPreview, DocumentSummary, EmailCounts, EmailRecord, EmailSummary, FieldComparison, ReviewContext, ReviewQueueItem, StageRun, Status } from "./api";

const PAGE_SIZE = 50;
const categoryLabels: Array<[string, string]> = [
  ["BL_COMPARISON", "BL comparison"],
  ["SI_REQUEST", "SI request"],
  ["INVOICE_QUERY", "Invoice query"],
  ["GENERAL", "General"],
  ["SPAM", "Spam"],
];

type Route = { kind: "inbox"; category?: string; status?: Exclude<Status, null>; uncertain?: boolean } | { kind: "email"; emailId: string } | { kind: "review" } | { kind: "runs" };
type LoadState<T> = { data: T | null; loading: boolean; error: string | null };

function routeFromLocation(): Route {
  const segments = window.location.pathname.split("/").filter(Boolean);
  if (segments[0] === "review") return { kind: "review" };
  if (segments[0] === "runs") return { kind: "runs" };
  if (segments[0] === "uncertain") return { kind: "inbox", uncertain: true };
  if (segments[0] === "email" && segments[1]) return { kind: "email", emailId: decodeURIComponent(segments[1]) };
  if (segments[0] === "category" && segments[1]) {
    const status = new URLSearchParams(window.location.search).get("status") as Exclude<Status, null> | null;
    return { kind: "inbox", category: decodeURIComponent(segments[1]), status: status ?? undefined };
  }
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
  const [mismatchFirst, setMismatchFirst] = useState(false);
  const [counts, setCounts] = useState<LoadState<EmailCounts>>({ data: null, loading: true, error: null });
  const [list, setList] = useState<LoadState<{ emails: EmailSummary[]; total: number }>>({ data: null, loading: true, error: null });
  const [detail, setDetail] = useState<LoadState<{ email: EmailRecord; documents: DocumentSummary[] }>>({ data: null, loading: false, error: null });
  const [activeIndex, setActiveIndex] = useState(-1);
  const [refresh, setRefresh] = useState(0);

  const selectedCategory = route.kind === "inbox" ? route.category : undefined;
  const selectedStatus = route.kind === "inbox" ? route.status : undefined;
  const selectedUncertain = route.kind === "inbox" ? route.uncertain : false;
  const totalPages = Math.max(1, Math.ceil((list.data?.total ?? 0) / PAGE_SIZE));

  function navigate(path: string) {
    window.history.pushState({}, "", path);
    setRoute(routeFromLocation());
  }

  useEffect(() => {
    const onPopState = () => setRoute(routeFromLocation());
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, [refresh]);

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
  }, [refresh]);

  useEffect(() => {
    let cancelled = false;
    setList({ data: null, loading: true, error: null });
    api.emails({ category: selectedCategory, status: selectedStatus, sort: selectedCategory === "BL_COMPARISON" && mismatchFirst ? "mismatch_first" : undefined, uncertain: selectedUncertain, query: submittedQuery, page, pageSize: PAGE_SIZE }).then(
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
  }, [page, selectedCategory, selectedStatus, selectedUncertain, submittedQuery, mismatchFirst, refresh]);

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
      if ((event.key === "n" || event.key === "p") && emails.length) {
        const mismatches = emails.map((item, index) => ({ item, index })).filter(({ item }) => item.status === "MISMATCH");
        if (!mismatches.length) return;
        event.preventDefault();
        const current = mismatches.findIndex(({ item }) => route.kind === "email" && item.email_id === route.emailId);
        const next = event.key === "n" ? Math.min(mismatches.length - 1, current + 1) : Math.max(0, current - 1);
        setActiveIndex(mismatches[next].index);
        navigate(`/email/${encodeURIComponent(mismatches[next].item.email_id)}`);
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
    return selectedUncertain ? "Uncertain classifications" : submittedQuery ? `Search: “${submittedQuery}”` : "All emails";
  }, [selectedCategory, selectedUncertain, submittedQuery]);

  return (
    <main className="app-shell">
      <aside className="sidebar" aria-label="Inbox sections">
        <div className="brand-row">
          <div>
            <p className="eyebrow">Averis × Monash</p>
            <h1>CargoCheck AI</h1>
          </div>
          <button className="icon-button" onClick={() => setTheme(theme === "light" ? "dark" : "light")} aria-label="Toggle colour theme">
            {theme === "light" ? "◐" : "◑"}
          </button>
        </div>
        <button className={`nav-item ${!selectedCategory && !selectedUncertain ? "selected" : ""}`} onClick={() => { setPage(1); navigate("/"); }}>
          <span>All</span><strong>{counts.data?.all ?? "—"}</strong>
        </button>
        <button className={`nav-item ${selectedUncertain ? "selected" : ""}`} onClick={() => { setPage(1); navigate("/uncertain"); }}><span>Uncertain</span><strong>{counts.data?.uncertain ?? "—"}</strong></button>
        <PanelState label="counts" state={counts} />
        <div className="nav-section">
          <button className={`nav-item ${route.kind === "review" ? "selected" : ""}`} onClick={() => { setPage(1); navigate("/review"); }}>
            <span>Review queue</span><strong>{counts.data?.statuses.NEEDS_REVIEW ?? "—"}</strong>
          </button>
          <button className={`nav-item ${route.kind === "runs" ? "selected" : ""}`} onClick={() => { setPage(1); navigate("/runs"); }}>
            <span>Runs & failures</span><strong>{counts.data?.run_issues ?? "—"}</strong>
          </button>
          {categoryLabels.map(([value, label]) => (
            <div key={value}>
              <button className={`nav-item ${selectedCategory === value && !selectedStatus ? "selected" : ""}`} onClick={() => { setPage(1); navigate(`/category/${value}`); }}>
                <span>{label}</span><strong>{counts.data?.categories[value] ?? 0}</strong>
              </button>
              {value === "BL_COMPARISON" && (
                <div className="subfilters" aria-label="BL comparison status filters">
                  {(["MISMATCH", "NEEDS_REVIEW", "OK"] as const).map((status) => (
                    <button key={status} className={`subfilter ${selectedStatus === status ? "selected" : ""} ${statusClass(status)}`} onClick={() => { setPage(1); navigate(`/category/BL_COMPARISON?status=${status}`); }}>
                      <span>{status === "NEEDS_REVIEW" ? "Needs review" : status[0] + status.slice(1).toLowerCase()}</span>
                      <strong>{counts.data?.statuses[status] ?? 0}</strong>
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
        <p className="sidebar-note">Categories use detected attachment roles and the email body. Status filters reflect persisted comparison results.</p>
      </aside>

      <section className="email-list-panel" aria-label="Email list">
        {route.kind === "review" ? <ReviewQueue onSelect={(emailId) => navigate(`/email/${encodeURIComponent(emailId)}`)} /> : route.kind === "runs" ? <RunsPage onSelect={(emailId) => navigate(`/email/${encodeURIComponent(emailId)}`)} onChanged={() => setRefresh((value) => value + 1)} /> : <>
        <div className="list-header">
          <div><p className="eyebrow">Inbox</p><h2>{heading}</h2></div>
          <span className="count-label">{list.data?.total ?? "—"}</span>
        </div>
        <form className="search-form" onSubmit={submitSearch}>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search sender, subject, or body" aria-label="Search emails" />
          <button type="submit">Search</button>
        </form>
        {selectedCategory === "BL_COMPARISON" && <label className="sort-control"><input type="checkbox" checked={mismatchFirst} onChange={(event) => { setPage(1); setMismatchFirst(event.target.checked); }} /> Mismatches first</label>}
        <PanelState label="emails" state={list} />
        {!list.loading && !list.error && list.data?.emails.length === 0 && <p className="panel-state">{selectedCategory ? `No ${categoryLabels.find(([value]) => value === selectedCategory)?.[1] ?? selectedCategory} emails match this filter.` : selectedUncertain ? "No uncertain classifications need review." : "No emails match this filter."}</p>}
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
        </>}
      </section>

      <section className="detail-panel" aria-label="Email viewer">
        {route.kind !== "email" && <Welcome />}
        {route.kind === "email" && <PanelState label="email" state={detail} />}
        {detail.data && <EmailDetail email={detail.data.email} documents={detail.data.documents} onClose={() => navigate("/")} onReviewSaved={() => setRefresh((value) => value + 1)} onCategoryChanged={() => setRefresh((value) => value + 1)} />}
      </section>
    </main>
  );
}

function EmailCard({ email, active, keyboardActive, onSelect }: { email: EmailSummary; active: boolean; keyboardActive: boolean; onSelect: () => void }) {
  return (
    <button className={`email-card ${email.status ? `card-${email.status.toLowerCase()}` : ""} ${email.category === "SPAM" ? "card-spam" : ""} ${active ? "selected" : ""} ${keyboardActive ? "keyboard-active" : ""}`} onClick={onSelect} role="listitem">
      <div className="card-topline"><span className="sender">{email.from}</span><span className="attachment-total">{email.attachment_count || ""}</span></div>
      <strong className="subject">{email.subject || "(no subject)"}</strong>
      <p className="snippet">{email.body_snippet || "No message body"}</p>
      {email.category === "SI_REQUEST" && <p className="card-meta">{email.display_meta.route ?? "Route not stated"}{email.display_meta.reference ? ` · ${email.display_meta.reference}` : ""}{email.display_meta.missing_fields?.length ? ` · Missing ${email.display_meta.missing_fields.map((field) => fieldLabels[field]).join(", ")}` : ""}</p>}
      {email.category === "INVOICE_QUERY" && <p className="card-meta">{email.display_meta.invoice_number ?? "Invoice number not found"} · {email.display_meta.topic ?? "Other"}</p>}
      {email.category === "GENERAL" && <p className="card-meta">{email.display_meta.notice_type ?? "Notice"}</p>}
      {email.category === "SPAM" && <p className="card-meta">Why flagged: {email.display_meta.why_flagged?.join(", ") || "Suspicious content"}</p>}
      {email.status === "MISMATCH" && <div className="card-detail-chips">{email.defect_fields.map((field) => <span key={field}>{fieldLabels[field]}</span>)}</div>}
      {email.status === "NEEDS_REVIEW" && <p className="card-reason">{email.review_reason?.replaceAll("_", " ") ?? "Review required"}</p>}
      {email.status === "OK" && <p className="card-ok-message">✓ All 7 fields match</p>}
      <div className="card-footer">
        <span className="category-badge">{email.category.replaceAll("_", " ")}</span>
        {email.status && <span className={`status-badge compact ${statusClass(email.status)}`}>{email.status === "NEEDS_REVIEW" ? "Needs review" : email.status}</span>}
        {email.reviewer_confirmed && <span className="reviewer-confirmed">Confirmed by reviewer</span>}
        {email.category_conf !== null && email.category_conf < 0.75 && <span className="uncertain-chip">Uncertain</span>}
        <span className="format-icons">{email.formats.map((format) => <span title={format} key={format}>{attachmentIcon(format)}</span>)}</span>
      </div>
    </button>
  );
}

function Welcome() {
  return <div className="welcome"><p className="eyebrow">Email viewer</p><h2>Select an email</h2><p>Choose a card to read the original message. Use ↑ and ↓ to move through this page of results.</p></div>;
}

function ReviewQueue({ onSelect }: { onSelect: (emailId: string) => void }) {
  const [queue, setQueue] = useState<LoadState<ReviewQueueItem[]>>({ data: null, loading: true, error: null });
  useEffect(() => { let cancelled = false; api.reviewQueue().then((data) => !cancelled && setQueue({ data, loading: false, error: null }), (error: Error) => !cancelled && setQueue({ data: null, loading: false, error: error.message })); return () => { cancelled = true; }; }, []);
  return <><div className="list-header"><div><p className="eyebrow">Human review</p><h2>Review queue</h2></div><span className="count-label">{queue.data?.length ?? "—"}</span></div><p className="queue-note">Unresolved cases, grouped by their recorded reason.</p><PanelState label="review queue" state={queue} /><div className="email-scroll" role="list">{queue.data?.map((item) => <button className="email-card card-needs_review" key={item.email_id} onClick={() => onSelect(item.email_id)}><div className="card-topline"><span className="sender">{item.from_addr}</span><span className="status-badge compact status-needs_review">{item.review_reason?.replaceAll("_", " ")}</span></div><strong className="subject">{item.subject || "(no subject)"}</strong><p className="snippet">{item.field_results.filter((field) => !field.equal).map((field) => fieldLabels[field.field]).join(", ") || "Inspect source evidence"}</p></button>)}</div>{queue.data?.length === 0 && <p className="panel-state">No emails need review.</p>}</>;
}

function RunsPage({ onSelect, onChanged }: { onSelect: (emailId: string) => void; onChanged: () => void }) {
  const [runs, setRuns] = useState<LoadState<StageRun[]>>({ data: null, loading: true, error: null });
  const [retrying, setRetrying] = useState<string | null>(null);
  const load = () => { setRuns({ data: null, loading: true, error: null }); api.runs().then((data) => setRuns({ data, loading: false, error: null }), (error: Error) => setRuns({ data: null, loading: false, error: error.message })); };
  useEffect(() => { load(); }, []);
  const retry = async (emailId: string) => { setRetrying(emailId); try { await api.retry(emailId); load(); onChanged(); } finally { setRetrying(null); } };
  const retryAll = async () => { setRetrying("all"); try { await api.retryFailed(); load(); onChanged(); } finally { setRetrying(null); } };
  return <><div className="list-header"><div><p className="eyebrow">Reliability</p><h2>Runs & failures</h2></div><button disabled={!runs.data?.length || retrying !== null} onClick={() => void retryAll()}>Retry all failed</button></div><p className="queue-note">Failures and unresolved model decisions are preserved with their stage and reason.</p><PanelState label="runs" state={runs} /><div className="email-scroll" role="list">{runs.data?.map((run) => <article className="run-card" key={`${run.email_id}-${run.stage}`}><div><strong>{run.stage}</strong><span className={`status-badge compact status-${run.state === "failed" ? "needs_review" : "pending"}`}>{run.state.replaceAll("_", " ")}</span><p>{run.subject || "(no subject)"}</p><small>{run.email_id} · {run.error ?? "No error detail"}</small></div><div><button onClick={() => onSelect(run.email_id)}>Open</button><button disabled={retrying !== null} onClick={() => void retry(run.email_id)}>{retrying === run.email_id ? "Retrying…" : "Retry"}</button></div></article>)}</div>{runs.data?.length === 0 && <p className="panel-state">No failed or pending stages.</p>}</>;
}

function EmailDetail({ email, documents, onClose, onReviewSaved, onCategoryChanged }: { email: EmailRecord; documents: DocumentSummary[]; onClose: () => void; onReviewSaved: () => void; onCategoryChanged: () => void }) {
  const [comparison, setComparison] = useState<LoadState<Comparison>>({ data: null, loading: email.category === "BL_COMPARISON", error: null });
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(documents[0]?.doc_id ?? null);

  useEffect(() => {
    if (!documents.some((document) => document.doc_id === selectedDocumentId)) {
      setSelectedDocumentId(documents[0]?.doc_id ?? null);
    }
  }, [documents, selectedDocumentId]);

  useEffect(() => {
    if (email.category !== "BL_COMPARISON") return;
    let cancelled = false;
    setComparison({ data: null, loading: true, error: null });
    api.comparison(email.email_id).then(
      (data) => !cancelled && setComparison({ data, loading: false, error: null }),
      (error: Error) => !cancelled && setComparison({ data: null, loading: false, error: error.message }),
    );
    return () => { cancelled = true; };
  }, [email.category, email.email_id]);

  const selectedDocument = documents.find((document) => document.doc_id === selectedDocumentId) ?? null;
  return (
    <article className="email-detail">
      <div className="detail-actions"><button className="back-button" onClick={onClose}>← Inbox</button><span className={`status-badge ${statusClass(comparison.data?.status ?? email.status)}`}>{comparison.data?.status ?? email.status ?? "Pending review"}</span></div>
      <p className="eyebrow">{email.email_id}</p>
      <h2>{email.subject || "(no subject)"}</h2>
      <p className="from-line"><span>From</span>{email.from}</p>
      <details className="email-body" open><summary>Email body</summary><pre>{email.body}</pre></details>
      <CategoryControl email={email} onChanged={onCategoryChanged} />
      {email.category === "BL_COMPARISON" && <><PanelState label="comparison" state={comparison} />{comparison.data && <ComparisonWorkspace email={email} comparison={comparison.data} documents={documents} onComparisonUpdated={(value) => { setComparison({ data: value, loading: false, error: null }); onReviewSaved(); }} />}</>}
      {email.category !== "BL_COMPARISON" && <>
      {email.category === "SI_REQUEST" && <BodyFieldTable emailId={email.email_id} />}
      <section className="attachments-section">
        <div><p className="eyebrow">Attachments</p><h3>{documents.length ? `${documents.length} file${documents.length === 1 ? "" : "s"}` : "No attachments"}</h3></div>
        {documents.length > 0 && <ul>{documents.map((document) => <li key={document.doc_id}><button className={`attachment-button ${document.doc_id === selectedDocumentId ? "selected" : ""}`} onClick={() => setSelectedDocumentId(document.doc_id)} aria-pressed={document.doc_id === selectedDocumentId}><span className="file-chip">{attachmentIcon(document.ext)}</span><span>{document.path?.split("/").at(-1) ?? document.doc_id}</span><small>{document.role_hint ?? "Unknown role"}</small></button></li>)}</ul>}
      </section>
      {selectedDocument && <DocPanel document={selectedDocument} />}
      </>}
    </article>
  );
}

function BodyFieldTable({ emailId }: { emailId: string }) {
  const [fields, setFields] = useState<LoadState<BodyField[]>>({ data: null, loading: true, error: null });
  useEffect(() => { let cancelled = false; api.bodyFields(emailId).then((data) => !cancelled && setFields({ data, loading: false, error: null }), (error: Error) => !cancelled && setFields({ data: null, loading: false, error: error.message })); return () => { cancelled = true; }; }, [emailId]);
  return <section className="body-fields"><p className="eyebrow">Shipping instruction in email body</p><h3>Parsed request fields</h3><PanelState label="body fields" state={fields} />{fields.data && <table><thead><tr><th>Field</th><th>Value</th><th>State</th></tr></thead><tbody>{fields.data.map((field) => <tr key={field.field}><th>{fieldLabels[field.field]}</th><td>{field.raw ?? "—"}</td><td>{field.status}</td></tr>)}</tbody></table>}</section>;
}

function CategoryControl({ email, onChanged }: { email: EmailRecord; onChanged: () => void }) {
  const [category, setCategory] = useState(email.category); const [saving, setSaving] = useState(false); const [saved, setSaved] = useState(false);
  useEffect(() => { setCategory(email.category); setSaved(false); }, [email.email_id, email.category]);
  const save = async (next = category) => { setSaving(true); try { await api.changeCategory(email.email_id, next); setCategory(next); setSaved(true); onChanged(); } finally { setSaving(false); } };
  return <section className="category-control"><label>Category<select value={category} disabled={saving} onChange={(event) => setCategory(event.target.value)}>{categoryLabels.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><button disabled={saving || category === email.category} onClick={() => void save()}>Save category</button>{email.category === "SPAM" && <button className="secondary-action" disabled={saving} onClick={() => void save("GENERAL")}>Not spam → General</button>}{saved && <small>{email.category_override ? "Human override saved" : "Using detected category"}</small>}</section>;
}

const fieldLabels: Record<string, string> = {
  shipper: "Shipper", consignee: "Consignee", notify_party: "Notify party",
  port_of_loading: "Port of loading", port_of_discharge: "Port of discharge",
  container_count: "Container count", gross_weight_kg: "Gross weight (kg)",
};

function ComparisonWorkspace({ email, comparison, documents, onComparisonUpdated }: { email: EmailRecord; comparison: Comparison; documents: DocumentSummary[]; onComparisonUpdated: (comparison: Comparison) => void }) {
  const [view, setView] = useState<"aligned" | "document">("aligned");
  const si = documents.find((document) => document.role_detected === "SI") ?? null;
  const bl = documents.find((document) => document.role_detected === "BL") ?? null;
  const [texts, setTexts] = useState<LoadState<{ si: string | null; bl: string | null }>>({ data: null, loading: true, error: null });
  const orderedFields = useMemo(() => {
    const severityRank = (severity: FieldComparison["severity"]) => severity === "high" ? 1 : 0;
    return [...comparison.field_results].sort((left, right) => severityRank(right.severity) - severityRank(left.severity));
  }, [comparison.field_results]);

  useEffect(() => {
    let cancelled = false;
    setTexts({ data: null, loading: true, error: null });
    Promise.all([si ? api.text(si.doc_id).catch(() => null) : Promise.resolve(null), bl ? api.text(bl.doc_id).catch(() => null) : Promise.resolve(null)]).then(
      ([siText, blText]) => !cancelled && setTexts({ data: { si: siText, bl: blText }, loading: false, error: null }),
      (error: Error) => !cancelled && setTexts({ data: null, loading: false, error: error.message }),
    );
    return () => { cancelled = true; };
  }, [si?.doc_id, bl?.doc_id]);

  const statusMessage = comparison.status === "MISMATCH"
    ? `Mismatch — ${comparison.defect_fields.length} field${comparison.defect_fields.length === 1 ? "" : "s"}`
    : comparison.status === "NEEDS_REVIEW"
      ? `Needs review: ${(comparison.review_reason ?? "unknown").replaceAll("_", " ")}`
      : "No mismatch detected";

  return <section className="comparison-workspace" aria-label="Shipping instruction and draft BL comparison">
    <div className={`comparison-banner ${statusClass(comparison.status)}`}><strong>{statusMessage}</strong>{comparison.explanations.map((item) => <span key={item}>{item}</span>)}</div>
    <ComparisonActions email={email} comparison={comparison} documents={documents} />
    <div className="field-strip" aria-label="Seven field comparison summary">
      {orderedFields.map((item) => <button key={item.field} className={item.equal ? "field-chip equal" : "field-chip differs"} onClick={() => document.getElementById(`comparison-${item.field}`)?.scrollIntoView({ behavior: "smooth", block: "center" })}>{item.equal ? "✓" : "✕"} {fieldLabels[item.field]}</button>)}
    </div>
    <div className="comparison-tabs" role="tablist" aria-label="Comparison views">
      <button role="tab" aria-selected={view === "aligned"} className={view === "aligned" ? "selected" : ""} onClick={() => setView("aligned")}>Aligned view</button>
      <button role="tab" aria-selected={view === "document"} className={view === "document" ? "selected" : ""} onClick={() => setView("document")}>Document view</button>
    </div>
    {view === "aligned" ? <><AlignedComparison si={si} bl={bl} fields={orderedFields} status={comparison.status} /><PanelState label="other information" state={texts} />{texts.data && <OtherInformation siText={texts.data.si} blText={texts.data.bl} fields={orderedFields} />}</> : <>
      <PanelState label="canonical documents" state={texts} />
      {texts.data && <DocumentComparison si={si} bl={bl} texts={texts.data} fields={orderedFields} />}
    </>}
    <details className="field-table"><summary>Compact field table</summary><table><colgroup><col className="field-name-column" /><col /><col /><col className="field-status-column" /></colgroup><thead><tr><th>Field</th><th>SI</th><th>Draft BL</th><th>Status</th></tr></thead><tbody>{orderedFields.map((item) => <tr key={item.field}><th>{fieldLabels[item.field]}</th><td>{item.si_raw ?? "—"}</td><td>{item.bl_raw ?? "—"}</td><td>{item.equal ? "Match" : comparison.status === "NEEDS_REVIEW" ? "Review" : "Mismatch"}</td></tr>)}</tbody></table></details>
    {comparison.status === "NEEDS_REVIEW" && <ReviewPanel emailId={email.email_id} comparison={comparison} onSaved={onComparisonUpdated} />}
    {comparison.reviews.length > 0 && <ReviewAudit reviews={comparison.reviews} fields={orderedFields} />}
  </section>;
}

function truncate(value: string, limit = 180) { return value.length <= limit ? value : `${value.slice(0, limit - 1)}…`; }

function draftMessage(email: EmailRecord, comparison: Comparison, documents: DocumentSummary[]) {
  const missingRole = documents.some((document) => document.role_detected === "SI") ? "draft BL" : "shipping instruction";
  if (comparison.status === "NEEDS_REVIEW" && comparison.review_reason === "missing_attachment") return { subject: `Re: ${email.subject}`, body: `Hi,\n\nCould you please send the missing ${missingRole} for this shipment so we can complete the document check?\n\nThank you.` };
  const lines = comparison.field_results.filter((field) => comparison.defect_fields.includes(field.field)).map((field) => `- ${fieldLabels[field.field]}: SI says "${truncate(field.si_raw ?? "not available")}", draft BL says "${truncate(field.bl_raw ?? "not available")}"`);
  let body = `Hi,\n\nWe checked the draft BL against the SI and found these differences:\n\n${lines.join("\n")}\n\nPlease review and send a corrected draft BL.\n\nThank you.`;
  if (body.length > 1550) body = `${body.slice(0, 1480)}\n\nSome values were shortened; see attached comparison.\n\nThank you.`;
  return { subject: `Re: ${email.subject}`, body };
}

function composeLinks(email: EmailRecord, comparison: Comparison, documents: DocumentSummary[]) {
  const message = draftMessage(email, comparison, documents);
  let body = message.body;
  let params = new URLSearchParams({ view: "cm", fs: "1", to: email.from, su: truncate(message.subject, 180), body });
  while (`https://mail.google.com/mail/?${params}`.length > 1950 && body.length > 260) {
    body = `${body.slice(0, Math.max(180, body.length - 160))}\n\nSee attached comparison for the complete values.`;
    params = new URLSearchParams({ view: "cm", fs: "1", to: email.from, su: truncate(message.subject, 180), body });
  }
  const mailto = new URLSearchParams({ subject: message.subject, body: message.body });
  return { message: { ...message, body }, gmail: `https://mail.google.com/mail/?${params}`, mailto: `mailto:${encodeURIComponent(email.from)}?${mailto}` };
}

function ComparisonActions({ email, comparison, documents }: { email: EmailRecord; comparison: Comparison; documents: DocumentSummary[] }) {
  const [copied, setCopied] = useState(false);
  const followUpKey = `sdoc-follow-up:${email.email_id}`;
  const [drafted, setDrafted] = useState(() => localStorage.getItem(followUpKey) === "1");
  const confident = comparison.field_results.every((field) => field.confidence >= 0.75);
  if (!(comparison.status === "MISMATCH" && confident) && !(comparison.status === "NEEDS_REVIEW" && comparison.review_reason === "missing_attachment")) return null;
  const links = composeLinks(email, comparison, documents);
  const label = comparison.status === "MISMATCH" ? "Send email" : "Request missing document";
  const copy = async () => { await navigator.clipboard?.writeText(`Subject: ${links.message.subject}\n\n${links.message.body}`); setCopied(true); };
  const draft = () => { window.open(links.gmail, "_blank", "noopener"); localStorage.setItem(followUpKey, "1"); setDrafted(true); };
  return <div className="comparison-actions"><button onClick={draft}>{label}</button><a href={links.mailto} onClick={() => { localStorage.setItem(followUpKey, "1"); setDrafted(true); }}>Open mail app</a><button className="secondary-action" onClick={() => void copy()}>{copied ? "Copied" : "Copy text"}</button>{drafted && <span className="follow-up-marker">Follow-up drafted</span>}<small>Opens a pre-filled draft only; it never sends mail.</small></div>;
}

function ReviewPanel({ emailId, comparison, onSaved }: { emailId: string; comparison: Comparison; onSaved: (comparison: Comparison) => void }) {
  const [context, setContext] = useState<LoadState<ReviewContext[]>>({ data: null, loading: true, error: null });
  const [field, setField] = useState(comparison.field_results.find((item) => !item.equal)?.field ?? "shipper");
  const [role, setRole] = useState<"SI" | "BL">("BL");
  const [value, setValue] = useState(""); const [reviewer, setReviewer] = useState(""); const [note, setNote] = useState("");
  const [disposition, setDisposition] = useState<"confirmed" | "cannot_determine" | "unreadable">("confirmed");
  const [saving, setSaving] = useState(false); const [error, setError] = useState<string | null>(null);
  useEffect(() => { let cancelled = false; api.reviewContext(emailId).then((data) => !cancelled && setContext({ data, loading: false, error: null }), (reason: Error) => !cancelled && setContext({ data: null, loading: false, error: reason.message })); return () => { cancelled = true; }; }, [emailId]);
  const evidence = context.data?.find((item) => item.doc_role === role && item.field === field) ?? null;
  const save = async (event: FormEvent) => { event.preventDefault(); setSaving(true); setError(null); try { onSaved(await api.saveReview(emailId, { field, doc_role: role, value, reviewer, note, disposition })); } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not save review"); } finally { setSaving(false); } };
  return <section className="review-panel"><p className="eyebrow">Human review</p><h3>Confirm or correct extracted value</h3><p>Reason: <strong>{comparison.review_reason?.replaceAll("_", " ")}</strong>. The original extraction stays visible in the audit trail.</p><PanelState label="review evidence" state={context} /><form onSubmit={save}><div className="review-grid"><label>Document<select value={role} onChange={(event) => setRole(event.target.value as "SI" | "BL")}><option value="SI">Shipping instruction</option><option value="BL">Draft BL</option></select></label><label>Field<select value={field} onChange={(event) => setField(event.target.value)}>{comparison.field_results.map((item) => <option key={item.field} value={item.field}>{fieldLabels[item.field]}</option>)}</select></label><label>Decision<select value={disposition} onChange={(event) => setDisposition(event.target.value as typeof disposition)}><option value="confirmed">Confirm / correct value</option><option value="cannot_determine">Cannot determine</option><option value="unreadable">Unreadable</option></select></label><label>Reviewer<input value={reviewer} onChange={(event) => setReviewer(event.target.value)} placeholder="Your name (optional)" /></label></div>{disposition === "confirmed" && <label>Correct value<input required value={value} onChange={(event) => setValue(event.target.value)} placeholder={evidence?.raw ?? "Enter value"} /></label>}<label>Note<textarea required={disposition !== "confirmed"} value={note} onChange={(event) => setNote(event.target.value)} placeholder="Why this was confirmed or unresolved" /></label><div className="source-evidence"><strong>Source evidence</strong><span>{evidence ? `Original read: ${evidence.raw ?? "no value"} · line ${evidence.line_no ?? "not available"}` : "No extracted row; inspect the source document."}</span>{evidence?.source_text_url && <a href={evidence.source_text_url} target="_blank" rel="noreferrer">Open canonical text</a>}{evidence?.source_page_url && <a href={evidence.source_page_url} target="_blank" rel="noreferrer">Open source page</a>}</div>{error && <p className="panel-error">{error}</p>}<button disabled={saving} type="submit">{saving ? "Saving…" : "Save review and recompute"}</button></form></section>;
}

function ReviewAudit({ reviews, fields }: { reviews: Comparison["reviews"]; fields: FieldComparison[] }) {
  return <details className="review-audit"><summary>Review audit trail ({reviews.length})</summary><ul>{reviews.map((review) => { const result = fields.find((item) => item.field === review.field); const original = review.doc_role === "SI" ? result?.si_original_raw : result?.bl_original_raw; return <li key={review.id}><strong>{fieldLabels[review.field]} · {review.doc_role}</strong>: original “{original ?? "not available"}”; reviewer {review.disposition.replaceAll("_", " ")}{review.value ? ` as “${review.value}”` : ""}{review.reviewer ? ` (${review.reviewer})` : ""}{review.note ? ` — ${review.note}` : ""}</li>; })}</ul></details>;
}

function AlignedComparison({ si, bl, fields, status }: { si: DocumentSummary | null; bl: DocumentSummary | null; fields: FieldComparison[]; status: Comparison["status"] }) {
  return <div className="aligned-comparison">
    <DocumentHeader title="Shipping instruction" document={si} missing="SI not attached" />
    <DocumentHeader title="Draft BL" document={bl} missing="Draft BL not attached" />
    {fields.map((item) => <div id={`comparison-${item.field}`} className={`comparison-row ${item.equal ? "" : status === "NEEDS_REVIEW" ? "review" : "mismatch"}`} key={item.field}>
      <div className={`comparison-cell ${status === "NEEDS_REVIEW" && (item.review_side === "SI" || item.review_side === "BOTH") ? "review-highlight" : ""}`}><span className="comparison-label">{fieldLabels[item.field]}</span><span>{item.si_raw ?? <em>Not available</em>}</span>{status === "NEEDS_REVIEW" && (item.review_side === "SI" || item.review_side === "BOTH") && <small className="review-marker">Review source</small>}</div>
      <div className={`comparison-cell bl-cell ${status === "MISMATCH" && !item.equal ? "highlighted" : ""} ${status === "NEEDS_REVIEW" && (item.review_side === "BL" || item.review_side === "BOTH") ? "review-highlight" : ""}`}><span className="comparison-label">{fieldLabels[item.field]}</span><span>{!item.equal && item.si_raw && item.bl_raw ? <HighlightedValue expected={item.si_raw} actual={item.bl_raw} segments={item.bl_diff_segments} /> : item.bl_raw ?? <em>Not available</em>}</span>{status === "MISMATCH" && !item.equal && item.si_raw && <small>SI: {item.si_raw}</small>}{status === "NEEDS_REVIEW" && (item.review_side === "BL" || item.review_side === "BOTH") && <small className="review-marker">Review source</small>}{item.diff_kind === "format_only" && <small>Same value, different format</small>}</div>
    </div>)}
  </div>;
}

function DocumentHeader({ title, document, missing }: { title: string; document: DocumentSummary | null; missing: string }) {
  return <div className="comparison-column-header"><strong>{title}</strong><span>{document ? `${document.path?.split("/").at(-1)} · ${attachmentIcon(document.ext)}` : missing}</span>{document && <a href={`/api/documents/${encodeURIComponent(document.doc_id)}/original?download=1`} target="_blank" rel="noreferrer">Original</a>}</div>;
}

function OtherInformation({ siText, blText, fields }: { siText: string | null; blText: string | null; fields: FieldComparison[] }) {
  const values = new Set(fields.flatMap((field) => [field.si_raw, field.bl_raw]).filter((value): value is string => Boolean(value)));
  const remaining = (text: string | null) => (text ?? "").split("\n").filter((line) => line.includes(":") && ![...values].some((value) => line.includes(value))).slice(0, 40);
  const siLines = remaining(siText); const blLines = remaining(blText);
  return <details className="other-information"><summary>Other information</summary><div><pre>{siLines.join("\n") || "No additional lines"}</pre><pre>{blLines.join("\n") || "No additional lines"}</pre></div></details>;
}

function DocumentComparison({ si, bl, texts, fields }: { si: DocumentSummary | null; bl: DocumentSummary | null; texts: { si: string | null; bl: string | null }; fields: FieldComparison[] }) {
  const siPanel = useRef<HTMLPreElement>(null);
  const blPanel = useRef<HTMLPreElement>(null);
  const syncing = useRef(false);
  const sync = (source: HTMLPreElement, target: HTMLPreElement | null) => {
    if (!target || syncing.current) return;
    syncing.current = true;
    target.scrollTop = source.scrollTop;
    target.scrollLeft = source.scrollLeft;
    requestAnimationFrame(() => { syncing.current = false; });
  };
  return <div className="document-comparison"><CanonicalDocument title="Shipping instruction" document={si} text={texts.si} fields={fields} side="si" scrollRef={siPanel} onScroll={(event) => sync(event.currentTarget, blPanel.current)} /><CanonicalDocument title="Draft BL" document={bl} text={texts.bl} fields={fields} side="bl" scrollRef={blPanel} onScroll={(event) => sync(event.currentTarget, siPanel.current)} /></div>;
}

function HighlightedValue({ expected, actual, segments }: { expected: string; actual: string; segments?: Array<{ text: string; changed: boolean }> }) {
  const parts = segments?.length ? segments : [{ text: actual, changed: expected.toLocaleLowerCase() !== actual.toLocaleLowerCase() }];
  return <>{parts.map((part, index) => part.changed ? <mark key={index}>{part.text}</mark> : <span key={index}>{part.text}</span>)}</>;
}

function CanonicalDocument({ title, document, text, fields, side, scrollRef, onScroll }: { title: string; document: DocumentSummary | null; text: string | null; fields: FieldComparison[]; side: "si" | "bl"; scrollRef?: RefObject<HTMLPreElement | null>; onScroll?: UIEventHandler<HTMLPreElement> }) {
  if (!document) return <section className="canonical-document missing-document"><h3>{title}</h3><p>{side === "bl" ? "Draft BL not attached" : "Shipping instruction not attached"}</p></section>;
  if (!text) return <section className="canonical-document missing-document"><h3>{title}</h3><p>This document is unreadable. Review is required.</p></section>;
  const highlights = side === "bl" ? fields.filter((field) => !field.equal && field.bl_raw).map((field) => field.bl_raw as string) : [];
  return <section className="canonical-document"><h3>{title}</h3><p>{document.path?.split("/").at(-1)}</p>{document.ext === ".pdf" ? <PdfDocumentBody documentId={document.doc_id} text={text} highlights={highlights} scrollRef={scrollRef} onScroll={onScroll} /> : <pre ref={scrollRef} onScroll={onScroll}>{text.split("\n").map((line, index) => <CanonicalLine key={index} line={line} highlights={highlights} />)}</pre>}</section>;
}

function PdfDocumentBody({ documentId, text, highlights, scrollRef, onScroll }: { documentId: string; text: string; highlights: string[]; scrollRef?: RefObject<HTMLPreElement | null>; onScroll?: UIEventHandler<HTMLPreElement> }) {
  const [tab, setTab] = useState<"text" | "pages">("text");
  return <><div className="pdf-source-tabs" role="tablist"><button role="tab" aria-selected={tab === "text"} className={tab === "text" ? "selected" : ""} onClick={() => setTab("text")}>Extracted text</button><button role="tab" aria-selected={tab === "pages"} className={tab === "pages" ? "selected" : ""} onClick={() => setTab("pages")}>Source pages</button></div>{tab === "text" ? <pre ref={scrollRef} onScroll={onScroll}>{text.split("\n").map((line, index) => <CanonicalLine key={index} line={line} highlights={highlights} />)}</pre> : <SourcePages documentId={documentId} />}</>;
}

function SourcePages({ documentId }: { documentId: string }) {
  const [pages, setPages] = useState<string[]>([]);
  useEffect(() => { let cancelled = false; api.preview(documentId).then((preview) => !cancelled && setPages(preview.original?.kind === "page_images" ? preview.original.pages ?? [] : [])); return () => { cancelled = true; }; }, [documentId]);
  if (!pages.length) return null;
  return <div className="source-pages">{pages.map((page, index) => <img key={page} src={page} alt={`Source page ${index + 1}`} />)}</div>;
}

function CanonicalLine({ line, highlights }: { line: string; highlights: string[] }) {
  const matched = highlights.find((value) => line.includes(value));
  if (!matched) return <>{line}{"\n"}</>;
  const [before, after] = line.split(matched, 2);
  return <>{before}<mark>{matched}</mark>{after}{"\n"}</>;
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
