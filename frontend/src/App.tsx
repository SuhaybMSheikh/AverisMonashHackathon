import { FormEvent, KeyboardEvent, RefObject, UIEventHandler, useEffect, useMemo, useRef, useState } from "react";

import { api, Comparison, DocumentPreview, DocumentSummary, EmailCounts, EmailRecord, EmailSummary, FieldComparison, Status } from "./api";

const PAGE_SIZE = 50;
const categoryLabels: Array<[string, string]> = [
  ["BL_COMPARISON", "BL comparison"],
  ["SI_REQUEST", "SI request"],
  ["INVOICE_QUERY", "Invoice query"],
  ["GENERAL", "General"],
  ["SPAM", "Spam"],
];

type Route = { kind: "inbox"; category?: string; status?: Exclude<Status, null> } | { kind: "email"; emailId: string };
type LoadState<T> = { data: T | null; loading: boolean; error: string | null };

function routeFromLocation(): Route {
  const segments = window.location.pathname.split("/").filter(Boolean);
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

  const selectedCategory = route.kind === "inbox" ? route.category : undefined;
  const selectedStatus = route.kind === "inbox" ? route.status : undefined;
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
    api.emails({ category: selectedCategory, status: selectedStatus, sort: selectedCategory === "BL_COMPARISON" && mismatchFirst ? "mismatch_first" : undefined, query: submittedQuery, page, pageSize: PAGE_SIZE }).then(
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
  }, [page, selectedCategory, selectedStatus, submittedQuery, mismatchFirst]);

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
        <button className={`nav-item ${!selectedCategory ? "selected" : ""}`} onClick={() => { setPage(1); navigate("/"); }}>
          <span>All</span><strong>{counts.data?.all ?? "—"}</strong>
        </button>
        <PanelState label="counts" state={counts} />
        <div className="nav-section">
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
    <button className={`email-card ${email.status ? `card-${email.status.toLowerCase()}` : ""} ${active ? "selected" : ""} ${keyboardActive ? "keyboard-active" : ""}`} onClick={onSelect} role="listitem">
      <div className="card-topline"><span className="sender">{email.from}</span><span className="attachment-total">{email.attachment_count || ""}</span></div>
      <strong className="subject">{email.subject || "(no subject)"}</strong>
      <p className="snippet">{email.body_snippet || "No message body"}</p>
      <div className="card-footer">
        <span className="category-badge">{email.category.replaceAll("_", " ")}</span>
        {email.status && <span className={`status-badge compact ${statusClass(email.status)}`}>{email.status === "NEEDS_REVIEW" ? "Needs review" : email.status}</span>}
        {email.category_conf !== null && email.category_conf < 0.75 && <span className="uncertain-chip">Uncertain</span>}
        <span className="format-icons">{email.formats.map((format) => <span title={format} key={format}>{attachmentIcon(format)}</span>)}</span>
      </div>
    </button>
  );
}

function Welcome() {
  return <div className="welcome"><p className="eyebrow">Email viewer</p><h2>Select an email</h2><p>Choose a card to read the original message. Use ↑ and ↓ to move through this page of results.</p></div>;
}

