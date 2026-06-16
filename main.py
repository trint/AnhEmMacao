import json
import os
import re
import tempfile
from datetime import datetime
from html import unescape
from pathlib import Path
from typing import Any
from xml.etree import ElementTree
from contextlib import contextmanager

import fcntl

from dotenv import load_dotenv
from greennode_agentbase import GreenNodeAgentBaseApp, PingStatus, RequestContext
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

load_dotenv()

app = GreenNodeAgentBaseApp()

DATA_DIR = Path(".agentbase")
KNOWLEDGE_FILE = DATA_DIR / "knowledge.json"
MAX_CONTEXT_CHARS = 4200
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 180
TOP_CONTEXT_CHUNKS = 6
DEFAULT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024

SUPPORTED_EXTENSIONS = {
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".xml",
    ".svg",
    ".drawio",
    ".bpmn",
    ".mmd",
    ".mermaid",
    ".puml",
    ".plantuml",
    ".pdf",
    ".docx",
    ".xlsx",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
READY = "READY"
NEEDS_REVIEW = "NEEDS_REVIEW"
FAILED = "FAILED"

QUALITY_CHECKLIST = [
    "Each case has a clear objective and expected result.",
    "Preconditions and test data are explicit.",
    "Positive, negative, boundary, workflow, integration, and permission scenarios are considered.",
    "Steps are executable by another QC without hidden assumptions.",
    "Priority and test type are assigned consistently.",
    "Generated cases reference the uploaded business documents where relevant.",
]

CHAT_HTML = """<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>QC Test Case Agent</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7fb;
      --panel: #ffffff;
      --text: #172033;
      --muted: #667085;
      --line: #d8dee9;
      --brand: #0f766e;
      --brand-dark: #115e59;
      --soft: #eef7f6;
      --warn: #fff7e6;
      --danger: #b42318;
      --shadow: 0 1px 2px rgba(16, 24, 40, .06);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--text);
      font: 15px/1.5 Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    .shell {
      min-height: 100vh;
      display: grid;
      grid-template-columns: minmax(340px, 460px) 1fr;
    }
    aside {
      background: var(--panel);
      border-right: 1px solid var(--line);
      padding: 24px;
      display: flex;
      flex-direction: column;
      gap: 16px;
      overflow: auto;
    }
    main {
      padding: 24px;
      overflow: auto;
    }
    h1 {
      margin: 0;
      font-size: 26px;
      line-height: 1.15;
      letter-spacing: 0;
    }
    h2 {
      margin: 0 0 10px;
      font-size: 16px;
      letter-spacing: 0;
    }
    .subtitle {
      margin: 6px 0 0;
      color: var(--muted);
    }
    .panel {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      background: #fff;
      box-shadow: var(--shadow);
    }
    label {
      display: block;
      margin: 0 0 7px;
      color: #344054;
      font-weight: 650;
      font-size: 13px;
    }
    input, textarea, select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px 11px;
      background: #fff;
      color: var(--text);
      font: inherit;
      outline: none;
    }
    textarea {
      min-height: 96px;
      resize: vertical;
    }
    input:focus, textarea:focus, select:focus {
      border-color: var(--brand);
      box-shadow: 0 0 0 3px rgba(15, 118, 110, .14);
    }
    .row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    .actions {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    button {
      width: 100%;
      border: 0;
      border-radius: 8px;
      padding: 11px 13px;
      background: var(--brand);
      color: #fff;
      font-weight: 750;
      cursor: pointer;
    }
    button.secondary {
      background: #344054;
    }
    button.light {
      background: #eef2f6;
      color: #243043;
    }
    button:hover { background: var(--brand-dark); }
    button.secondary:hover { background: #1d2939; }
    button.light:hover { background: #dfe5ee; }
    button:disabled {
      opacity: .65;
      cursor: not-allowed;
    }
    .hint {
      border: 1px solid #f7d38b;
      background: var(--warn);
      color: #7a4b00;
      border-radius: 8px;
      padding: 11px;
      font-size: 13px;
    }
    .toolbar {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: center;
      margin-bottom: 16px;
    }
    .status {
      color: var(--muted);
      font-size: 13px;
    }
    .empty {
      min-height: calc(100vh - 48px);
      display: grid;
      place-items: center;
      color: var(--muted);
      text-align: center;
      border: 1px dashed var(--line);
      border-radius: 8px;
      background: rgba(255,255,255,.65);
      padding: 24px;
    }
    .summary {
      background: var(--soft);
      border: 1px solid #b7dfda;
      border-radius: 8px;
      padding: 16px;
      margin-bottom: 16px;
    }
    .summary h2 {
      margin: 0 0 6px;
      font-size: 18px;
    }
    .cases {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(330px, 1fr));
      gap: 14px;
    }
    .case, .knowledge-item {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 15px;
      box-shadow: var(--shadow);
    }
    .case h3 {
      margin: 0 0 10px;
      font-size: 16px;
      line-height: 1.3;
    }
    .meta {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 12px;
    }
    .pill {
      border-radius: 999px;
      background: #f2f4f7;
      color: #344054;
      padding: 4px 9px;
      font-size: 12px;
      font-weight: 650;
    }
    .pill.high { background: #fee4e2; color: #912018; }
    .kb-status {
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 11px;
      font-weight: 800;
      margin-left: 6px;
    }
    .kb-status.ready {
      background: #dcfae6;
      color: #067647;
    }
    .kb-status.needs_review {
      background: #fff1c2;
      color: #7a4b00;
    }
    .kb-status.failed {
      background: #fee4e2;
      color: #912018;
    }
    .section-title {
      margin: 12px 0 6px;
      color: #344054;
      font-weight: 750;
      font-size: 13px;
    }
    ol, ul {
      margin: 0;
      padding-left: 20px;
    }
    li { margin: 4px 0; }
    .error {
      color: var(--danger);
      background: #fff1f0;
      border: 1px solid #fecdca;
      border-radius: 8px;
      padding: 12px;
    }
    .knowledge-list {
      display: grid;
      gap: 10px;
      max-height: 220px;
      overflow: auto;
    }
    .knowledge-item {
      padding: 10px;
      font-size: 13px;
    }
    .knowledge-item strong {
      display: block;
      margin-bottom: 3px;
    }
    .item-actions {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 6px;
      margin-top: 9px;
    }
    .item-actions button {
      padding: 7px 8px;
      font-size: 12px;
    }
    .review-box {
      display: none;
      margin-top: 10px;
    }
    .review-box.open {
      display: block;
    }
    .review-box textarea {
      min-height: 120px;
      font-size: 13px;
    }
    .small {
      color: var(--muted);
      font-size: 12px;
    }
    @media (max-width: 900px) {
      .shell { grid-template-columns: 1fr; }
      aside { border-right: 0; border-bottom: 1px solid var(--line); }
      main { padding: 18px; }
      .row, .actions { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside>
      <div>
        <h1>QC Test Case Agent</h1>
        <p class="subtitle">Train bang tai lieu, workflow, diagram roi generate test case theo context do.</p>
      </div>
      <div class="hint" id="ai-status">AI: checking...</div>

      <section class="panel">
        <h2>Training knowledge</h2>
        <label for="knowledge-title">Document / workflow name</label>
        <input id="knowledge-title" placeholder="Document / workflow name" />
        <label for="knowledge-type">Type</label>
        <select id="knowledge-type">
          <option value="workflow">Workflow</option>
          <option value="diagram">Diagram</option>
          <option value="requirement">Requirement document</option>
          <option value="business-rule">Business rule</option>
        </select>
        <label for="knowledge-text">Paste content for documents/workflows</label>
        <textarea id="knowledge-text" placeholder="Paste requirement, workflow, rules, or process text here."></textarea>
        <div class="actions">
          <button id="train-text" type="button">Train text</button>
          <button id="refresh-knowledge" class="light" type="button">Refresh</button>
        </div>
        <label for="knowledge-file">Upload file</label>
        <input id="knowledge-file" type="file" />
        <button id="train-file" class="secondary" type="button">Train file</button>
        <div class="hint" id="training-hint">Use paste for docs/workflows. Use upload for diagrams. Image-only PNG/JPG/WebP will be saved as NEEDS_REVIEW until OCR/vision is connected.</div>
      </section>

      <section class="panel">
        <h2>Generate test cases</h2>
        <form id="chat-form">
          <label for="feature">Feature / Requirement</label>
          <textarea id="feature" required placeholder="Feature or requirement to test"></textarea>
          <div class="row">
            <div>
              <label for="actor">Actor</label>
              <input id="actor" placeholder="User role" />
            </div>
            <div>
              <label for="platform">Platform</label>
              <input id="platform" placeholder="Application surface" />
            </div>
          </div>
          <label for="criteria">Acceptance criteria</label>
          <textarea id="criteria" placeholder="Acceptance criteria"></textarea>
          <button id="send" type="submit">Generate from trained knowledge</button>
        </form>
      </section>

      <section class="panel">
        <h2>Knowledge base</h2>
        <div id="knowledge-list" class="knowledge-list"></div>
      </section>
    </aside>
    <main>
      <div class="toolbar">
        <strong>Generated test cases</strong>
        <span class="status" id="status">Ready</span>
      </div>
      <div id="output" class="empty">Train tai lieu hoac nhap feature, sau do bam Generate.</div>
    </main>
  </div>
  <script>
    const form = document.querySelector("#chat-form");
    const output = document.querySelector("#output");
    const statusEl = document.querySelector("#status");
    const send = document.querySelector("#send");
    const trainText = document.querySelector("#train-text");
    const trainFile = document.querySelector("#train-file");
    const refreshKnowledge = document.querySelector("#refresh-knowledge");
    const knowledgeList = document.querySelector("#knowledge-list");
    const knowledgeType = document.querySelector("#knowledge-type");
    const knowledgeText = document.querySelector("#knowledge-text");
    const trainingHint = document.querySelector("#training-hint");

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, char => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
      })[char]);
    }

    function list(items, ordered = false) {
      if (!Array.isArray(items)) {
        if (items && typeof items === "object") {
          items = Object.entries(items).map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(", ") : value}`);
        } else {
          items = items ? [items] : [];
        }
      }
      const tag = ordered ? "ol" : "ul";
      return `<${tag}>${items.map(item => `<li>${escapeHtml(item)}</li>`).join("")}</${tag}>`;
    }

    function renderKnowledge(items) {
      if (!items.length) {
        knowledgeList.innerHTML = '<div class="small">No trained knowledge yet.</div>';
        return;
      }
      knowledgeList.innerHTML = items.map(item => `
        <div class="knowledge-item" data-id="${escapeHtml(item.id)}">
          <strong>${escapeHtml(item.title)}<span class="kb-status ${String(item.status || "READY").toLowerCase()}">${escapeHtml(item.status || "READY")}</span></strong>
          <div class="small">${escapeHtml(item.type)} · ${escapeHtml(item.source)} · ${item.text_length} chars · ${item.chunk_count || 0} chunks</div>
          <div class="small">${escapeHtml(item.status_message || "")}</div>
          <div>${escapeHtml(item.preview)}</div>
          <div class="item-actions">
            <button class="light" type="button" data-action="toggle-review">Review/Edit</button>
            <button class="secondary" type="button" data-action="mark-ready">Mark READY</button>
            <button class="light" type="button" data-action="mark-review">Needs review</button>
            <button class="light" type="button" data-action="delete">Delete</button>
          </div>
          <div class="review-box">
            <label>Reviewed content used for generation</label>
            <textarea>${escapeHtml(item.text || "")}</textarea>
            <div class="actions">
              <button type="button" data-action="save-ready">Save as READY</button>
              <button class="light" type="button" data-action="save-review">Save review note</button>
            </div>
          </div>
        </div>
      `).join("");
    }

    async function updateKnowledge(id, action, text = null) {
      statusEl.textContent = "Updating knowledge...";
      const payload = { id, action };
      if (text !== null) payload.text = text;
      const response = await fetch("/knowledge/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Knowledge update failed");
      await loadKnowledge();
      statusEl.textContent = data.item ? `Updated: ${data.item.status}` : "Updated";
    }

    function syncTrainingMode() {
      if (knowledgeType.value === "diagram") {
        knowledgeText.disabled = true;
        trainText.disabled = true;
        knowledgeText.placeholder = "Diagram should be uploaded as a file. Use SVG/drawio/BPMN/Mermaid/PDF for readable diagrams; PNG/JPG/WebP will be saved as NEEDS_REVIEW.";
        trainingHint.textContent = "Diagram mode: upload the diagram file. Text paste is disabled because diagrams are normally visual artifacts, not manual text.";
      } else {
        knowledgeText.disabled = false;
        trainText.disabled = false;
        knowledgeText.placeholder = "Paste requirement, workflow, rules, or process text here.";
        trainingHint.textContent = "Use paste for docs/workflows. Use upload for diagrams. Image-only PNG/JPG/WebP will be saved as NEEDS_REVIEW until OCR/vision is connected.";
      }
    }

    async function loadKnowledge() {
      const response = await fetch("/knowledge");
      const data = await response.json();
      renderKnowledge(data.items || []);
    }

    async function loadAiStatus() {
      const response = await fetch("/ai/status");
      const data = await response.json();
      const aiStatus = document.querySelector("#ai-status");
      aiStatus.textContent = data.configured
        ? `AI: ${data.model} connected via ${data.wire_api}`
        : "AI: fallback mode. Configure MAAS_API_KEY or LLM_API_KEY to enable LLM RAG.";
    }

    function render(data) {
      const cases = data.test_cases || [];
      const sourceRefs = data.source_refs || [];
      output.className = "";
      output.innerHTML = `
        <section class="summary">
          <h2>${escapeHtml(data.feature)}</h2>
          <div>${escapeHtml(data.actor)} · ${escapeHtml(data.platform)} · ${cases.length} cases · AI mode: ${escapeHtml(data.ai_mode || "fallback")}</div>
          <div class="section-title">Knowledge used</div>
          ${sourceRefs.length ? list(sourceRefs.map(ref => `${ref.title} (${ref.type})`)) : '<div class="small">No matching knowledge found.</div>'}
          <div class="section-title">Context summary</div>
          <div>${escapeHtml(data.context_summary || "No context summary.")}</div>
        </section>
        <section class="cases">
          ${cases.map(testCase => `
            <article class="case">
              <h3>${escapeHtml(testCase.id)} · ${escapeHtml(testCase.title)}</h3>
              <div class="meta">
                <span class="pill">${escapeHtml(testCase.type)}</span>
                <span class="pill ${String(testCase.priority).toLowerCase()}">${escapeHtml(testCase.priority)}</span>
              </div>
              <div class="section-title">Preconditions</div>
              ${list(testCase.preconditions || [])}
              <div class="section-title">Test data</div>
              ${list(testCase.test_data || [])}
              <div class="section-title">Steps</div>
              ${list(testCase.steps || [], true)}
              <div class="section-title">Expected result</div>
              <p>${escapeHtml(testCase.expected_result)}</p>
              ${(testCase.references || []).length ? `<div class="section-title">References</div>${list(testCase.references)}` : ""}
            </article>
          `).join("")}
        </section>
      `;
    }

    async function trainFromText() {
      const payload = {
        title: document.querySelector("#knowledge-title").value,
        type: document.querySelector("#knowledge-type").value,
        text: document.querySelector("#knowledge-text").value,
        source: "pasted-text"
      };
      trainText.disabled = true;
      statusEl.textContent = "Training text...";
      try {
        const response = await fetch("/knowledge", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Training failed");
        await loadKnowledge();
        statusEl.textContent = "Trained";
      } catch (error) {
        statusEl.textContent = "Error";
        output.className = "error";
        output.textContent = error.message;
      } finally {
        trainText.disabled = false;
      }
    }

    async function trainFromFile() {
      const fileInput = document.querySelector("#knowledge-file");
      if (!fileInput.files.length) {
        statusEl.textContent = "Choose a file first";
        return;
      }
      const formData = new FormData();
      formData.append("file", fileInput.files[0]);
      formData.append("title", document.querySelector("#knowledge-title").value || fileInput.files[0].name);
      formData.append("type", document.querySelector("#knowledge-type").value);
      trainFile.disabled = true;
      statusEl.textContent = "Training file...";
      try {
        const response = await fetch("/knowledge/upload", { method: "POST", body: formData });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Upload failed");
        await loadKnowledge();
        statusEl.textContent = `Saved: ${data.item?.status || "READY"}`;
      } catch (error) {
        statusEl.textContent = "Error";
        output.className = "error";
        output.textContent = error.message;
      } finally {
        trainFile.disabled = false;
      }
    }

    form.addEventListener("submit", async event => {
      event.preventDefault();
      send.disabled = true;
      statusEl.textContent = "Generating...";
      output.className = "empty";
      output.textContent = "Dang tao test cases tu knowledge base...";

      const payload = {
        feature: document.querySelector("#feature").value,
        actor: document.querySelector("#actor").value,
        platform: document.querySelector("#platform").value,
        acceptance_criteria: document.querySelector("#criteria").value.split("\\n").map(v => v.trim()).filter(Boolean)
      };

      try {
        const response = await fetch("/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Request failed");
        render(data);
        statusEl.textContent = "Done";
      } catch (error) {
        output.className = "error";
        output.textContent = error.message;
        statusEl.textContent = "Error";
      } finally {
        send.disabled = false;
      }
    });

    trainText.addEventListener("click", trainFromText);
    trainFile.addEventListener("click", trainFromFile);
    refreshKnowledge.addEventListener("click", loadKnowledge);
    knowledgeType.addEventListener("change", syncTrainingMode);
    knowledgeList.addEventListener("click", async event => {
      const button = event.target.closest("button[data-action]");
      if (!button) return;

      const itemEl = button.closest(".knowledge-item");
      const reviewBox = itemEl.querySelector(".review-box");
      const textarea = reviewBox.querySelector("textarea");
      const id = itemEl.dataset.id;
      const action = button.dataset.action;

      if (action === "toggle-review") {
        reviewBox.classList.toggle("open");
        return;
      }

      if (action === "delete" && !confirm("Delete this knowledge item?")) {
        return;
      }

      try {
        if (action === "mark-ready") await updateKnowledge(id, "mark-ready");
        if (action === "mark-review") await updateKnowledge(id, "mark-review");
        if (action === "delete") await updateKnowledge(id, "delete");
        if (action === "save-ready") await updateKnowledge(id, "save-ready", textarea.value);
        if (action === "save-review") await updateKnowledge(id, "save-review", textarea.value);
      } catch (error) {
        statusEl.textContent = "Error";
        output.className = "error";
        output.textContent = error.message;
      }
    });
    syncTrainingMode();
    loadAiStatus();
    loadKnowledge();
  </script>
</body>
</html>
"""


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\x00", " ").strip()
    return re.sub(r"\s+", " ", text)


def _normalize_multiline(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\x00", " ")
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_acceptance_criteria(raw: Any) -> list[str]:
    if isinstance(raw, list):
        items = [_clean_text(item) for item in raw]
        return [item for item in items if item]

    text = _normalize_multiline(raw)
    if not text:
        return []

    parts = re.split(r"(?:\n|;|\d+[.)]\s+|-\s+)", text)
    return [part.strip() for part in parts if part.strip()]


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return value[:40] or "feature"


def _case(
    case_id: str,
    title: str,
    case_type: str,
    priority: str,
    steps: list[str],
    expected: str,
    references: list[str] | None = None,
) -> dict:
    return {
        "id": case_id,
        "title": title,
        "type": case_type,
        "priority": priority,
        "preconditions": [
            "Test environment is available and stable.",
            "Tester has an account with the required permission for this scenario.",
        ],
        "test_data": [
            "Use valid baseline data for the feature under test.",
            "Record exact input values used during execution.",
        ],
        "steps": steps,
        "expected_result": expected,
        "references": references or [],
    }


@contextmanager
def _knowledge_lock():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = DATA_DIR / "knowledge.lock"
    with lock_path.open("w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _read_knowledge_unlocked() -> list[dict]:
    if not KNOWLEDGE_FILE.exists():
        return []
    try:
        data = json.loads(KNOWLEDGE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Knowledge file is corrupted: {KNOWLEDGE_FILE}") from exc
    except OSError as exc:
        raise RuntimeError(f"Could not read knowledge file: {KNOWLEDGE_FILE}") from exc
    if not isinstance(data, list):
        raise RuntimeError(f"Knowledge file must contain a JSON list: {KNOWLEDGE_FILE}")
    return [item for item in data if isinstance(item, dict)]


def _read_knowledge() -> list[dict]:
    with _knowledge_lock():
        return _read_knowledge_unlocked()


def _write_knowledge_unlocked(items: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=DATA_DIR, delete=False) as temp_file:
        json.dump(items, temp_file, indent=2, ensure_ascii=False)
        temp_file.write("\n")
        temp_path = Path(temp_file.name)
    temp_path.replace(KNOWLEDGE_FILE)


def _write_knowledge(items: list[dict]) -> None:
    with _knowledge_lock():
        _write_knowledge_unlocked(items)


def _preview(text: str, limit: int = 180) -> str:
    clean = _clean_text(text)
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3] + "..."


def _keywords(text: str) -> set[str]:
    tokens = re.findall(r"(?u)\b[\w-]{3,}\b", text.lower())
    stopwords = {
        "and",
        "the",
        "for",
        "with",
        "that",
        "this",
        "from",
        "user",
        "case",
        "test",
        "feature",
        "requirement",
        "workflow",
        "diagram",
        "can",
        "after",
        "before",
        "when",
        "then",
        "must",
        "should",
        "và",
        "hoặc",
        "các",
        "cho",
        "khi",
        "sau",
        "trước",
        "người",
        "dùng",
        "tính",
        "năng",
        "kiểm",
        "thử",
    }
    return {token for token in tokens if token not in stopwords}


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[dict]:
    normalized = _normalize_multiline(text)
    if not normalized:
        return []

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", normalized) if part.strip()]
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        if len(paragraph) > chunk_size:
            if current:
                chunks.append(current.strip())
                current = ""
            start = 0
            while start < len(paragraph):
                chunks.append(paragraph[start : start + chunk_size].strip())
                start += max(1, chunk_size - overlap)
            continue

        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            chunks.append(current.strip())
            current = paragraph

    if current:
        chunks.append(current.strip())

    return [
        {
            "chunk_id": index,
            "text": chunk,
            "keywords": sorted(_keywords(chunk)),
            "preview": _preview(chunk, 160),
        }
        for index, chunk in enumerate(chunks)
        if chunk
    ]


def _chunk_score(query: str, query_keywords: set[str], item: dict, chunk: dict) -> int:
    chunk_text = " ".join(
        [
            str(item.get("title", "")),
            str(item.get("type", "")),
            str(item.get("source", "")),
            str(chunk.get("text", "")),
        ]
    )
    chunk_keywords = set(chunk.get("keywords") or _keywords(chunk_text))
    score = len(query_keywords & chunk_keywords) * 3
    lower_query = query.lower().strip()
    lower_text = chunk_text.lower()
    if lower_query and lower_query in lower_text:
        score += 10
    for term in query_keywords:
        if term in str(item.get("title", "")).lower():
            score += 2
        if term in str(item.get("type", "")).lower():
            score += 1
    return score


def add_knowledge(
    title: str,
    knowledge_type: str,
    text: str,
    source: str,
    status: str = READY,
    status_message: str = "Readable and indexed.",
    readable: bool = True,
) -> dict:
    normalized = _normalize_multiline(text)
    if status == READY and len(normalized) < 3:
        raise ValueError("Knowledge content is too short to train.")

    with _knowledge_lock():
        items = _read_knowledge_unlocked()
        item = {
            "id": f"KB-{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
            "title": _clean_text(title) or "Untitled knowledge",
            "type": _clean_text(knowledge_type) or "document",
            "source": _clean_text(source) or "manual",
            "text": normalized,
            "text_length": len(normalized),
            "chunks": _chunk_text(normalized) if readable and status == READY else [],
            "preview": _preview(normalized),
            "status": status,
            "status_message": status_message,
            "readable": readable,
            "created_at": datetime.now().isoformat(),
        }
        items.insert(0, item)
        _write_knowledge_unlocked(items[:100])
    return item


def update_knowledge_item(knowledge_id: str, action: str, text: str | None = None) -> dict | None:
    with _knowledge_lock():
        items = _read_knowledge_unlocked()
        index = next((idx for idx, item in enumerate(items) if item.get("id") == knowledge_id), None)
        if index is None:
            raise ValueError("Knowledge item not found.")

        if action == "delete":
            removed = items.pop(index)
            _write_knowledge_unlocked(items)
            return {
                "id": removed.get("id"),
                "title": removed.get("title"),
                "status": "DELETED",
            }

        item = items[index]
        now = datetime.now().isoformat()

        if action in {"save-ready", "save-review"}:
            normalized = _normalize_multiline(text)
            if action == "save-ready" and len(normalized) < 8:
                raise ValueError("Reviewed content is too short to mark READY.")
            item["text"] = normalized
            item["text_length"] = len(normalized)
            item["chunks"] = _chunk_text(normalized) if action == "save-ready" else []
            item["preview"] = _preview(normalized)
            item["reviewed_at"] = now

        if action in {"mark-ready", "save-ready"}:
            if len(_normalize_multiline(item.get("text", ""))) < 8:
                raise ValueError("Add reviewed content before marking READY.")
            item["status"] = READY
            item["readable"] = True
            item["chunks"] = _chunk_text(item.get("text", ""))
            item["status_message"] = "Reviewed and indexed."
            item["reviewed_at"] = now
        elif action in {"mark-review", "save-review"}:
            item["status"] = NEEDS_REVIEW
            item["readable"] = False
            item["chunks"] = []
            item["status_message"] = "Saved for review. It will not be used for generation until marked READY."
            item["reviewed_at"] = now
        else:
            raise ValueError(f"Unsupported knowledge action: {action}")

        items[index] = item
        _write_knowledge_unlocked(items)
        return item


def retrieve_context(query: str, limit: int = 4) -> list[dict]:
    query_keywords = _keywords(query)
    scored = []
    for item in _read_knowledge():
        if item.get("status", READY) != READY or item.get("readable", True) is False:
            continue
        chunks = item.get("chunks") or _chunk_text(item.get("text", ""))
        for chunk in chunks:
            score = _chunk_score(query, query_keywords, item, chunk)
            if score >= 4:
                scored.append((score, item, chunk))

    scored.sort(key=lambda pair: (pair[0], pair[1].get("created_at", "")), reverse=True)

    grouped: dict[str, dict] = {}
    for score, item, chunk in scored[:TOP_CONTEXT_CHUNKS]:
        item_id = str(item.get("id"))
        if item_id not in grouped:
            grouped[item_id] = {
                **item,
                "matched_chunks": [],
                "match_score": 0,
            }
        grouped[item_id]["matched_chunks"].append(
            {
                "chunk_id": chunk.get("chunk_id"),
                "text": chunk.get("text", ""),
                "preview": chunk.get("preview") or _preview(chunk.get("text", "")),
                "score": score,
            }
        )
        grouped[item_id]["match_score"] += score

    results = sorted(grouped.values(), key=lambda item: item.get("match_score", 0), reverse=True)
    return results[:limit]


def summarize_context(items: list[dict]) -> str:
    if not items:
        return "No matching trained document, workflow, or diagram was found."

    snippets = []
    for item in items:
        matched_text = " ".join(chunk.get("text", "") for chunk in item.get("matched_chunks", []))
        snippets.append(f"{item.get('title', 'Untitled')}: {_preview(matched_text or item.get('text', ''), 360)}")
    summary = " | ".join(snippets)
    return summary[:MAX_CONTEXT_CHARS]


def derive_criteria_from_context(items: list[dict]) -> list[str]:
    candidates: list[str] = []
    for item in items:
        text = _normalize_multiline(
            "\n".join(chunk.get("text", "") for chunk in item.get("matched_chunks", [])) or item.get("text", "")
        )
        lines = [line.strip(" -\t") for line in text.splitlines() if line.strip()]
        for line in lines:
            lower = line.lower()
            if any(word in lower for word in ["must", "should", "cannot", "reject", "approve", "expire", "timeout", "permission", "role", "rule"]):
                candidates.append(line)

    cleaned = []
    seen = set()
    for candidate in candidates:
        value = _clean_text(candidate).strip(":- ")
        lower_value = value.lower()
        if lower_value in {"rule", "rules", "business rule", "business rules", "acceptance criteria"}:
            continue
        if 8 <= len(value) <= 180 and lower_value not in seen:
            seen.add(value.lower())
            cleaned.append(value)
    return cleaned[:8]


def derive_workflow_steps(items: list[dict]) -> list[str]:
    for item in items:
        text = _normalize_multiline(
            "\n".join(chunk.get("text", "") for chunk in item.get("matched_chunks", [])) or item.get("text", "")
        )
        if "->" in text:
            first_flow = next((line for line in text.splitlines() if "->" in line), "")
            steps = [_clean_text(part) for part in first_flow.split("->")]
            steps = [step for step in steps if step]
            if len(steps) >= 2:
                return steps[:10]
    return []


def llm_status() -> dict:
    api_key = os.getenv("LLM_API_KEY") or os.getenv("MAAS_API_KEY")
    base_url = os.getenv("LLM_BASE_URL") or "https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1"
    model = os.getenv("LLM_MODEL") or "minimax/minimax-m2.5"
    wire_api = os.getenv("LLM_WIRE_API") or ("responses" if os.getenv("MAAS_API_KEY") and not os.getenv("LLM_WIRE_API") else "chat")
    configured = all([api_key, base_url, model])
    return {
        "configured": configured,
        "base_url": base_url if configured else "",
        "model": model if configured else "",
        "wire_api": wire_api,
        "env_key": "LLM_API_KEY" if os.getenv("LLM_API_KEY") else "MAAS_API_KEY",
    }


def _context_for_llm(items: list[dict]) -> str:
    blocks = []
    for item in items:
        chunks = item.get("matched_chunks") or [{"text": item.get("text", "")}]
        for chunk in chunks:
            text = _normalize_multiline(chunk.get("text", ""))
            if text:
                blocks.append(
                    f"Source: {item.get('title', 'Untitled')} | Type: {item.get('type', 'document')} | "
                    f"Chunk: {chunk.get('chunk_id', 'full')}\n{text}"
                )
    return "\n\n---\n\n".join(blocks)[:MAX_CONTEXT_CHARS]


def _coerce_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_clean_text(item) for item in value if _clean_text(item)]
    if isinstance(value, dict):
        items = []
        for key, item_value in value.items():
            if isinstance(item_value, (list, dict)):
                item_text = json.dumps(item_value, ensure_ascii=False)
            else:
                item_text = _clean_text(item_value)
            key_text = _clean_text(key)
            if key_text and item_text:
                items.append(f"{key_text}: {item_text}")
        return items
    text = _clean_text(value)
    return [text] if text else []


def _sanitize_test_case(raw_case: dict, fallback_index: int) -> dict:
    return {
        "id": _clean_text(raw_case.get("id")) or f"TC-LLM-{fallback_index:03d}",
        "title": _clean_text(raw_case.get("title")) or "Generated test case",
        "type": _clean_text(raw_case.get("type")) or "Functional",
        "priority": _clean_text(raw_case.get("priority")) or "Medium",
        "preconditions": _coerce_list(raw_case.get("preconditions")),
        "test_data": _coerce_list(raw_case.get("test_data")),
        "steps": _coerce_list(raw_case.get("steps")),
        "expected_result": _clean_text(raw_case.get("expected_result")) or "Expected behavior is observed.",
        "references": _coerce_list(raw_case.get("references")),
    }


def _parse_llm_json(content: str) -> dict:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE | re.DOTALL).strip()

    decoder = json.JSONDecoder()
    candidates = [content]

    first_brace = content.find("{")
    last_brace = content.rfind("}")
    if first_brace >= 0 and last_brace > first_brace:
        candidates.append(content[first_brace : last_brace + 1])
        candidates.append(content[first_brace:])

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc
            try:
                parsed, _ = decoder.raw_decode(candidate)
            except json.JSONDecodeError as raw_exc:
                last_error = raw_exc
                continue
        if isinstance(parsed, dict):
            return parsed

    raise ValueError(f"Could not parse LLM JSON response: {last_error}")


def _enhance_with_llm(response: dict, payload: dict, context_items: list[dict]) -> dict:
    status = llm_status()
    if not status["configured"]:
        response["ai_mode"] = "fallback-no-llm-config"
        response["ai_status"] = status
        return response

    try:
        import httpx

        base_url = status["base_url"].rstrip("/")
        api_key = os.getenv("LLM_API_KEY") or os.getenv("MAAS_API_KEY", "")
        model = status["model"]
        wire_api = status["wire_api"]
        context = _context_for_llm(context_items)
        fallback_cases = response.get("test_cases", [])

        prompt_text = (
            "You are a senior QC test design assistant. Use the filtered business context to improve "
            "the provided test cases. Return ONLY valid JSON with keys test_cases and notes. "
            "Each test case must include id, title, type, priority, preconditions, test_data, steps, "
            "expected_result, references. Do not invent facts outside the context.\n\n"
            f"Feature payload:\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
            f"Filtered context chunks:\n{context or 'No context matched.'}\n\n"
            f"Baseline test cases:\n{json.dumps(fallback_cases, ensure_ascii=False, indent=2)}"
        )

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if wire_api == "responses":
            llm_response = httpx.post(
                f"{base_url}/responses",
                headers=headers,
                json={
                    "model": model,
                    "input": [
                        {
                            "role": "system",
                            "content": "Return compact, valid JSON only. No markdown fences.",
                        },
                        {
                            "role": "user",
                            "content": prompt_text,
                        },
                    ],
                    "temperature": 0.2,
                    "max_output_tokens": 6000,
                },
                timeout=45,
            )
        else:
            llm_response = httpx.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "Return compact, valid JSON only. No markdown fences.",
                        },
                        {
                            "role": "user",
                            "content": prompt_text,
                        },
                    ],
                    "temperature": 0.2,
                },
                timeout=45,
            )
        llm_response.raise_for_status()
        llm_payload = llm_response.json()
        if wire_api == "responses":
            content = (
                llm_payload.get("output_text")
                or "".join(
                    part.get("text", "")
                    for item in llm_payload.get("output", [])
                    for part in item.get("content", [])
                    if part.get("type") in {"output_text", "text"}
                )
            )
        else:
            content = llm_payload["choices"][0]["message"]["content"]

        parsed = _parse_llm_json(content)
        if isinstance(parsed.get("test_cases"), list) and parsed["test_cases"]:
            sanitized_cases = [
                _sanitize_test_case(test_case, index)
                for index, test_case in enumerate(parsed["test_cases"], start=1)
                if isinstance(test_case, dict)
            ]
            if not sanitized_cases:
                raise ValueError("LLM response did not include valid test case objects.")
            response["test_cases"] = sanitized_cases
            response["notes"] = _coerce_list(parsed.get("notes")) or response.get("notes", [])
            response["ai_mode"] = "llm-rag"
            response["ai_status"] = status
            return response
        raise ValueError("LLM response did not include test_cases.")
    except Exception as exc:
        response["ai_mode"] = "fallback-llm-error"
        response["ai_error"] = str(exc)
        response["ai_status"] = status
        return response


