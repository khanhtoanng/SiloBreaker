# Successor selection phase 2: việc cần chốt trước khi code

Trạng thái: phase 1 (backend) đã commit `ce83be2` trên `feature/candidate-selection`, với 157 test pass.
Chưa viết dòng code nào cho phase 2. File này liệt kê những điểm phải chốt trước khi code.

## 1. Nhánh

- Yêu cầu ghi `feature/successor-selection`, nhưng nhánh này chưa tồn tại. Phase 1 nằm trên
  `feature/candidate-selection`.
- **Cần chốt:** làm tiếp trên `feature/candidate-selection` (đề xuất), hay tạo nhánh mới từ đó.

## 2. Backend còn thiếu (không phải lỗi, mà là phần mở rộng)

Yêu cầu phase 2 nói "chỉ đổi backend nếu phát hiện lỗi thật", nhưng UI cần những thứ API hiện chưa có:

| Cần cho UI | Hiện trạng phase 1 | Việc backend cần làm |
|---|---|---|
| Tạo handoff "Choose successor later" | Bắt buộc gửi `successor_id` hoặc 2–4 `candidate_ids` | Cho phép tạo handoff chưa có successor và chưa có pool |
| "Start common assessment" (chọn exercise đã phát hành + hạn nộp) | Pool được chốt ngay lúc tạo handoff; chưa có exercise riêng cho pool, chưa có hạn nộp | Endpoint mới để bắt đầu đánh giá chung; migration thêm `exercise_id` và `due_at` cho đợt đánh giá |
| "One official attempt" | `max_attempts` mặc định là 2 | Đặt bằng 1 cho đợt đánh giá chung, hoặc cho admin chọn |
| % phù hợp (tab Suitability) cho mọi thành viên, kể cả người chưa vào pool | Chỉ có `context.recovered_incidents` cho ứng viên đã có trong pool | Endpoint suitability cho admin trả % hoặc `no_history` |
| % điểm (tab Results) | Chỉ có group theo `aggregate()` | Readiness trả thêm `score_pct`, `is_top`, `is_tie`, `missing_critical` |
| Quyết định hiển thị "top hay không, tie hay không" | `successor_selection` lưu `recommended` và `in_recommended` | Lưu thêm snapshot top/tie (có thể phải thêm migration) |

**Cần chốt:** có đồng ý mở rộng backend cho các mục trên không (mỗi mục đều có test).

## 3. Công thức hai con số %: chưa khớp với số e2e mong đợi

Theo yêu cầu, mọi con số do API tính; trình duyệt không tính lại.

### 3.1 % phù hợp (Fit)

Số sự cố có trích dẫn trong dữ liệu offline, đếm theo người khôi phục:

| Khu vực | Người khôi phục |
|---|---|
| settlement | alice 3 |
| webhooks | alice 2, bob 1, carol 1 |
| certificates | alice 2 |
| fx-rates | không có |

- E2e mong đợi **Bob 20%, Carol 20%, Minh "No history"**. Không tìm ra mẫu số nào cho ra 20%:
  1/9 ≈ 11%, còn nếu chỉ tính webhooks thì 1/4 = 25%.
- **Đề xuất:** Fit = số sự cố người đó khôi phục ÷ tổng số sự cố có người khôi phục trong các
  khu vực của handoff. Kết quả: Bob 11%, Carol 11%. Minh trả về `no_history`, UI hiện chữ
  "No history — not 0%".
- **Cần chốt:** công thức chính xác, hoặc chấp nhận đề xuất này và sửa số e2e theo.

### 3.2 % điểm (Score)

Verdict của bộ chấm offline (C1, C2 là critical):

| Ứng viên | C1 | C2 | C3 | C4 | C5 | aggregate |
|---|---|---|---|---|---|---|
| Bob (correct_paraphrase) | met | met | met | met | met | demonstrated |
| Carol (partial_answer) | met | met | unmet | met | met | partial |
| Minh (unsafe) | partial | unmet | partial | unmet | unmet | not_yet |

- E2e mong đợi **Bob 100%, Carol 75%, Minh 8%**.
- Với điểm có trọng số (met = 1, partial = 0.5, critical có trọng số w), Carol được
  (2w+2)/(2w+3). Muốn ra 75% thì w = 0.5, tức tiêu chí critical lại nhẹ hơn tiêu chí thường.
  Khi đó Minh được 18.75%, không phải 8%. Vậy không công thức hiển nhiên nào cho ra cả ba số.
