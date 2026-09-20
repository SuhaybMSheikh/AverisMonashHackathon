import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
const skillDir = "C:/Users/yeapz/.codex/plugins/cache/openai-primary-runtime/presentations/26.905.11957/skills/presentations";
const workspaceDir = "C:/Users/yeapz/OneDrive/Desktop/AverisMonashHackathon";
const candidatePath = path.join(workspaceDir, ".codex-build/phase13/phase13_demo_deck_draft.pptx");
const finalPath = path.join(workspaceDir, "artifacts/phase13_demo_deck.pptx");
const { finalizePresentation } = await import(pathToFileURL(path.join(skillDir, "container_tools/artifact_tool_utils.mjs")).href);
await fs.mkdir(path.dirname(finalPath), { recursive: true });
const result = await finalizePresentation({
  workspaceDir, candidatePath, finalPath,
  pythonExecutable: "C:/Users/yeapz/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe",
  integrityValidatorPath: path.join(skillDir, "container_tools/inspect_presentation_package_integrity.py"),
  layoutValidatorPath: path.join(skillDir, "container_tools/inspect_presentation_layout_geometry.py"),
  layoutArgs: ["--expected-slide-size-emu", "12192000,6858000", "--validate-bullet-geometry", "--validate-heading-fit"],
  requiredNativeTableOwnerSlides: [],
  fontPolicy: { basis: "design", families: ["Arial"] },
  verifyArtifactToolImport: true,
  receiptPath: path.join(workspaceDir, ".codex-build/phase13/validation.json"),
});
console.log(JSON.stringify(result));
