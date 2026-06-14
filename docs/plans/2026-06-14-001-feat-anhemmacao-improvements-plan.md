---
title: "feat: Cải tiến toàn diện AnhEmMacao"
date: 2026-06-14
origin: docs/brainstorms/2026-06-14-anhemmacao-improvements-requirements.md
type: feat
depth: standard
---

# feat: Cải tiến toàn diện AnhEmMacao

**Ngày:** 2026-06-14
**Nguồn:** `docs/brainstorms/2026-06-14-anhemmacao-improvements-requirements.md`
**Loại:** feat | Standard

---

## Summary

Năm cải tiến có thứ tự cho AnhEmMacao — công cụ sinh test case tự động nội bộ. Các cải tiến được thiết kế để ship độc lập, theo thứ tự ưu tiên: export CSV (giá trị tức thì), technical hygiene (nền tảng), vision/OCR (giảm thủ công), custom test types (linh hoạt), và cải thiện retrieval/prompt (chất lượng).

---

## Problem Frame

AnhEmMacao sinh test case từ tài liệu tính năng nhưng có năm rào cản cản trở quy trình QC hàng ngày: (1) kết quả chỉ hiển thị trên UI, không xuất được; (2) ảnh/diagram không đọc được, tạo NEEDS_REVIEW tồn đọng; (3) loại test case cố định không phản ánh đặc thù dự án; (4) keyword retrieval bỏ sót context liên quan; (5) `fcntl` không chạy trên Windows. Mỗi vấn đề là độc lập, có thể giải quyết theo thứ tự mà không cần rewrite toàn bộ.

---

## Requirements

Từ requirements document (see origin: `docs/brainstorms/2026-06-14-anhemmacao-improvements-requirements.md`):

- **R1** — Export CSV với UTF-8 BOM, đủ cột để QA review trong Google Sheets
- **R2** — Steps trong CSV: tất cả bước gộp trong một ô, cách nhau bằng newline
- **R3** — Tên file mặc định: `testcases-YYYY-MM-DD-HH-MM.csv`
- **R4** — Vision integration opt-in qua env var; nếu không cấu hình, fallback về NEEDS_REVIEW như hiện tại
- **R5** — Custom test case types qua config file; khi không có config, dùng 6 loại mặc định hiện tại
- **R6** — Thay `fcntl` bằng `filelock` — cross-platform, Windows-compatible
- **R7** — Tăng `TOP_CONTEXT_CHUNKS` 6→10, `MAX_CONTEXT_CHARS` 4200→6000
- **R8** — Cải thiện chunk scoring: ratio-based thay vì đếm tuyệt đối
- **R9** — Deduplication: bỏ test case trùng lặp trong cùng một response
- **R10** — Unit tests cho `_keywords`, `_chunk_text`, `_chunk_score`, `retrieve_context`

---

## Key Technical Decisions

**KTD1 — CSV export gửi test cases từ client hay re-generate server-side?**
Client gửi lại danh sách test cases trong POST body (`/export/csv`). Re-generate sẽ tốn LLM call, và kết quả có thể khác. Client đã có JSON trong bộ nhớ từ `/chat` response, gửi lại là đơn giản nhất. (see origin: R1–R3)