def build_test_cases(payload: dict) -> dict:
    feature = _clean_text(payload.get("feature") or payload.get("message") or payload.get("requirement"))
    if not feature:
        feature = "Unspecified feature"

    actor = _clean_text(payload.get("actor") or payload.get("user_role") or "User")
    platform = _clean_text(payload.get("platform") or "Target application")
    criteria = _split_acceptance_criteria(payload.get("acceptance_criteria") or payload.get("criteria"))

    query = " ".join([feature, actor, platform, " ".join(criteria)])
    context_items = retrieve_context(query)
    context_summary = summarize_context(context_items)
    context_refs = [f"{item.get('title', 'Untitled')} ({item.get('type', 'document')})" for item in context_items]

    if not criteria:
        criteria = derive_criteria_from_context(context_items)

    workflow_steps = derive_workflow_steps(context_items)
    feature_key = _slug(feature)

    cases = [
        _case(
            f"TC-{feature_key}-001",
            f"{actor} can complete the happy path for {feature}",
            "Positive",
            "High",
            [
                f"Open {platform} with a valid {actor} account.",
                f"Navigate to the {feature} flow.",
                "Prepare data according to the trained business document.",
                "Submit or complete the action.",
            ],
            f"The {feature} action completes successfully and the system matches the documented workflow.",
            context_refs,
        ),
        _case(
            f"TC-{feature_key}-002",
            f"Required validation is shown for missing or invalid data in {feature}",
            "Negative",
            "High",
            [
                f"Open the {feature} flow.",
                "Leave mandatory fields empty or provide invalid values from the trained rules.",
                "Submit the form or trigger the action.",
            ],
            "The system blocks submission and shows clear validation messages near the invalid fields.",
            context_refs,
        ),
        _case(
            f"TC-{feature_key}-003",
            f"Boundary values are handled correctly for {feature}",
            "Boundary",
            "Medium",
            [
                f"Open the {feature} flow.",
                "Enter minimum allowed values and submit.",
                "Repeat with maximum allowed values.",
                "Repeat with values just outside the allowed range.",
            ],
            "Allowed boundary values are accepted; out-of-range values are rejected with understandable errors.",
            context_refs,
        ),
        _case(
            f"TC-{feature_key}-004",
            f"Unauthorized access is prevented for {feature}",
            "Permission",
            "High",
            [
                "Sign in with an account that should not have access to this feature.",
                f"Attempt to open or execute the {feature} flow.",
            ],
            "The system denies access without exposing sensitive data or allowing the action to complete.",
            context_refs,
        ),
        _case(
            f"TC-{feature_key}-005",
            f"System handles interruption or failure during {feature}",
            "Resilience",
            "Medium",
            [
                f"Start the {feature} flow with valid data.",
                "Simulate a timeout, refresh, duplicate submit, or network interruption.",
                "Return to the feature and verify the final state.",
            ],
            "The system prevents duplicate/partial inconsistent results and gives the user a recoverable state.",
            context_refs,
        ),
    ]

    if workflow_steps:
        cases.append(
            _case(
                f"TC-{feature_key}-006",
                f"Workflow transitions follow the trained diagram for {feature}",
                "Workflow",
                "High",
                [f"Verify workflow step: {step}." for step in workflow_steps],
                "Each transition follows the trained workflow and invalid transitions are not allowed.",
                context_refs,
            )
        )

    start_index = 7 if workflow_steps else 6
    for index, criterion in enumerate(criteria, start=start_index):
        cases.append(
            _case(
                f"TC-{feature_key}-{index:03d}",
                f"Acceptance criterion is satisfied: {criterion}",
                "Acceptance",
                "High",
                [
                    f"Prepare data and user state for: {criterion}.",
                    f"Execute the {feature} behavior related to this criterion.",
                    "Observe system response, stored data, events, and user-visible result.",
                ],
                f"The system behavior matches the acceptance criterion: {criterion}.",
                context_refs,
            )
        )

    response = {
        "status": "success",
        "generated_at": datetime.now().isoformat(),
        "feature": feature,
        "actor": actor,
        "platform": platform,
        "context_summary": context_summary,
        "source_refs": [
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "type": item.get("type"),
                "source": item.get("source"),
                "matched_chunks": [
                    {
                        "chunk_id": chunk.get("chunk_id"),
                        "preview": chunk.get("preview"),
                        "score": chunk.get("score"),
                    }
                    for chunk in item.get("matched_chunks", [])
                ],
            }
            for item in context_items
        ],
        "test_cases": cases,
        "quality_checklist": QUALITY_CHECKLIST,
        "notes": [
            "Upload requirement documents, workflow exports, diagrams, or business rules before generating final test cases.",
            "Image-only diagrams need OCR/vision integration; export them as SVG, drawio, Mermaid, BPMN, PDF, or paste the flow text for best local results.",
        ],
    }
    return _enhance_with_llm(response, payload, context_items)


