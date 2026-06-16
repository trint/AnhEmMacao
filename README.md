# QC Test Case Agent

Agent hỗ trợ QC/QA biến **feature, requirement, acceptance criteria, workflow và diagram** thành **bộ test case có cấu trúc**. Agent học từ tài liệu nghiệp vụ bạn nạp vào (RAG) và có thể tự sinh test case bằng kiến thức QC khi chưa có tài liệu.

Hệ thống xây trên **GreenNode AgentBase**, vừa có **web UI** để dùng trực tiếp, vừa có endpoint `/invocations` để chạy như một agent trên AgentBase.

---

## 1. Hệ thống làm gì

- **Sinh test case có cấu trúc**: mỗi case gồm id, title, type, priority, preconditions, test data, steps, expected result, references.
- **Bao phủ nhiều loại kịch bản**: Positive, Negative, Boundary, Permission, Resilience, Workflow và Acceptance (suy ra từ acceptance criteria).
- **Train knowledge base**: nạp tài liệu, workflow, business rule, diagram bằng paste text hoặc upload file.
- **RAG**: khi sinh test case, agent tìm các đoạn (chunk) tài liệu liên quan nhất và dùng làm ngữ cảnh.
- **Hai chế độ sinh**:
  - *Local rule-based* (mặc định, không cần API key): tạo bộ case baseline + case theo workflow/criteria.
  - *LLM* (khi có API key): mô hình cải thiện và mở rộng bộ case dựa trên ngữ cảnh đã lọc.
- **Tự học (auto-learn)**: khi sinh test case mà chưa có tài liệu liên quan, LLM tự đúc kết hiểu biết về feature và lưu lại để tái sử dụng lần sau.
- **Bộ nhớ bền (tuỳ chọn)**: tích hợp AgentBase Memory Service để knowledge tồn tại qua restart và chia sẻ giữa các replica.

### Luồng xử lý sinh test case

1. Nhận input (`feature`/`message`/`requirement`, `actor`, `platform`, `acceptance_criteria`).
2. Truy hồi ngữ cảnh: chunk hoá knowledge `READY`, chấm điểm theo keyword, lấy các chunk liên quan nhất (tối đa 6 chunk, gộp về tối đa 4 tài liệu).
3. Tạo bộ test case baseline bằng rule-based, kèm case workflow (nếu tài liệu có dạng `A -> B -> C`) và case cho từng acceptance criterion.
4. Nếu cấu hình LLM: gọi mô hình để cải thiện/ mở rộng bộ case; nếu lỗi sẽ tự fallback về kết quả rule-based.
5. Nếu không có ngữ cảnh và LLM tự sinh: lưu phần đúc kết (`learned_summary`) vào knowledge base như item `auto-learned`.

---

## 2. Yêu cầu

- Python 3.12 (hoặc tương thích).
- `pip`.
- Docker (tuỳ chọn, nếu chạy bằng container).
- API key LLM (tuỳ chọn, để bật chế độ AI).

Dependencies (`requirements.txt`): `greennode-agentbase`, `python-dotenv`, `python-multipart`, `pypdf`, `python-docx`, `openpyxl`.

---

## 3. Chạy local

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env      # điền các giá trị cần thiết
venv/bin/python main.py
```

Server chạy ở port **8080**.

- Web UI: `http://localhost:8080/`
- Health check: `curl http://localhost:8080/health`

## 4. Chạy bằng Docker

```bash
docker build -t qc-test-case-agent .
docker run --rm -p 8080:8080 --env-file .env qc-test-case-agent
```

Sau đó mở `http://localhost:8080/`.

---

## 5. Dùng web UI

Giao diện chia 2 cột:

**Cột trái — Train & nhập liệu**
- *Training knowledge*: đặt tên, chọn `Type` (Workflow / Diagram / Requirement document / Business rule), rồi **paste text** hoặc **upload file**.
  - Với type `Diagram`, ô paste bị khoá — diagram nên được upload dưới dạng file.
- *Generate test cases*: nhập Feature/Requirement, Actor, Platform, Acceptance criteria (mỗi tiêu chí một dòng), bấm **Generate**.
- *Knowledge base*: danh sách item đã nạp, kèm trạng thái và các action review.

**Cột phải — Kết quả**
- Tóm tắt feature, knowledge được dùng, context summary, chế độ AI và toàn bộ test case sinh ra.

Banner AI ở đầu cột trái cho biết đang ở chế độ fallback hay đã kết nối LLM.

---

## 6. API

| Method | Endpoint | Mục đích |
|--------|----------|----------|
| GET | `/` | Web UI |
| GET | `/invocations` | Web UI (khi mở trên AgentBase) |
| POST | `/invocations` | Entrypoint AgentBase — sinh test case |
| POST | `/chat` | Sinh test case (dùng bởi web UI) |
| GET | `/ai/status` | Trạng thái cấu hình LLM |
| GET | `/knowledge` | Danh sách knowledge |
| POST | `/knowledge` | Thêm knowledge bằng JSON |
| POST | `/knowledge/upload` | Upload file knowledge |
| POST | `/knowledge/action` | Cập nhật trạng thái knowledge |
| GET | `/health` | Health check |