**KTD2 — Vision API: chat completions wire API thay vì responses wire API.**
MiniMax M2.5 vision support chưa xác minh. OpenAI chat completions format phổ biến hơn và tương thích với nhiều provider (OpenAI, Azure, Groq, Gemini). Vision chỉ kích hoạt khi `LLM_WIRE_API=chat` VÀ `LLM_VISION_ENABLED=true`. Responses wire API được bỏ qua cho vision, có thể bổ sung sau khi xác nhận MiniMax support. (see origin: Câu hỏi còn mở #1)

**KTD3 — Custom test case types: JSON, không phải YAML.**
Không cần thêm dependency mới (`pyyaml`). JSON đủ cho cấu trúc đơn giản (type, priority, prompt template). File ở `.agentbase/testcase_types.json` để cùng thư mục với `knowledge.json`. Fallback về 6 loại mặc định khi file không tồn tại. (see origin: R5)

**KTD4 — Unit tests: `pytest` trong `tests/test_core.py`.**
Import trực tiếp từ `main.py`. Không cần refactor kiến trúc. `pytest` và `pytest-mock` được thêm vào `requirements-dev.txt` mới — tách biệt với `requirements.txt` production.

**KTD5 — Chunk scoring ratio-based: chia cho tổng keywords trong chunk.**
Thay vì `+3 per overlapping keyword` (tuyệt đối, thiên về chunk dài), dùng `score = (overlap_count / max(len(chunk_keywords), 1)) * 10` như base score + các bonus hiện có. Chunks ngắn, focused sẽ score cao hơn khi keyword match tỷ lệ cao.

---

## High-Level Technical Design

### Luồng export CSV

```
[Browser] POST /export/csv {test_cases: [...]}
     |
     ↓
[export_csv_api] → csv.writer → io.StringIO → encode UTF-8 BOM
     |
     ↓
Response(Content-Type: text/csv, Content-Disposition: attachment)
     |
     ↓
[Browser] downloads file → QA opens in Google Sheets
```

### Luồng vision cho ảnh upload

```
[knowledge_upload_api] receives PNG/JPG/WebP
     |
     ↓
llm_status() → check LLM_VISION_ENABLED + wire_api == "chat"
     |
   YES → _extract_image_via_vision(data, media_type)
     |         |
     |         ↓ POST /chat/completions with base64 image
     |         |
     |         ↓ returns extracted text
     |
     ↓ save as READY knowledge item
     |
   NO  → save as NEEDS_REVIEW (existing behavior)
```

### Luồng load custom test case types

```
build_test_cases() calls load_test_case_types()
     |
     ↓
try: read .agentbase/testcase_types.json
     |
   EXISTS → parse list of {type, priority, steps_template, condition}
     |
   MISSING → return DEFAULT_TEST_CASE_TYPES (6 loại hiện tại)
     |
     ↓
loop over types → generate _case(...) for each enabled type
```

---

## Implementation Units

### U1. CSV Export — Endpoint và UI button

**Goal:** Team QC có thể download kết quả test case ra CSV và mở trong Google Sheets để review.

**Requirements:** R1, R2, R3

**Dependencies:** Không có

**Files:**
- `main.py` — thêm `export_csv_api` handler và route
- `requirements.txt` — không cần thêm (csv là stdlib)

**Approach:**
- Handler `export_csv_api` nhận POST với JSON body `{"test_cases": [...], "feature": "..."}`.
- Dùng `csv.writer` + `io.StringIO`. Columns: `ID`, `Title`, `Type`, `Priority`, `Preconditions`, `Test Data`, `Steps`, `Expected Result`, `References`.
- `Steps` field: join danh sách bước bằng `\n` thành single string — Google Sheets parse quoted multi-line cells đúng.
- Encode output: `"﻿" + sio.getvalue()` → bytes, UTF-8 BOM để Google Sheets nhận diện encoding.
- Response: `Content-Type: text/csv; charset=utf-8-sig`, `Content-Disposition: attachment; filename="testcases-YYYY-MM-DD-HH-MM.csv"`.
- Filename timestamp: dùng `datetime.now()` formatted `%Y-%m-%d-%H-%M`.
- Thêm route: `app.add_route("/export/csv", export_csv_api, methods=["POST"])`.
- UI (`CHAT_HTML` embedded string): thêm nút "Export CSV" trong toolbar div (gần dòng 413). Khi click, JS gọi POST `/export/csv` với `test_cases` từ state hiện tại, trigger browser download.

**Patterns to follow:** Xem route handlers hiện tại (lines 1577–1763) — async def, Request → JSONResponse. Export trả `Response` thay vì `JSONResponse`.

**Test scenarios:**
- Happy path: POST với 5 test cases → response có header `text/csv`, filename đúng format, UTF-8 BOM (`\xef\xbb\xbf` ở đầu), 5 data rows + 1 header row
- Steps multi-line: test case với 3 steps → ô Steps trong CSV chứa text với 2 `\n` characters, Google Sheets hiển thị multi-line khi mở
- Empty test cases: POST với `test_cases: []` → CSV với chỉ header row, không error
- Vietnamese content: title và steps có dấu tiếng Việt → không bị lỗi encoding khi mở Google Sheets
- Missing fields: test case thiếu `test_data` → output CSV ô đó trống, không crash

**Verification:** Download CSV từ UI, mở trong Google Sheets, thấy đúng 9 cột, tiếng Việt hiển thị đúng, Steps hiển thị multi-line trong một ô.

---

### U2. Cross-platform file locking với filelock

**Goal:** AnhEmMacao chạy được trên Windows (thay `fcntl` — Linux-only).

**Requirements:** R6

**Dependencies:** Không có

**Files:**
- `requirements.txt` — thêm `filelock`
- `main.py` — thay đổi import và `_knowledge_lock()`

**Approach:**
- Xóa `import fcntl` (line 12).
- Thêm `from filelock import FileLock` ở vị trí đó.
- Rewrite `_knowledge_lock()` (lines 759–768): thay toàn bộ body bằng `lock_path = KNOWLEDGE_DIR / "knowledge.lock"; return FileLock(str(lock_path))`. `FileLock` là context manager, trả về trực tiếp thay vì `yield`.
- Tất cả callers (`add_knowledge`, `update_knowledge_item`, `_read_knowledge`, `_write_knowledge`) dùng `with _knowledge_lock():` — API không đổi.
- Thêm `filelock` vào `requirements.txt`.
- Cập nhật `Dockerfile`: `RUN pip install -r requirements.txt` — không cần thay đổi gì thêm.

**Patterns to follow:** `_knowledge_lock()` là context manager — `FileLock` implement `__enter__`/`__exit__` nên thay thế trực tiếp.

**Test scenarios:**
- Import thành công trên Windows: `from filelock import FileLock` không raise ImportError
- Concurrent write: hai async tasks đồng thời gọi `add_knowledge` → chỉ một task write tại một thời điểm, không data corruption
- Lock release on exception: nếu write operation raise exception, lock được release (FileLock context manager đảm bảo này)
- Backward compatibility: lock file `.agentbase/knowledge.lock` vẫn được tạo đúng chỗ

**Verification:** Chạy ứng dụng trên Windows, upload knowledge và generate test cases — không có `ImportError` hay `AttributeError`.

---

### U3. Unit tests cho core functions

**Goal:** Các hàm core có test coverage, phát hiện regression khi cải tiến U5 và U6 chỉnh scoring/chunking.

**Requirements:** R10

**Dependencies:** U2 (filelock thay fcntl trước để test có thể import main.py trên Windows)

**Files:**
- `tests/__init__.py` — file rỗng
- `tests/test_core.py` — test suite chính
- `requirements-dev.txt` — pytest, pytest-mock

**Approach:**
- `tests/test_core.py` import trực tiếp: `from main import _keywords, _chunk_text, _chunk_score, retrieve_context`
- Dùng `pytest-mock` (mocker fixture) để patch `_read_knowledge` trong `retrieve_context` tests.
- Tổ chức theo 4 nhóm `class Test<FunctionName>`.
- Không cần test LLM calls hay HTTP routes trong unit test scope này.

**Test scenarios:**

*`_keywords`:*
- Input rỗng → empty set
- Input chỉ stopwords (`"và", "the", "is"`) → empty set
- Input `"đăng nhập thất bại"` → set chứa `"đăng"`, `"nhập"`, `"thất"`, `"bại"` (không có stopwords)
- Từ ngắn hơn 3 ký tự bị loại: `"ab"` → không trong result
- Hyphenated word `"test-case"` → `"test-case"` trong result (regex `[\w-]{3,}`)

*`_chunk_text`:*
- Text ngắn hơn CHUNK_SIZE → trả về 1 chunk
- Text có 3 đoạn ngăn cách bằng `\n\n` → trả về 3 chunks
- Đoạn dài hơn CHUNK_SIZE → bị cắt thành nhiều chunks, mỗi chunk ≤ CHUNK_SIZE chars
- Overlap: chunk thứ hai bắt đầu bằng `CHUNK_OVERLAP` ký tự cuối của chunk trước
- Mỗi chunk có đủ keys: `chunk_id`, `text`, `keywords`, `preview`

*`_chunk_score`:*
- Zero overlap → score 0 (trừ khi full query match)
- Full query string là substring của chunk text → score +10
- 3 overlapping keywords → score tăng proportionally
- Title keyword match → score +2 per matching keyword
- Sau U6: ratio-based scoring — chunk 3 keywords overlap / 3 total > chunk 3 overlap / 10 total

*`retrieve_context`:*
- Knowledge store rỗng (mock trả `[]`) → trả `[]`
- Item có `status != "READY"` → bị bỏ qua
- Item có `readable == False` → bị bỏ qua
- Query khớp 1 item → trả list với 1 item, có `matched_chunks` và `match_score`
- `limit=2` với 5 matching items → chỉ trả 2 item có score cao nhất

**Verification:** `pytest tests/` chạy xanh trên cả Linux và Windows. Tất cả assertions pass.

---

### U4. Vision/OCR cho ảnh upload

**Goal:** Ảnh PNG, JPG, WebP được trích xuất nội dung tự động khi cấu hình vision — xóa NEEDS_REVIEW tồn đọng.

**Requirements:** R4

**Dependencies:** U2 (fcntl thay thế trước để tránh issue trên Windows khi test)

**Files:**
- `main.py` — thêm `_extract_image_via_vision()`, cập nhật `knowledge_upload_api` và `extract_file_text`
- `.env.example` — thêm `LLM_VISION_ENABLED=false`

**Approach:**
- Thêm hàm `_extract_image_via_vision(data: bytes, media_type: str) -> str`:
  - Chỉ hoạt động khi `llm_status()["available"] == True` VÀ `LLM_WIRE_API == "chat"` VÀ `LLM_VISION_ENABLED == "true"` (env var).
  - Build httpx POST tới `{LLM_BASE_URL}/chat/completions` với body: `{"model": ..., "messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:{media_type};base64,{base64data}"}}, {"type": "text", "text": "Extract all text content from this image for QA documentation..."}]}]}`.
  - Trả về content string từ response `choices[0].message.content`.
  - Timeout: 30 giây. Nếu exception → raise `ValueError` để caller fallback về NEEDS_REVIEW.
- Cập nhật `extract_file_text` (lines 1546–1547): với image extensions (`.png`, `.jpg`, `.jpeg`, `.webp`), thử gọi `_extract_image_via_vision()` trước; nếu raise `ValueError` hoặc vision không enabled → raise `ValueError("vision-not-available")` như hiện tại.
- Cập nhật `knowledge_upload_api` (lines 1718–1728): phân biệt `ValueError("vision-not-available")` (→ NEEDS_REVIEW) với các lỗi khác (→ FAILED).
- UI: cập nhật message NEEDS_REVIEW để chỉ hiện khi `LLM_VISION_ENABLED != true`.

**Patterns to follow:** `_enhance_with_llm` (lines 1184–1290) — cùng pattern httpx POST + error handling + env var check.

**Test scenarios:**
- Vision disabled (`LLM_VISION_ENABLED=false`): upload PNG → status `NEEDS_REVIEW`, không gọi LLM
- Vision enabled, model có vision: upload JPG → gọi `_extract_image_via_vision`, extract text thành công → status `READY`, content có text
- Vision enabled nhưng LLM timeout: → fallback `NEEDS_REVIEW`, không crash
- Vision enabled nhưng `LLM_WIRE_API=responses`: → không kích hoạt vision (chỉ hỗ trợ chat wire API), trả `NEEDS_REVIEW`
- Media type đúng: PNG → `image/png`, JPEG → `image/jpeg`, WebP → `image/webp` trong base64 data URL
- LLM trả empty string: → raise ValueError, fallback NEEDS_REVIEW

**Verification:** Set `LLM_VISION_ENABLED=true` + OpenAI-compatible API key. Upload screenshot Figma → knowledge item có status `READY` với content là text mô tả ảnh. Upload PNG khi vision disabled → vẫn `NEEDS_REVIEW`.

---

### U5. Custom test case types qua config file

**Goal:** Team thêm loại test case mới (Security, Performance...) không cần sửa code.

**Requirements:** R5

**Dependencies:** U3 (unit tests tạo test coverage trước khi refactor build_test_cases)

**Files:**
- `main.py` — thêm `load_test_case_types()`, refactor `build_test_cases` (lines 1313–1393)
- `.agentbase/testcase_types.json` — config file mẫu (tạo nếu team muốn customize)
- `docs/testcase_types_example.json` — ví dụ config cho team tham khảo

**Approach:**
- Định nghĩa `DEFAULT_TEST_CASE_TYPES: list[dict]` constant — 6 loại hiện tại, dạng cấu trúc mới.
- Mỗi type entry: `{"type": "Positive", "priority": "High", "enabled": true, "condition": null, "steps_hint": "..."}`.
  - `condition`: `null` (always include) hoặc `"has_workflow"` (chỉ include khi `workflow_steps` non-empty — dùng cho Workflow type).
- Thêm `load_test_case_types() -> list[dict]`: đọc `.agentbase/testcase_types.json`, trả `DEFAULT_TEST_CASE_TYPES` nếu file không tồn tại hoặc invalid JSON.
- Refactor `build_test_cases`: thay 6 `_case(...)` literal calls bằng loop:
  ```
  types = load_test_case_types()
  for i, t in enumerate(types):
      if t.get("condition") == "has_workflow" and not workflow_steps:
          continue
      if not t.get("enabled", True):
          continue
      cases.append(_case(..., type=t["type"], priority=t["priority"], ...))
  ```
- Acceptance-criteria cases vẫn được generate sau loop, không thay đổi.
- Thêm `GET /config/types` route trả về danh sách types hiện tại — UI hoặc API caller có thể query.

**Patterns to follow:** `retrieve_context` pattern — try/except với fallback rõ ràng. File locking không cần cho read-only config.

**Test scenarios:**
- File không tồn tại → `load_test_case_types()` trả DEFAULT_TEST_CASE_TYPES (6 loại), không raise
- File JSON invalid → trả DEFAULT, log warning, không crash
- File có 8 loại (thêm Security, Performance) → `build_test_cases` sinh 8 loại case (+ acceptance cases)
- Type có `"enabled": false` → bị skip, không xuất hiện trong result
- Type có `"condition": "has_workflow"` và không có workflow steps → bị skip
- Type có `"condition": "has_workflow"` và có workflow steps → được include
- `GET /config/types` trả danh sách types từ config hoặc default

**Verification:** Tạo `.agentbase/testcase_types.json` với loại Security thêm vào. Generate test case → thấy test case loại Security trong output. Xóa file → output trở về 6 loại mặc định.

---

### U6. Cải thiện chất lượng retrieval

**Goal:** Retrieval trả về context liên quan hơn, đặc biệt khi knowledge base có nhiều tài liệu.

**Requirements:** R7, R8, R9

**Dependencies:** U3 (unit tests cho _chunk_score đã có trước khi thay đổi scoring logic)

**Files:**
- `main.py` — cập nhật constants (lines 25–28), refactor `_chunk_score` (line 894), thêm deduplication trong `build_test_cases`

**Approach:**
- Tăng constants: `TOP_CONTEXT_CHUNKS = 10` (từ 6), `MAX_CONTEXT_CHARS = 6000` (từ 4200).
- Refactor `_chunk_score` → ratio-based scoring:
  - Base score: `(len(keyword_overlap) / max(len(chunk["keywords"]), 1)) * 10` (thay vì `+3 per keyword`).
  - Giữ bonus: `+10` nếu full query là substring, `+2 per title keyword`, `+1 per type keyword`.
  - Trả về float thay vì int — callers chỉ sort/compare nên không breaking.
- Deduplication trong `build_test_cases`: sau khi sinh all cases, filter bỏ cases có cùng `title` (case-insensitive) hoặc steps giống nhau >90% (simple string comparison đủ, không cần fancy similarity).

**Patterns to follow:** `_chunk_score` hiện tại (line 894) — thay thế trực tiếp, giữ signature.

**Test scenarios:**
- Constants test: `TOP_CONTEXT_CHUNKS == 10`, `MAX_CONTEXT_CHARS == 6000`
- Ratio scoring: chunk với 3/3 keywords match score cao hơn chunk với 3/10 keywords match
- Absolute scoring (cũ): 3/10 > 3/3 vì đếm tuyệt đối — sau thay đổi điều này bị đảo
- Full query bonus vẫn +10: chunk chứa full query string score tăng đúng
- Dedup: 2 cases có cùng title → chỉ giữ 1
- Unique cases: không bị xóa nhầm cases có title khác nhau

**Verification:** Với knowledge base có nhiều tài liệu, generate test case về một feature cụ thể → ít nhất 80% cases liên quan trực tiếp đến feature đó (QA lead review thủ công).

---

### U7. Tinh chỉnh LLM system prompt

**Goal:** Test case được generate chính xác hơn, ít chung chung, phản ánh đúng feature context.

**Requirements:** Cải thiện implicit trong R7 (chất lượng LLM output)

**Dependencies:** U6 (context window lớn hơn sẵn sàng trước khi tinh chỉnh prompt)

**Files:**
- `main.py` — cập nhật `_context_for_llm` hoặc system prompt string trong `_enhance_with_llm` (lines 1090–1180)

**Approach:**
- Thêm explicit instruction vào system prompt: yêu cầu LLM gắn mỗi test case với feature/actor/acceptance criteria cụ thể từ context, không sinh test case generic.
- Thêm instruction: "Mỗi test case phải có ít nhất 3 steps cụ thể, không được viết steps chung chung như 'Perform action' hay 'Check result'."
- Thêm JSON schema hint trong prompt để LLM trả về đúng format, giảm parse error.
- Tăng `max_output_tokens` trong responses wire API từ 6000 lên 8000 để cover nhiều test cases hơn.
- Giữ nguyên fallback behavior: LLM fail → dùng local generation.

**Patterns to follow:** `_context_for_llm` (lines 1090–1180) và system prompt hiện tại trong `_enhance_with_llm`.

**Test scenarios:**
- Prompt có explicit instruction về specificity → LLM-generated cases có steps với action cụ thể
- `max_output_tokens` tăng lên 8000 trong responses API payload
- Fallback vẫn hoạt động: nếu LLM trả invalid JSON → local generation được dùng
- JSON schema hint trong prompt: LLM trả đúng structure, ít parse error hơn

**Verification:** So sánh kết quả trước/sau với cùng một feature description. QA lead nhận xét test cases cụ thể hơn, steps có action rõ ràng. Parse error rate giảm.

---

## Scope Boundaries

### Trong scope
- Tất cả 7 implementation units ở trên
- Backward compatibility hoàn toàn: không breaking change với callers/clients hiện tại
- UI changes nằm trong embedded `CHAT_HTML` string — không tách file riêng

### Deferred to Follow-Up Work
- Tách `CHAT_HTML` ra file `static/index.html` riêng (giảm `main.py` xuống ~600 dòng) — khi team sẵn sàng refactor UI workflow
- MiniMax vision API support — sau khi xác nhận MiniMax M2.5 hỗ trợ vision
- Semantic search với embeddings — sau khi retrieval improvements (U6) được đánh giá
- Database storage thay JSON — khi knowledge base vượt 100 items thường xuyên

### Ngoài scope
- Multi-user authentication/authorization
- Direct push lên Jira/TestRail
- Google Sheets API integration
- Internationalization ngoài tiếng Việt/Anh

---

## Open Questions

1. **MiniMax vision support** (deferred): `minimax/minimax-m2.5` có hỗ trợ image_url trong chat completions không? Nếu có, U4 có thể bỏ điều kiện `LLM_WIRE_API=chat`. — Xác nhận với team trước U4.

2. **Steps format export** (resolved): Single multi-line cell — đã xác nhận với user.

3. **CSV import template** (deferred): Team có muốn CSV format khớp với Jira/TestRail import template cụ thể không? Có thể cần mapping cột đặc biệt.

---

## Risks & Dependencies

| Risk | Mức độ | Mitigation |
|------|--------|------------|
| `httpx` version không hỗ trợ image payload format | Thấp | httpx là transitive dep của greennode-agentbase — pin explicit version khi thêm vision |
| `filelock` conflict với `greennode-agentbase` transitive deps | Thấp | `filelock` không có transitive deps nặng |
| Ratio-based scoring làm thay đổi behavior retrieval | Trung bình | U3 unit tests bắt regression trước khi U6 deploy |
| LLM_VISION_ENABLED + wrong wire API → silent failure | Thấp | Thêm warning log khi vision enabled nhưng wire_api != "chat" |
| `build_test_cases` refactor (U5) break existing logic | Trung bình | U3 tests phải pass trước khi U5 được implement |

---

## Sources & Research

- Grounding dossier từ brainstorm session: `main.py` lines 1-1782 analyzed
- Repository research: exact function signatures, route patterns, dependency file contents
- Requirements document: `docs/brainstorms/2026-06-14-anhemmacao-improvements-requirements.md`
- External research: không cần — local patterns đủ rõ cho tất cả 5 cải tiến
