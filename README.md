# A06 — BƯỚC

Phiên bản lưu Git chỉ giữ 10 ảnh giày mẫu và manifest model, không chứa trọng số pretrained hoặc toàn bộ ảnh runtime. Xem [GITHUB.md](GITHUB.md) để push repo và bổ sung dữ liệu khi clone sang máy khác. Bản local đầy đủ vẫn chạy như hướng dẫn dưới đây.

Web tìm sản phẩm bằng văn bản Việt/Anh, giọng nói, ảnh hoặc ảnh kèm chỉ dẫn. Giao diện đã được nối với dữ liệu ESCI và các model V2 chạy local trên CPU. `assignment06` chạy độc lập; không import hoặc đọc file từ `semantic_v2` hay `ui-prototype`.

## Chạy trên máy hiện tại

```powershell
cd D:\Quota\PTTKHTTT\A06\assignment06
.\.venv\Scripts\python.exe main.py
```

Mở **http://127.0.0.1:5000/**. Lần khởi động cần tải các model vào RAM và kiểm tra checksum; không tải lại dữ liệu, gọi API dịch hoặc tạo lại vector. Dừng bằng `Ctrl+C`. Nếu cổng đã dùng, thêm `--port 5003`.

Ví dụ: `quick drying water shoes`, `giày đi nước`, `giày dưới 8 trăm`. Có thể nhập khoảng giá ở bộ lọc. Điều kiện giá trong câu và trên giao diện được lấy giao; nếu mâu thuẫn, hệ thống báo lỗi. “Dưới 800k” là `< 800.000`; ô “Đến 800000” là `≤ 800.000`.

Chọn **Thêm ảnh** hoặc dán ảnh vào ô tìm; bỏ trống chữ để tìm ảnh tương tự. Với ảnh giày đi nước màu cam/xanh, thử `đen` hoặc `giống đôi này nhưng màu đen`. Một ảnh tĩnh JPG/PNG/WebP, tối đa 5 MB và 16 triệu pixel. Chỉ dẫn Việt cho ảnh hiện hỗ trợ các mẫu đổi màu; thay đổi khác dùng tiếng Anh. SEARLE truy hồi sản phẩm có sẵn, không tạo ảnh hoặc bảo đảm tìm được đúng mẫu ở mọi truy vấn.

**Nói để nhập** → **Dừng nhập** → kiểm tra/sửa phiên âm → **Tìm kiếm**. Trình duyệt cần micro, hỗ trợ MediaRecorder và localhost/HTTPS. Ghi âm tự dừng sau 25 giây; server chấp nhận tối đa 30 giây/5 MB. Giọng Quảng Nam chưa được xác minh riêng.

Kết quả tìm có `Rank #x · Cosine 0.xxxx` nhỏ dưới giá, giữ nguyên hạng truy hồi khi sắp xếp danh sách theo giá. Không có panel “Chi tiết tìm kiếm”; detail không có hạng/điểm. Nút “Sản phẩm tương tự” lấy ảnh của sản phẩm hiện tại vào thanh tìm như một ảnh vừa được dán và tự tìm bằng ảnh; xóa truy vấn/bộ lọc cũ để chúng không ảnh hưởng lượt tìm mới. Khi duyệt danh mục không truy vấn, không có rank. Trang detail giữ tên đầy đủ, ảnh, giá, màu, thông tin có bằng chứng và mô tả Việt; không tự tạo tồn kho, biến thể, đánh giá, giao hàng hoặc chức năng đặt hàng.

## Cấu trúc

```text
assignment06/
  main.py                 # Entry point web / CLI evidence
  bootstrap.py            # Lắp repository và các adapter model
  application/
    search_service.py     # Điều phối truy hồi, giữ hạng, khóa xử lý
    query_service.py      # Kiểm tra bộ lọc và thứ tự
    ranking_service.py    # Rank và sắp xếp danh sách kết quả
    image_service.py      # Adapter ảnh / ảnh kèm chỉ dẫn
    speech_service.py     # Adapter phiên âm
    intelligence/         # Encoder, retrieval, giá Việt/Anh, CIR, ASR
  data/
    product_repository.py # Catalog hiển thị / ảnh nguồn / phân trang
    vector_index.py       # SQLite text vector persistence
    image_index.py        # SQLite image vector persistence
    image_storage.py      # Manifest ảnh có nguồn, kiểm tra catalog
    esci/                 # Catalog, bản dịch, thuộc tính, SQLite, manifests
    images/               # Ảnh sản phẩm gốc đã đối chiếu nguồn
    processed/            # Taxonomy phục vụ retrieval
  presentation/
    search_ui.py          # Routes; không chứa model/thuật toán truy hồi
    search_result_view.py # Chiếu thông tin sản phẩm sang giao diện Việt
    templates/            # Search, detail, not-found
    static/               # CSS, JavaScript, asset quảng cáo
  config/                 # Cấu hình model đã chọn
  models/                 # Trọng số local + manifest/revision/license
  scripts/check_demo.py  # Smoke test với web và model thật
  tests/                  # Kiểm thử quy tắc và hợp đồng HTTP
  screenshots/            # Ảnh giao diện và bằng chứng kiểm tra
```