function EmailDetail({ email, documents, onClose }: { email: EmailRecord; documents: DocumentSummary[]; onClose: () => void }) {
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
      <div className="detail-actions"><button className="back-button" onClick={onClose}>← Inbox</button><span className={`status-badge ${statusClass(email.status)}`}>{email.status ?? "Pending review"}</span></div>
      <p className="eyebrow">{email.email_id}</p>
      <h2>{email.subject || "(no subject)"}</h2>
      <p className="from-line"><span>From</span>{email.from}</p>
      <details className="email-body" open><summary>Email body</summary><pre>{email.body}</pre></details>
      {email.category === "BL_COMPARISON" && <><PanelState label="comparison" state={comparison} />{comparison.data && <ComparisonWorkspace comparison={comparison.data} documents={documents} />}</>}
      {email.category !== "BL_COMPARISON" && <>
      <section className="attachments-section">
        <div><p className="eyebrow">Attachments</p><h3>{documents.length ? `${documents.length} file${documents.length === 1 ? "" : "s"}` : "No attachments"}</h3></div>
        {documents.length > 0 && <ul>{documents.map((document) => <li key={document.doc_id}><button className={`attachment-button ${document.doc_id === selectedDocumentId ? "selected" : ""}`} onClick={() => setSelectedDocumentId(document.doc_id)} aria-pressed={document.doc_id === selectedDocumentId}><span className="file-chip">{attachmentIcon(document.ext)}</span><span>{document.path?.split("/").at(-1) ?? document.doc_id}</span><small>{document.role_hint ?? "Unknown role"}</small></button></li>)}</ul>}
      </section>
      {selectedDocument && <DocPanel document={selectedDocument} />}
      </>}
    </article>
  );
}

const fieldLabels: Record<string, string> = {
  shipper: "Shipper", consignee: "Consignee", notify_party: "Notify party",
  port_of_loading: "Port of loading", port_of_discharge: "Port of discharge",
  container_count: "Container count", gross_weight_kg: "Gross weight (kg)",
};

function ComparisonWorkspace({ comparison, documents }: { comparison: Comparison; documents: DocumentSummary[] }) {
  const [view, setView] = useState<"aligned" | "document">("aligned");
  const si = documents.find((document) => document.role_detected === "SI") ?? null;
  const bl = documents.find((document) => document.role_detected === "BL") ?? null;
  const [texts, setTexts] = useState<LoadState<{ si: string | null; bl: string | null }>>({ data: null, loading: true, error: null });

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
    <div className="field-strip" aria-label="Seven field comparison summary">
      {comparison.field_results.map((item) => <button key={item.field} className={item.equal ? "field-chip equal" : "field-chip differs"} onClick={() => document.getElementById(`comparison-${item.field}`)?.scrollIntoView({ behavior: "smooth", block: "center" })}>{item.equal ? "✓" : "✕"} {fieldLabels[item.field]}</button>)}
    </div>
    <div className="comparison-tabs" role="tablist" aria-label="Comparison views">
      <button role="tab" aria-selected={view === "aligned"} className={view === "aligned" ? "selected" : ""} onClick={() => setView("aligned")}>Aligned view</button>
      <button role="tab" aria-selected={view === "document"} className={view === "document" ? "selected" : ""} onClick={() => setView("document")}>Document view</button>
    </div>
    {view === "aligned" ? <><AlignedComparison si={si} bl={bl} fields={comparison.field_results} status={comparison.status} /><PanelState label="other information" state={texts} />{texts.data && <OtherInformation siText={texts.data.si} blText={texts.data.bl} fields={comparison.field_results} />}</> : <>
      <PanelState label="canonical documents" state={texts} />
      {texts.data && <DocumentComparison si={si} bl={bl} texts={texts.data} fields={comparison.field_results} />}
    </>}
    <details className="field-table"><summary>Compact field table</summary><table><thead><tr><th>Field</th><th>SI</th><th>Draft BL</th><th>Status</th></tr></thead><tbody>{comparison.field_results.map((item) => <tr key={item.field}><th>{fieldLabels[item.field]}</th><td>{item.si_raw ?? "—"}</td><td>{item.bl_raw ?? "—"}</td><td>{item.equal ? "Match" : comparison.status === "NEEDS_REVIEW" ? "Review" : "Mismatch"}</td></tr>)}</tbody></table></details>
  </section>;
}

