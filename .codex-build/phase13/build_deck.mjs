import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const skillDir = "C:/Users/yeapz/.codex/plugins/cache/openai-primary-runtime/presentations/26.905.11957/skills/presentations";
const tmpDir = "C:/Users/yeapz/OneDrive/Desktop/AverisMonashHackathon/.codex-build/phase13";
const { resolvePresentationFont } = await import(pathToFileURL(path.join(skillDir, "container_tools/artifact_tool_utils.mjs")).href);
const font = resolvePresentationFont();
const deck = Presentation.create({ slideSize: { width: 1280, height: 720 } });

function addText(slide, text, left, top, width, height, size, color = "#172033", bold = false) {
  const shape = slide.shapes.add({ geometry: "textbox", position: { left, top, width, height }, fill: "none", line: { fill: "none", width: 0 } });
  shape.text = text;
  shape.text.style = { typeface: font, fontSize: size, color, bold, autoFit: "shrinkText" };
  return shape;
}
function slide(title, body, note) {
  const s = deck.slides.add(); s.background.fill = "#F4F6FB";
  addText(s, "AVERIS × MONASH", 72, 42, 400, 28, 16, "#2355D9", true);
  addText(s, title, 72, 92, 1130, 72, 40, "#172033", true);
  addText(s, body, 78, 200, 1110, 390, 25, "#26344D", false);
  addText(s, "Shipping Document Verification", 72, 664, 420, 20, 14, "#667085");
  s.speakerNotes.textFrame.setText(note);
  return s;
}
const cover = deck.slides.add(); cover.background.fill = "#2355D9";
addText(cover, "Shipping Document\nVerification", 82, 165, 900, 180, 54, "#FFFFFF", true);
addText(cover, "Explainable SI and draft BL checks for a mixed-format inbox", 86, 380, 920, 54, 26, "#E8EFFF");
addText(cover, "Averis × Monash Hackathon", 86, 612, 520, 24, 18, "#FFFFFF", true);
cover.speakerNotes.textFrame.setText("Project overview. Evidence: repository README and PROJECT_ROADMAP.md.");
slide("The operational problem", "Shipping teams receive instructions and draft bills across text, spreadsheets, Word files, PDFs, scans, and email bodies. A missed discrepancy can create downstream rework. The desk makes the decision and its evidence visible.", "Project framing from PROJECT_ROADMAP.md.");
slide("Pipeline architecture", "Read-only inbox\n↓\nCanonical conversion with content hashes\n↓\nRules-first classification with an optional cached Gemini fallback\n↓\nSeven-field extraction and normalization\n↓\nDeterministic SI versus BL comparison\n↓\nHuman review, audit trail, validated submission, offline snapshot", "Architecture follows README and PROJECT_ROADMAP.md.");
slide("Reliability controls", "Canonical text gives every format one parser. Deterministic comparison avoids model guesswork on material fields. Low confidence, corrupt files, missing attachments, and unknown document roles route to review. The Runs page records failures and offers safe retries.", "Evidence: Phase 4, 7, 9, and 11 implementation.");
slide("What the reviewer sees", "Open a BL comparison to inspect seven fixed field rows. The SI stays as the reference. Only the differing BL text receives a highlight. Uncertain cases expose source evidence, reviewer overlays, and an append-only audit trail.", "Evidence: Phase 8 and Phase 9 UI behavior.");
slide("Evaluation results", "Round 2 organizer submission\nFinal score: 1.000000\nStage 1 accuracy: 1.000000\nStage 3 field F1: 1.000000\nEnd-to-end rate: 1.000000\nEscalation precision: 1.000000\nEscalation recall: 0.850000\n\nThe team used full validated submissions only; no individual-email probing.", "Metrics: docs/score_log.md and docs/submit_summary.md, 2026-09-20.");
slide("Limitations and next steps", "Address comparison follows the documented party-name policy. Scan extraction can remain uncertain and routes to review. Gemini is opt-in and subject to free-tier availability. The demo uses a frozen local snapshot; the team should rehearse the clean-machine workflow before presenting.", "Limitations: docs/phase12_limitations.md. Demo procedure: docs/demo_rehearsal.md.");
const draft = path.join(tmpDir, "phase13_demo_deck_draft.pptx");
await (await PresentationFile.exportPptx(deck)).save(draft);
console.log(draft);
