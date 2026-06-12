# QC Test Case Agent

Agent hỗ trợ QC/QA chuyển feature description, acceptance criteria, tài liệu nghiệp vụ, workflow và diagram thành bộ test case có cấu trúc.

Ứng dụng có sẵn web UI để nhập yêu cầu, train knowledge và xem kết quả. API `/invocations` dùng được khi triển khai trên GreenNode AgentBase.

## Tính năng chính

- Sinh test case từ feature, requirement hoặc message tự do.
- Nhận actor/user role, platform và acceptance criteria.
- Lưu knowledge nội bộ trong `.agentbase/knowledge.json`.
- Upload và trích xuất nội dung từ `.txt`, `.md`, `.csv`, `.json`, `.xml`, `.svg`, `.drawio`, `.bpmn`, `.mmd`, `.mermaid`, `.puml`, `.plantuml`, `.pdf`, `.docx`, `.xlsx`.
- Lưu ảnh diagram `.png`, `.jpg`, `.jpeg`, `.webp` ở trạng thái cần review vì bản local chưa có OCR/vision.
- Có chế độ local rule-based mặc định và chế độ LLM RAG khi cấu hình API key.

## Yêu cầu

- Python 3.12 hoặc tương thích.
- `pip`.
- Docker, nếu muốn chạy bằng container.
- API key LLM, nếu muốn bật chế độ AI RAG.

## Chạy local

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env
venv/bin/python main.py
```

Mở web UI:

```text
http://localhost:8080/
```

Health check:

```bash
curl http://localhost:8080/health
```

## Chạy bằng Docker

```bash
docker build -t qc-test-case-agent .
docker run --rm -p 8080:8080 --env-file .env qc-test-case-agent
```

Sau đó mở:

```text
http://localhost:8080/
```

## Cấu hình môi trường

Tạo `.env` từ `.env.example` và điền các giá trị cần thiết:

```bash
cp .env.example .env
```

Các biến quan trọng:

- `GREENNODE_CLIENT_ID`, `GREENNODE_CLIENT_SECRET`: thông tin xác thực AgentBase khi triển khai hoặc dùng dịch vụ AgentBase.
- `GREENNODE_AGENT_IDENTITY`: tùy chọn, chỉ cần khi dùng agent identity.
- `MAAS_API_KEY`: API key GreenNode MaaS MiniMax, dùng cho LLM RAG và có thể dùng chung với `codex.toml`.
- `LLM_API_KEY`: API key cho provider OpenAI-compatible khác.
- `LLM_WIRE_API`: `responses` cho MaaS MiniMax, hoặc `chat` cho Chat Completions-compatible provider.
- `LLM_BASE_URL`: base URL của LLM provider.
- `LLM_MODEL`: model dùng để enhance test case.
- `MAX_UPLOAD_BYTES`: giới hạn upload file, mặc định `10485760` bytes, tức 10 MB.

Ví dụ cấu hình GreenNode MaaS MiniMax:

```env
MAAS_API_KEY=vn-...
LLM_WIRE_API=responses
LLM_BASE_URL=https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1
LLM_MODEL=minimax/minimax-m2.5
```

Nếu không cấu hình LLM key, agent vẫn chạy bằng local rule-based generation.

## API

### Sinh test case

Endpoint AgentBase:

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

Web UI dùng endpoint nội bộ `/chat`:

```bash
curl -X POST http://localhost:8080/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Create test cases for login with OTP",
    "actor": "Customer",
    "platform": "Mobile app"
  }'
```

Input được hỗ trợ:

- `feature`, `message` hoặc `requirement`: feature hoặc yêu cầu nghiệp vụ cần test.
- `actor` hoặc `user_role`: vai trò người dùng.
- `platform`: bề mặt ứng dụng, ví dụ web app, mobile app, API.
- `acceptance_criteria` hoặc `criteria`: danh sách hoặc text acceptance criteria.

Response gồm:

- test cases có cấu trúc
- context summary từ trained knowledge
- source references
- preconditions
- test data notes
- steps
- expected results
- priority và test type
- QC quality checklist

### Trạng thái AI

```bash
curl http://localhost:8080/ai/status
```

Endpoint này cho biết agent đang chạy local fallback hay đã bật LLM RAG.

## Train knowledge

Có thể train knowledge trong web UI, hoặc gọi API trực tiếp.

### Thêm knowledge bằng JSON

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

### Upload file

```bash
curl -X POST http://localhost:8080/knowledge/upload \
  -F "title=Payment requirement" \
  -F "type=requirement" \
  -F "file=@/path/to/requirement.docx"
```

### Xem danh sách knowledge

```bash
curl http://localhost:8080/knowledge
```

### Cập nhật trạng thái knowledge

```bash
curl -X POST http://localhost:8080/knowledge/action \
  -H "Content-Type: application/json" \
  -d '{
    "id": "knowledge-id",
    "action": "mark-ready"
  }'
```

Các trạng thái knowledge:

- `READY`: nội dung đã được trích xuất, lưu và dùng khi sinh test case.
- `NEEDS_REVIEW`: file đã lưu nhưng chưa được index, thường gặp với image-only diagram.
- `FAILED`: file đã lưu kèm lý do lỗi và không được dùng để generate.

Các action trong UI:

- `Review/Edit`: kiểm tra hoặc sửa nội dung đã lưu.
- `Save as READY`: lưu nội dung sau review và cho phép dùng khi generate.
- `Save review note`: lưu nội dung chỉnh sửa nhưng chưa đưa vào generation.
- `Mark READY`: duyệt một item đã đọc được.
- `Needs review`: loại item khỏi generation cho tới khi được review.
- `Delete`: xóa item khỏi knowledge base.

## AI RAG mode

Mặc định agent sinh test case bằng rule-based generation và keyword chunk retrieval. Khi có cấu hình LLM, flow sẽ là:

1. Đọc tất cả knowledge có trạng thái `READY`.
2. Chia tài liệu dài thành các chunk.
3. Chọn các chunk liên quan nhất với feature cần test.
4. Gọi LLM để cải thiện bộ test case dựa trên context đã chọn.
5. Tự fallback về local generation nếu LLM call lỗi.

GreenNode MaaS MiniMax là cấu hình khuyến nghị cho dự án này vì `codex.toml` đã được chuẩn bị sẵn với Responses API.

Để dùng Codex CLI với cấu hình trong `codex.toml`:

```bash
export MAAS_API_KEY="vn-..."
codex
```

Provider OpenAI-compatible khác cũng có thể dùng được bằng cách đặt:

```env
LLM_API_KEY=...
LLM_WIRE_API=chat
LLM_BASE_URL=...
LLM_MODEL=...
```

## Ghi chú về diagram

- Nên upload diagram thay vì paste nội dung vào text box.
- Các định dạng readable gồm SVG, drawio, BPMN, Mermaid, PlantUML và PDF.
- Image-only PNG/JPG/WebP được lưu ở trạng thái `NEEDS_REVIEW` cho tới khi có OCR/vision hoặc nội dung được review thủ công.

## Cấu trúc dự án

```text
.
├── main.py              # App, web UI, API, knowledge store, generator
├── requirements.txt     # Python dependencies
├── Dockerfile           # Container image
├── codex.toml           # Codex CLI config for GreenNode MaaS MiniMax
├── .env.example         # Environment variable template
└── README.md
```