function AlignedComparison({ si, bl, fields, status }: { si: DocumentSummary | null; bl: DocumentSummary | null; fields: FieldComparison[]; status: Comparison["status"] }) {
  return <div className="aligned-comparison">
    <DocumentHeader title="Shipping instruction" document={si} missing="SI not attached" />
    <DocumentHeader title="Draft BL" document={bl} missing="Draft BL not attached" />
    {fields.map((item) => <div id={`comparison-${item.field}`} className={`comparison-row ${item.equal ? "" : status === "NEEDS_REVIEW" ? "review" : "mismatch"}`} key={item.field}>
      <div className="comparison-cell"><span className="comparison-label">{fieldLabels[item.field]}</span><span>{item.si_raw ?? <em>Not available</em>}</span></div>
      <div className={`comparison-cell bl-cell ${item.equal ? "" : "highlighted"}`}><span className="comparison-label">{fieldLabels[item.field]}</span><span>{!item.equal && item.si_raw && item.bl_raw ? <HighlightedValue expected={item.si_raw} actual={item.bl_raw} /> : item.bl_raw ?? <em>Not available</em>}</span>{!item.equal && item.si_raw && <small>SI: {item.si_raw}</small>}{item.diff_kind === "format_only" && <small>Same value, different format</small>}</div>
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

function HighlightedValue({ expected, actual }: { expected: string; actual: string }) {
  const left = expected.toLocaleLowerCase();
  const right = actual.toLocaleLowerCase();
  const rows = Array.from({ length: left.length + 1 }, () => Array(right.length + 1).fill(0) as number[]);
  for (let x = left.length - 1; x >= 0; x -= 1) for (let y = right.length - 1; y >= 0; y -= 1) rows[x][y] = left[x] === right[y] ? rows[x + 1][y + 1] + 1 : Math.max(rows[x + 1][y], rows[x][y + 1]);
  const unchanged = new Set<number>();
  for (let x = 0, y = 0; x < left.length && y < right.length;) {
    if (left[x] === right[y]) { unchanged.add(y); x += 1; y += 1; }
    else if (rows[x + 1][y] >= rows[x][y + 1]) x += 1;
    else y += 1;
  }
  const groups: Array<{ changed: boolean; text: string }> = [];
  for (let index = 0; index < actual.length; index += 1) {
    const changed = !unchanged.has(index);
    const previous = groups.at(-1);
    if (previous?.changed === changed) previous.text += actual[index];
    else groups.push({ changed, text: actual[index] });
  }
  return <>{groups.map((group, index) => group.changed ? <mark key={index}>{group.text}</mark> : <span key={index}>{group.text}</span>)}</>;
}

function CanonicalDocument({ title, document, text, fields, side, scrollRef, onScroll }: { title: string; document: DocumentSummary | null; text: string | null; fields: FieldComparison[]; side: "si" | "bl"; scrollRef?: RefObject<HTMLPreElement | null>; onScroll?: UIEventHandler<HTMLPreElement> }) {
  if (!document) return <section className="canonical-document missing-document"><h3>{title}</h3><p>{side === "bl" ? "Draft BL not attached" : "Shipping instruction not attached"}</p></section>;
  if (!text) return <section className="canonical-document missing-document"><h3>{title}</h3><p>This document is unreadable. Review is required.</p></section>;
  const highlights = side === "bl" ? fields.filter((field) => !field.equal && field.bl_raw).map((field) => field.bl_raw as string) : [];
  return <section className="canonical-document"><h3>{title}</h3><p>{document.path?.split("/").at(-1)}</p>{document.ext === ".pdf" && <SourcePages documentId={document.doc_id} />}<pre ref={scrollRef} onScroll={onScroll}>{text.split("\n").map((line, index) => <CanonicalLine key={index} line={line} highlights={highlights} />)}</pre></section>;
}

function SourcePages({ documentId }: { documentId: string }) {
  const [pages, setPages] = useState<string[]>([]);
  useEffect(() => { let cancelled = false; api.preview(documentId).then((preview) => !cancelled && setPages(preview.original?.kind === "page_images" ? preview.original.pages ?? [] : [])); return () => { cancelled = true; }; }, [documentId]);
  if (!pages.length) return null;
  return <details className="source-pages"><summary>Original pages</summary>{pages.map((page, index) => <img key={page} src={page} alt={`Source page ${index + 1}`} />)}</details>;
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
