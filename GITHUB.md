# Đưa assignment06 lên GitHub

Repo Git được đặt ngay trong `assignment06/`, chỉ chứa dự án này.

## Thành phần được lưu

- Source Python, giao diện, config, tests và hướng dẫn.
- Catalog ESCI, bản dịch Việt, thông tin nguồn, SQLite vector indexes.
- Đúng 10 ảnh giày mẫu trong `data/images/`, giữ nguyên tên/source ID.
- Manifest model và giấy phép upstream; không lưu trọng số pretrained.

`.gitignore` chỉ ngăn Git theo dõi file, không xóa các ảnh/model trên máy. Các index và manifest vẫn đại diện cho toàn bộ catalog, không phải một dataset đã được rút gọn còn 10 sản phẩm. Sau khi clone sang máy khác, cần bổ sung thư mục model đầy đủ và các ảnh còn lại từ bản dự án local trước khi chạy demo đầy đủ. Chỉ 10 ảnh mẫu không thay thế gói dữ liệu runtime.

## Tạo repo mới và push

1. Đăng nhập GitHub và mở **New repository**. Đặt tên, ví dụ `a06-multimodal-search`, chọn Public hoặc Private. Để repo trống: không tạo README, .gitignore hoặc license ở bước này.
2. Copy URL HTTPS của repo vừa tạo, rồi chạy PowerShell:

```powershell
cd D:\Quota\PTTKHTTT\A06\assignment06
git remote add origin https://github.com/YOUR_USERNAME/a06-multimodal-search.git
git push -u origin main
```

Thay `YOUR_USERNAME` và tên repo bằng thông tin của bạn. Nếu Git mở cửa sổ đăng nhập, đăng nhập GitHub theo hướng dẫn của Git Credential Manager. Không đưa token vào source, URL remote hoặc file cấu hình dự án.

Nếu Git báo `dubious ownership` do thư mục được tạo trong môi trường Codex, chỉ đánh dấu đúng repo này là thư mục tin cậy rồi chạy lại lệnh:

```powershell
git config --global --add safe.directory D:/Quota/PTTKHTTT/A06/assignment06
```

## Những lần cập nhật sau

```powershell
git add .
git commit -m "Update A06 prototype"
git push
```

Kiểm tra phạm vi và ảnh được theo dõi:

```powershell
git rev-parse --show-toplevel
git ls-files data/images
git status
```

Thư mục gốc phải là `D:/Quota/PTTKHTTT/A06/assignment06`; danh sách ảnh có 10 file. Không chạy `git add` từ thư mục cha để gom các bài khác vào repo này.