def _decode_bytes(data: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def _strip_markup(text: str) -> str:
    text = unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    return _normalize_multiline(text)


def _strip_markdown(text: str) -> str:
    # Fenced code blocks: keep content, remove fences
    text = re.sub(r"^```[^\n]*\n(.*?)```", lambda m: m.group(1), text, flags=re.MULTILINE | re.DOTALL)
    # Inline code
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # ATX headers
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Setext headers
    text = re.sub(r"^[=\-]{3,}\s*$", "", text, flags=re.MULTILINE)
    # Bold/italic
    text = re.sub(r"\*{1,3}([^*\n]+)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,3}([^_\n]+)_{1,3}", r"\1", text)
    # Images before links
    text = re.sub(r"!\[([^\]]*)\]\([^\)]*\)", r"\1", text)
    # Links
    text = re.sub(r"\[([^\]]+)\]\([^\)]*\)", r"\1", text)
    # Blockquotes
    text = re.sub(r"^>\s*", "", text, flags=re.MULTILINE)
    # Horizontal rules
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
    # HTML tags
    text = re.sub(r"<[^>]+>", " ", text)
    # List markers (- item, * item, 1. item)
    text = re.sub(r"^[\s]*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[\s]*\d+\.\s+", "", text, flags=re.MULTILINE)
    return _normalize_multiline(text)


def _max_upload_bytes() -> int:
    raw = os.getenv("MAX_UPLOAD_BYTES", str(DEFAULT_MAX_UPLOAD_BYTES))
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_MAX_UPLOAD_BYTES


def _format_bytes(value: int) -> str:
    if value >= 1024 * 1024:
        return f"{value / (1024 * 1024):.1f} MB"
    if value >= 1024:
        return f"{value / 1024:.1f} KB"
    return f"{value} bytes"


def _write_temp_upload(data: bytes, suffix: str) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(delete=False, dir=DATA_DIR, suffix=suffix) as temp_file:
        temp_file.write(data)
        return Path(temp_file.name)


def _extract_docx(data: bytes) -> str:
    try:
        from docx import Document
    except ImportError as exc:
        raise ValueError("python-docx is not installed. Run: venv/bin/pip install -r requirements.txt") from exc

    temp_path = _write_temp_upload(data, ".docx")
    try:
        document = Document(str(temp_path))
        paragraphs = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
        for table in document.tables:
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if cells:
                    paragraphs.append(" | ".join(cells))
        return _normalize_multiline("\n".join(paragraphs))
    finally:
        temp_path.unlink(missing_ok=True)


def _extract_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ValueError("pypdf is not installed. Run: venv/bin/pip install -r requirements.txt") from exc

    temp_path = _write_temp_upload(data, ".pdf")
    try:
        reader = PdfReader(str(temp_path))
        pages = [page.extract_text() or "" for page in reader.pages]
        return _normalize_multiline("\n".join(pages))
    finally:
        temp_path.unlink(missing_ok=True)


def _extract_xlsx(data: bytes) -> str:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise ValueError("openpyxl is not installed. Run: venv/bin/pip install -r requirements.txt") from exc

    temp_path = _write_temp_upload(data, ".xlsx")
    try:
        workbook = load_workbook(str(temp_path), read_only=True, data_only=True)
        rows = []
        for sheet in workbook.worksheets:
            rows.append(f"Sheet: {sheet.title}")
            for row in sheet.iter_rows(values_only=True):
                values = [_clean_text(value) for value in row if value is not None and _clean_text(value)]
                if values:
                    rows.append(" | ".join(values))
        return _normalize_multiline("\n".join(rows))
    finally:
        temp_path.unlink(missing_ok=True)


def extract_file_text(filename: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {suffix or 'unknown'}")

    if suffix in IMAGE_EXTENSIONS:
        raise ValueError("Image diagram uploaded but OCR/vision is not configured, so the content cannot be read yet.")

    if suffix == ".pdf":
        return _extract_pdf(data)
    if suffix == ".docx":
        return _extract_docx(data)
    if suffix == ".xlsx":
        return _extract_xlsx(data)

    text = _decode_bytes(data)
    if suffix in {".md"}:
        stripped = _strip_markdown(text)
        return stripped if stripped else _normalize_multiline(text)

    if suffix in {".xml", ".svg", ".drawio", ".bpmn"}:
        try:
            root = ElementTree.fromstring(text)
            xml_texts = [element.text.strip() for element in root.iter() if element.text and element.text.strip()]
            attributes = [str(value) for element in root.iter() for value in element.attrib.values() if value]
            text = "\n".join(xml_texts + attributes) or text
        except ElementTree.ParseError:
            pass
        return _strip_markup(text)

    if suffix == ".json":
        try:
            parsed = json.loads(text)
            return _normalize_multiline(json.dumps(parsed, indent=2, ensure_ascii=False))
        except json.JSONDecodeError:
            return _normalize_multiline(text)

    return _normalize_multiline(text)


async def chat_page(request: Request) -> HTMLResponse:
    return HTMLResponse(CHAT_HTML)


async def chat_api(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON payload"}, status_code=400)

    if not isinstance(payload, dict):
        return JSONResponse({"error": "Payload must be a JSON object"}, status_code=400)

    try:
        return JSONResponse(build_test_cases(payload))
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


async def ai_status_api(request: Request) -> JSONResponse:
    return JSONResponse(llm_status())


async def knowledge_list_api(request: Request) -> JSONResponse:
    items = []
    try:
        knowledge_items = _read_knowledge()
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)

    for item in knowledge_items:
        items.append(
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "type": item.get("type"),
                "source": item.get("source"),
                "text": item.get("text", ""),
                "text_length": item.get("text_length", len(item.get("text", ""))),
                "chunk_count": len(item.get("chunks") or _chunk_text(item.get("text", ""))),
                "preview": item.get("preview") or _preview(item.get("text", "")),
                "status": item.get("status", READY),
                "status_message": item.get("status_message", "Readable and indexed."),
                "readable": item.get("readable", True),
                "created_at": item.get("created_at"),
            }
        )
    return JSONResponse({"items": items})


async def knowledge_action_api(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON payload"}, status_code=400)

    knowledge_id = _clean_text(payload.get("id"))
    action = _clean_text(payload.get("action"))
    if not knowledge_id or not action:
        return JSONResponse({"error": "Both id and action are required."}, status_code=400)

    try:
        item = update_knowledge_item(knowledge_id, action, payload.get("text"))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)

    return JSONResponse({"item": item})


async def knowledge_create_api(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON payload"}, status_code=400)

    knowledge_type = str(payload.get("type", "document"))
    if knowledge_type == "diagram":
        try:
            item = add_knowledge(
                title=payload.get("title", "Untitled diagram"),
                knowledge_type=knowledge_type,
                text="Diagram was submitted through the text API. Upload the original diagram file so it can be parsed or marked for OCR/vision review.",
                source=payload.get("source", "pasted-text"),
                status=NEEDS_REVIEW,
                status_message="Diagram text paste is disabled. Upload SVG/drawio/BPMN/Mermaid/PDF, or connect OCR/vision for image diagrams.",
                readable=False,
            )
        except RuntimeError as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)
        return JSONResponse({"item": item}, status_code=202)

    try:
        item = add_knowledge(
            title=payload.get("title", "Untitled knowledge"),
            knowledge_type=knowledge_type,
            text=payload.get("text", ""),
            source=payload.get("source", "manual"),
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)

    return JSONResponse({"item": item})


async def knowledge_upload_api(request: Request) -> JSONResponse:
    max_upload_bytes = _max_upload_bytes()
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > max_upload_bytes:
                return JSONResponse(
                    {"error": f"Upload is too large. Maximum size is {_format_bytes(max_upload_bytes)}."},
                    status_code=413,
                )
        except ValueError:
            return JSONResponse({"error": "Invalid Content-Length header."}, status_code=400)

    try:
        form = await request.form()
    except Exception as exc:
        return JSONResponse({"error": f"Could not read upload form: {exc}"}, status_code=400)

    upload = form.get("file")
    if upload is None:
        return JSONResponse({"error": "Missing file upload"}, status_code=400)

    filename = getattr(upload, "filename", "uploaded-file")
    suffix = Path(filename).suffix.lower()
    try:
        data = await upload.read()
        if not data:
            return JSONResponse({"error": "Uploaded file is empty."}, status_code=400)
        if len(data) > max_upload_bytes:
            return JSONResponse(
                {"error": f"Upload is too large. Maximum size is {_format_bytes(max_upload_bytes)}."},
                status_code=413,
            )
        if suffix in IMAGE_EXTENSIONS:
            item = add_knowledge(
                title=str(form.get("title") or filename),
                knowledge_type=str(form.get("type") or "diagram"),
                text=f"Image diagram file uploaded: {filename}. OCR/vision is not configured in this local version, so the visual content was not extracted.",
                source=filename,
                status=NEEDS_REVIEW,
                status_message="Saved, but not indexed. Export diagram as SVG/drawio/BPMN/Mermaid/PDF or connect OCR/vision.",
                readable=False,
            )
            return JSONResponse({"item": item}, status_code=202)

        text = extract_file_text(filename, data)
        item = add_knowledge(
            title=str(form.get("title") or filename),
            knowledge_type=str(form.get("type") or "document"),
            text=text,
            source=filename,
        )
    except ValueError as exc:
        item = add_knowledge(
            title=str(form.get("title") or filename),
            knowledge_type=str(form.get("type") or "document"),
            text=f"File upload could not be indexed: {filename}. Reason: {exc}",
            source=filename,
            status=FAILED,
            status_message=str(exc),
            readable=False,
        )
        return JSONResponse({"item": item}, status_code=202)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
    except Exception as exc:
        return JSONResponse({"error": f"Could not train file: {exc}"}, status_code=500)

    return JSONResponse({"item": item})


app.add_route("/", chat_page, methods=["GET"])
app.add_route("/invocations", chat_page, methods=["GET"])
app.add_route("/chat", chat_api, methods=["POST"])
app.add_route("/ai/status", ai_status_api, methods=["GET"])
app.add_route("/knowledge", knowledge_list_api, methods=["GET"])
app.add_route("/knowledge", knowledge_create_api, methods=["POST"])
app.add_route("/knowledge/upload", knowledge_upload_api, methods=["POST"])
app.add_route("/knowledge/action", knowledge_action_api, methods=["POST"])


@app.entrypoint
def handler(payload: dict, context: RequestContext) -> dict:
    """Generate structured QC test cases from feature, requirement, and trained knowledge."""
    result = build_test_cases(payload)
    result["session_id"] = context.session_id
    return result


@app.ping
def health_check() -> PingStatus:
    """Health check for GET /health."""
    return PingStatus.HEALTHY


if __name__ == "__main__":
    app.run(port=8080, host="0.0.0.0")