### Sinh test case — endpoint AgentBase

```bash
curl -X POST http://localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -H "X-GreenNode-AgentBase-User-Id: qc-user" \
  -H "X-GreenNode-AgentBase-Session-Id: qc-session" \
  -d '{
    "feature": "User can reset password",
    "actor": "Customer",
    "platform": "Web app",
    "acceptance_criteria": [
      "Customer receives a reset email",
      "Expired reset link cannot be used",
      "New password must follow password policy"
    ]
  }'
```

### Sinh test case — endpoint nội bộ của web UI

```bash
curl -X POST http://localhost:8080/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Create test cases for login with OTP",
    "actor": "Customer",
    "platform": "Mobile app"
  }'
```

**Input được hỗ trợ:**

- `feature`, `message` hoặc `requirement` — feature/yêu cầu cần test.
- `actor` hoặc `user_role` — vai trò người dùng (mặc định `User`).
- `platform` — bề mặt ứng dụng (web, mobile, API…).
- `acceptance_criteria` hoặc `criteria` — list hoặc text; nếu để trống, agent sẽ cố suy ra criteria từ ngữ cảnh đã train.

**Response gồm:**

- `feature`, `actor`, `platform`, `generated_at`
- `test_cases` — danh sách case có cấu trúc đầy đủ
- `context_summary` + `source_refs` — knowledge đã dùng và chunk khớp
- `quality_checklist` — checklist chất lượng QC
- `notes` — ghi chú
- `ai_mode` — chế độ đã chạy (xem bên dưới)
- `auto_learned` — (nếu có) item vừa được tự học

### Trạng thái AI

```bash
curl http://localhost:8080/ai/status
```

Trả về `configured`, `model`, `base_url`, `wire_api`. Các giá trị `ai_mode` có thể gặp trong response:

| `ai_mode` | Ý nghĩa |
|-----------|---------|
| `fallback-no-llm-config` | Chưa cấu hình API key → dùng rule-based |
| `llm-rag` | LLM cải thiện case dựa trên ngữ cảnh đã train |
| `llm-generate` | Không có ngữ cảnh → LLM tự sinh từ kiến thức QC |
| `fallback-llm-error` | Gọi LLM lỗi → fallback về rule-based (kèm `ai_error`) |

---

## 7. Train knowledge

### Thêm bằng JSON

```bash
curl -X POST http://localhost:8080/knowledge \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Login OTP workflow",
    "type": "workflow",
    "source": "manual",
    "text": "Start -> Enter phone number -> Send OTP -> Verify OTP -> Login success\nRules:\n- OTP expires after 5 minutes\n- Wrong OTP is rejected after 5 attempts"
  }'
```

> Mẹo: dùng dấu `->` trong workflow để agent sinh thêm case kiểm tra chuyển trạng thái.

### Upload file

```bash
curl -X POST http://localhost:8080/knowledge/upload \
  -F "title=Payment requirement" \
  -F "type=requirement" \
  -F "file=@/path/to/requirement.docx"
```

**Định dạng đọc được:** `.txt`, `.md`, `.csv`, `.json`, `.xml`, `.svg`, `.drawio`, `.bpmn`, `.mmd`, `.mermaid`, `.puml`, `.plantuml`, `.pdf`, `.docx`, `.xlsx`.

**Ảnh diagram** (`.png`, `.jpg`, `.jpeg`, `.webp`): được lưu nhưng **không trích xuất** (bản local chưa có OCR/vision) → trạng thái `NEEDS_REVIEW`.

Giới hạn dung lượng mặc định 10 MB (`MAX_UPLOAD_BYTES`).

### Xem & cập nhật

```bash
# Danh sách
curl http://localhost:8080/knowledge

# Cập nhật trạng thái
curl -X POST http://localhost:8080/knowledge/action \
  -H "Content-Type: application/json" \
  -d '{ "id": "KB-...", "action": "mark-ready" }'
```

**Trạng thái knowledge:**

- `READY` — đã trích xuất, index và dùng khi sinh test case.
- `NEEDS_REVIEW` — đã lưu nhưng chưa index (thường gặp với diagram ảnh); **không** dùng để generate.
- `FAILED` — không đọc được, kèm lý do; không dùng để generate.

**Action (`/knowledge/action`):**

| Action | Tác dụng |
|--------|----------|
| `mark-ready` | Duyệt item thành `READY` (cần đã có nội dung) |
| `mark-review` | Đưa về `NEEDS_REVIEW`, loại khỏi generation |
| `save-ready` | Lưu nội dung đã sửa (kèm `text`) và đặt `READY` |
| `save-review` | Lưu nội dung đã sửa nhưng giữ `NEEDS_REVIEW` |
| `delete` | Xoá item |