V1 cũ được lưu tại `../archive/assignment06_v1`, ngoài dự án hiện tại. Các script tạo sản phẩm giả, tìm đơn hàng, histogram ảnh và voice giả đã được thay thế. Sandbox `../semantic_v2` vẫn giữ các thí nghiệm, tải dữ liệu và benchmark; chúng không phải dependency của demo.

## Dữ liệu và model

- 1.842 sản phẩm nguồn; 446 không có URL ảnh được ẩn, còn 1.396 hiển thị với 1.395 ảnh có nguồn. Một ảnh nguồn tải lỗi được giữ sản phẩm và hiển thị “Chưa có ảnh”. Không dùng ảnh tương tự để thay thế ảnh gốc.
- Giữ catalog tiếng Anh, bản dịch Việt đã chuẩn bị offline và hai bộ passage vector EN/VI. Query được E5 encode trực tiếp, dùng cosine tốt hơn trong hai bộ vector; không dịch query bằng API. Mặc định semantic, không bật hybrid trong storefront.
- Text: `intfloat/multilingual-e5-small`, 384 chiều, query/passage prefixes, 512 token. Ảnh: SigLIP2-base. Ảnh + chỉ dẫn: SEARLE với CLIP ViT-B/32 và lọc màu chính có nguồn. Voice: PhoWhisper-small CT2 FP32, CPU 4 threads.
- Giá bán hiển thị bằng VND. Nguồn và cách tạo giá vẫn được giữ trong `data/esci/display.json`; giá này không phải giá thương mại được Amazon xác minh. Giao diện không ghi nhãn giá demo theo yêu cầu.
- Nhóm Giày / Phụ kiện là ánh xạ quy tắc từ tên nguồn, không phải taxonomy chính thức Amazon. Giày đi nước được gọi “aqua socks” vẫn thuộc Giày. Ánh xạ này chỉ phục vụ lọc/hiển thị, không thay nội dung hoặc vector đã đánh giá.
- `models/*/manifest.json` giữ revision/checksum. SEARLE upstream có giấy phép CC BY-NC 4.0, giữ bản gốc trong `models/searle-b32/upstream/LICENSE`; demo học thuật phi thương mại. Fixture voice giữ nguồn/giấy phép VIVOS tại `tests/fixtures/voice-source.json`.

## Kiểm tra

```powershell
# Quy tắc và API; không tải model
New-Item -ItemType Directory -Force data\test_tmp | Out-Null
$env:TEMP=(Resolve-Path data\test_tmp).Path
$env:TMP=$env:TEMP
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

# Web đang chạy tại 5000: kiểm tra chữ, giá, nhóm, ảnh, CIR, voice, detail
.\.venv\Scripts\python.exe scripts\check_demo.py

# Bằng chứng input / xử lý / score riêng cho bài demo, không đưa vào storefront
.\.venv\Scripts\python.exe main.py --demo --output demo-results.json
```

Smoke test lưu `screenshots/runtime-checks.json`. Đây là kiểm tra tích hợp và một số ca hồi quy, không phải benchmark độ chính xác hay cam kết mọi kết quả có liên quan. Chất lượng semantic và CIR vẫn có giới hạn của model/dữ liệu đã được thảo luận ở sandbox.

## Cài lại môi trường

Python 3.12; môi trường hiện tại đã được chuẩn bị độc lập. Nếu chuyển máy, mang theo các thư mục `models/`, `data/` và tạo môi trường mới:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Không cần tài khoản Vertex/API key để chạy. Khi cập nhật catalog/model, cần chuẩn bị lại manifest và vector tương ứng trước khi mở web; startup sẽ từ chối index lệch checksum thay vì âm thầm dùng vector cũ.

## Demo đơn hàng

Chọn **Đơn hàng của tôi** trên header; tra cứu `O001`, `O002` hoặc `O003`. Giao diện danh sách và chi tiết dùng `presentation/static/orders-mock.json`, giả định khách hàng C001. Tra cứu và tổng tiền xử lý bằng JavaScript; không có order API, backend đơn hàng hoặc đăng nhập. Ảnh và liên kết sản phẩm sử dụng catalog hiện tại.
