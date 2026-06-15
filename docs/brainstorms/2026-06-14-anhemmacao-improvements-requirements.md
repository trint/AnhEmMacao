# AnhEmMacao — Cải tiến toàn diện

**Ngày:** 2026-06-14
**Đối tượng:** Team QC nội bộ
**Trạng thái:** Draft

---

## Mục tiêu

Nâng cấp có thứ tự **AnhEmMacao** — công cụ sinh test case tự động — để team QC nội bộ có thể sử dụng hiệu quả hơn trong quy trình hàng ngày. Không rewrite toàn bộ; mỗi cải tiến mang lại giá trị độc lập và có thể ship riêng.

---

## Người dùng

**Team QC nội bộ** — gồm QA engineer và QA lead. QA engineer tạo test case từ tài liệu tính năng; QA lead review và phân phối trước khi import vào Jira/TestRail.

---

## Cải tiến theo độ ưu tiên

### 1. Export test case ra CSV (ưu tiên #1)

**Vấn đề:** Kết quả test case chỉ hiển thị trên UI, không xuất được ra file. QA phải copy thủ công từng dòng.

**Yêu cầu:**
- Nút "Export CSV" xuất hiện sau khi test case được sinh ra
- File CSV có các cột: `ID`, `Title`, `Type`, `Priority`, `Preconditions`, `Test Data`, `Steps`, `Expected Result`, `References`
- Steps được phân tách rõ ràng (mỗi bước trên một dòng trong ô, hoặc cột `Step 1`, `Step 2`... tùy số bước)
- Encoding UTF-8 với BOM để Google Sheets hiển thị tiếng Việt đúng
- Tên file mặc định: `testcases-YYYY-MM-DD-HH-MM.csv`

**Tiêu chí hoàn thành:** QA download CSV, mở bằng Google Sheets mà không bị lỗi encoding, thấy đủ thông tin để review mà không cần quay lại tool.

**Không bao gồm:** Tích hợp Google Sheets API, push trực tiếp lên Google Drive.

---

### 2. Đọc ảnh và diagram qua Vision AI (ưu tiên #2)

**Vấn đề:** PNG, JPG, WebP upload lên bị đánh dấu `NEEDS_REVIEW` — tool không đọc được nội dung. QA phải tự nhập lại nội dung sơ đồ thủ công.

**Yêu cầu:**
- Khi có `LLM_API_KEY` được cấu hình với model hỗ trợ vision (vd: `gpt-4o`, `claude-3-5-sonnet`), tự động gửi ảnh lên LLM để trích xuất nội dung
- Kết quả trích xuất lưu vào knowledge store như text thông thường (status `READY`)
- Nếu không có vision-capable model, giữ nguyên hành vi hiện tại (`NEEDS_REVIEW`) — không breaking change
- UI hiển thị rõ ảnh đã được xử lý bởi vision hay vẫn cần review thủ công

**Tiêu chí hoàn thành:** Upload screenshot Figma hoặc flowchart → tool sinh test case dựa trên nội dung ảnh mà không cần QA nhập lại.

**Giả định chưa kiểm chứng:** LLM provider hiện tại (MiniMax) có hỗ trợ vision — cần xác nhận trước khi implement.

---

### 3. Tùy chỉnh loại test case (ưu tiên #3)

**Vấn đề:** 6 loại test case cố định trong code (`Positive`, `Negative`, `Boundary`, `Permission`, `Resilience`, `Workflow`) không phản ánh đặc thù từng dự án. Team không thể thêm loại mới không cần chỉnh code.

**Yêu cầu:**
- File config (JSON hoặc YAML) định nghĩa danh sách loại test case và template prompt cho mỗi loại
- UI cho phép xem danh sách loại hiện tại và bật/tắt từng loại khi generate
- Khi không có config, dùng 6 loại mặc định như hiện tại — backward compatible

**Tiêu chí hoàn thành:** Team thêm loại "Security" hoặc "Performance" vào config file mà không cần sửa `main.py`, và tool sinh test case theo loại đó.

---

### 4. Cải thiện chất lượng retrieval và LLM (ưu tiên #4)

**Vấn đề:** Knowledge retrieval dùng exact keyword match — khi có nhiều tài liệu, tool trả về sai context hoặc thiếu thông tin liên quan.

**Yêu cầu:**
- Tăng giới hạn context: `TOP_CONTEXT_CHUNKS` từ 6 lên 10, `MAX_CONTEXT_CHARS` từ 4,200 lên 6,000
- Cải thiện scoring: ưu tiên chunks có nhiều keyword overlap theo tỷ lệ (không chỉ đếm tuyệt đối)
- Tinh chỉnh system prompt để yêu cầu test case cụ thể hơn, giảm kết quả chung chung
- Thêm deduplication: bỏ các test case trùng lặp trong cùng một response

**Tiêu chí hoàn thành:** Với cùng một feature description, test case sinh ra có ít nhất 80% case liên quan trực tiếp đến tính năng đó (đánh giá thủ công bởi QA lead).

---

### 5. Technical hygiene (nền tảng)

**Vấn đề:** Một số vấn đề kỹ thuật làm giảm độ tin cậy và khả năng maintain.

**Yêu cầu:**
- Thay `fcntl` bằng thư viện `filelock` để hỗ trợ Windows (hiện `fcntl` chỉ chạy trên Linux/macOS)
- Tách HTML/CSS/JS ra file riêng hoặc thư mục `static/` — giảm `main.py` từ 1,782 dòng
- Thêm unit test cho các hàm core: `_keywords`, `_chunk_score`, `retrieve_context`, `_chunk_text`
- Cập nhật `Dockerfile` để reflect các dependency mới

**Tiêu chí hoàn thành:** Test suite chạy được trên Windows và Linux; `main.py` dưới 1,000 dòng.

---

## Phạm vi không bao gồm

- Chuyển đổi storage sang database (JSON file vẫn đủ ở quy mô hiện tại)
- Trực tiếp push lên Jira/TestRail (QA review thủ công là bước cần thiết)
- Giao diện multi-user với phân quyền
- Semantic search với embedding vector (có thể xem xét sau khi retrieval cơ bản được cải thiện)

---

## Câu hỏi còn mở

1. MiniMax M2.5 có hỗ trợ vision API không? Nếu không, cần dùng model phụ riêng cho ảnh.
2. Steps trong CSV nên gộp vào một ô (multi-line) hay tách thành nhiều cột?
3. Có cần format CSV theo template chuẩn của Jira/TestRail để import thẳng không?

---

## Thứ tự triển khai đề xuất

| Thứ tự | Tính năng | Lý do |
|--------|-----------|-------|
| 1 | Export CSV | Giá trị tức thì, không phụ thuộc LLM config |
| 2 | Technical hygiene (filelock + tests) | Nền tảng cho các thay đổi tiếp theo |
| 3 | Vision/OCR | Giảm công việc thủ công lớn nhất |
| 4 | Custom test case types | Tăng linh hoạt cho từng dự án |
| 5 | Cải thiện retrieval + prompt | Cần data thực tế để đánh giá hiệu quả |