Trên web UI, các action tương ứng: *Review/Edit*, *Mark READY*, *Needs review*, *Delete*, *Save as READY*, *Save review note*.

> Knowledge được lưu tại `.agentbase/knowledge.json` (ghi an toàn bằng file lock + atomic write), tối đa 100 item gần nhất.

---

## 8. Cấu hình môi trường

Tạo `.env` từ `.env.example`. `.env.example` chỉ chứa cấu hình AgentBase cơ bản; các biến LLM/Memory bên dưới là tuỳ chọn.

### AgentBase

| Biến | Mô tả |
|------|-------|
| `GREENNODE_CLIENT_ID`, `GREENNODE_CLIENT_SECRET` | Xác thực AgentBase khi triển khai |
| `GREENNODE_AGENT_IDENTITY` | Tuỳ chọn, chỉ cần khi dùng agent identity |
| `PORT` | Port runtime (server local mặc định 8080) |

### LLM (bật chế độ AI)

| Biến | Mặc định | Mô tả |
|------|----------|-------|
| `MAAS_API_KEY` | – | API key GreenNode MaaS MiniMax |
| `LLM_API_KEY` | – | API key cho provider OpenAI-compatible khác |
| `LLM_BASE_URL` | `https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1` | Base URL LLM |
| `LLM_MODEL` | `minimax/minimax-m2.5` | Model dùng để enhance test case |
| `LLM_WIRE_API` | `responses` nếu có `MAAS_API_KEY`, ngược lại `chat` | `responses` (MaaS MiniMax) hoặc `chat` (Chat Completions) |
| `LLM_TIMEOUT` | `120` | Timeout (giây) cho lời gọi LLM |
| `MAX_UPLOAD_BYTES` | `10485760` | Giới hạn upload file (10 MB) |

Ví dụ dùng GreenNode MaaS MiniMax:

```env
MAAS_API_KEY=vn-...
LLM_WIRE_API=responses
LLM_BASE_URL=https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1
LLM_MODEL=minimax/minimax-m2.5
```

Provider OpenAI-compatible khác:

```env
LLM_API_KEY=...
LLM_WIRE_API=chat
LLM_BASE_URL=...
LLM_MODEL=...
```

Nếu không cấu hình key nào, agent vẫn chạy bằng rule-based generation.

### Memory Service (bộ nhớ bền — tuỳ chọn)

Khi cấu hình, knowledge `READY` và phần tự học được lưu lên AgentBase Memory Service (best-effort), tồn tại qua restart và chia sẻ giữa các replica. Mọi lỗi đều fallback về knowledge local nên agent không bao giờ gãy.

| Biến | Mô tả |
|------|-------|
| `MEMORY_ID` | ID memory store |
| `MEMORY_STRATEGY_ID` | ID strategy (bắt buộc để bật) |
| `MEMORY_ACTOR` | Namespace actor, mặc định `qc-shared` |

---

## 9. Chế độ AI RAG (chi tiết)

Khi đã cấu hình LLM, flow là:

1. Đọc toàn bộ knowledge `READY`, chia thành chunk.
2. Chấm điểm và chọn các chunk liên quan nhất với feature đang test.
3. Gọi LLM để **cải thiện và bám sát** bộ test case theo ngữ cảnh đã lọc (`llm-rag`).
4. Nếu **không có** ngữ cảnh nào khớp, LLM **tự sinh** test case từ kiến thức QC và trả về `learned_summary` để agent tự học (`llm-generate`).
5. Mọi lỗi gọi LLM → tự fallback về rule-based (`fallback-llm-error`).

GreenNode MaaS MiniMax là cấu hình khuyến nghị; `codex.toml` đã chuẩn bị sẵn Responses API. Dùng Codex CLI:

```bash
export MAAS_API_KEY="vn-..."
codex
```

---

## 10. Ghi chú về diagram

- Nên **upload** diagram thay vì paste nội dung.
- Định dạng đọc tốt: SVG, drawio, BPMN, Mermaid, PlantUML, PDF.
- Ảnh PNG/JPG/WebP được lưu ở `NEEDS_REVIEW` cho tới khi kết nối OCR/vision hoặc review nội dung thủ công.

---

## 11. Cấu trúc dự án

```text
.
├── main.py            # App: web UI, API, knowledge store, RAG, LLM, Memory Service
├── requirements.txt   # Python dependencies
├── Dockerfile         # Container image (python:3.12-slim, port 8080)
├── codex.toml         # Cấu hình Codex CLI cho GreenNode MaaS MiniMax
├── .greennode.json    # Cấu hình triển khai AgentBase
├── .env.example       # Mẫu biến môi trường
├── .agentbase/        # Dữ liệu runtime (knowledge.json) — sinh khi chạy
└── README.md
```