- **Đề xuất:** Score = Σ(trọng số × điểm) ÷ Σ trọng số, với critical = 2, thường = 1,
  met = 1, partial = 0.5, unmet = 0. Kết quả: Bob 100%, Carol 86%, Minh 21%.
- Huy hiệu "Missing a critical condition" vẫn lấy theo `aggregate()` (not_yet), không lấy từ %.
- **Cần chốt:** công thức chính xác, hoặc chấp nhận đề xuất này và sửa số e2e theo.

## 4. Quan hệ giữa % điểm và group của phase 1

- Phase 1 xếp nhóm Ready, Ready with support và Not yet theo `aggregate()`, và `recommended` là
  mọi người ở nhóm cao nhất. Phase 2 lại xếp theo % điểm, với các huy hiệu "Best result" và
  "Tie — admin decides".
- **Đề xuất:**
  - Top là những người có % cao nhất trong nhóm cao nhất. Như vậy một bài not_yet không bao giờ
    đứng trên một bài partial, kể cả khi % cao hơn.
  - Tie là khi có từ hai người cùng là top.
  - Lý do bắt buộc khi chọn người ngoài top. Quy tắc này thay cho `recommended` theo nhóm.
- **Cần chốt:** đồng ý quy tắc này, hoặc dùng quy tắc khác.

## 5. Kiểm tra và hạ tầng chưa có

- **`noVietnameseText`:** repo hiện không có test nào tên này. Cần tạo test (Vitest) quét
  `frontend/src` để phát hiện ký tự tiếng Việt. Chốt phạm vi quét: chỉ `frontend/src`, hay cả e2e.
- **"Smoke test nếu có":** cần xác nhận repo có smoke test riêng hay chưa. Chưa thấy trong
  danh sách lệnh của `AGENTS.md`.
- **`e2e/selection_flow.py`:** viết mới; `demo_flow.py` giữ nguyên.

## 6. Kế hoạch sau khi chốt (thứ tự làm)

1. **Backend:** viết test trước, rồi thêm migration (handoff chưa có successor, đợt đánh giá
   chung với exercise, hạn nộp và 1 lượt chính thức), endpoint suitability, `score_pct`,
   `is_top`, `is_tie` trong readiness, và snapshot top/tie khi chọn.
2. **Frontend:**
   - Admin → Handoffs: tùy chọn "Choose successor later"; trang handoff có hai tab Suitability
     và Results.
   - Suitability: thanh % vẽ bằng SVG, hoặc "No history — not 0%"; cột căn cứ (khu vực + mã sự
     cố); ô chọn mỗi dòng. Chọn 1 người hiện "Assign directly"; chọn từ 2 người hiện "Start
     common assessment" (hộp thoại chọn exercise và hạn nộp). Kèm chú thích cố định.
   - Results: sắp xếp theo %, thanh SVG, các huy hiệu, chi tiết từng tiêu chí có đánh dấu
     critical, warnings, hộp thoại "Select as successor" bắt buộc lý do khi chọn ngoài top,
     hiện quyết định sau khi chọn, chú thích cố định.
   - Learn (ứng viên): banner; "Read the approved knowledge" (gọi study-opened rồi mở thư viện)
     phải bấm trước thì "Submit answer" mới sáng; sau khi chấm hiện % của mình và "Request
     review"; hết lượt thì ẩn nút nộp.
   - Expert → Exercise: bài làm hiện theo alias; hàng chờ phúc khảo với form sửa verdict từng
     tiêu chí và lý do bắt buộc.
   - Toàn bộ chữ tiếng Anh, rộng 390px không tràn ngang, mọi ô nhập có label.
3. **Vitest:** Suitability (No history không hiện 0%; nút đổi theo số người chọn), Results
   (huy hiệu top/tie/critical; lý do bắt buộc), Learn (Submit bị khóa khi chưa đọc; hết lượt).
4. **E2e:** `e2e/selection_flow.py --runs 3`, dùng các con số đã chốt ở mục 3.
5. **Docs:** README có mục "Successor selection" (hai con số %, công thức, quy tắc top/tie/lý
   do, giới hạn, admin quyết định cuối) và bảng 5 tài khoản thử; `docs/DEMO.md` thêm cảnh chọn
   người kế nhiệm.
6. **Kiểm tra:** chạy `pytest -q`, `ruff check app tests`, `ruff format --check app tests`,
   `npm test`, `npm run build`, `python e2e/demo_flow.py --runs 3`,
   `python e2e/selection_flow.py --runs 3`.
7. **Commit:** "Successor selection phase 2: UI, e2e, docs" (không Co-Authored-By, không
   Claude-Session), dừng, chưa push.
