# FileHub VN — Ứng dụng quản lý tệp và thư mục cho Windows

Ứng dụng Python có giao diện đồ họa, **hoạt động hoàn toàn ngoại tuyến**, để quản lý các tệp/thư mục trong Desktop, Downloads, Documents, ổ đĩa C:/D:/G:... và những thư mục khác mà tài khoản Windows có quyền truy cập.

## Tính năng

- Điều hướng **Desktop / Tài liệu / Tải xuống / Hình ảnh / Video / ổ đĩa / thư mục bất kỳ**.
- Nhập đường dẫn, điều hướng **Quay lại / Tiến tới / Lên thư mục cha**.
- **Tìm tên file và thư mục**, có tùy chọn quét cả thư mục con, xử lý quét nền tránh khóa giao diện.
- Danh sách có **sắp xếp theo tên, loại, kích thước, ngày sửa, đường dẫn**.
- **Mở file** bằng ứng dụng mặc định của Windows, mở thư mục bằng nhấp đúp.
- **Sao chép, cắt/di chuyển, dán nhiều file/thư mục** giữa các ổ đĩa.
- **Tạo thư mục, đổi tên, chuyển nhiều file vào Thùng rác Windows**.
- **Yêu thích**, thư mục xem gần đây, hiển thị file ẩn, giao diện sáng/tối.
- Menu chuột phải, phím tắt, sao chép đường dẫn dạng văn bản, bảng thông tin file.
- Tên trùng khi sao chép/di chuyển được **tự động đổi tên bản sao, không ghi đè**.

## Tạo EXE bằng 1 cú nhấp trên máy Windows

1. Giải nén gói `FileHubVN_Source.zip` vào thư mục bất kỳ.
2. Cài **Python 3.10 trở lên** trên Windows, bật tùy chọn **Add Python to PATH** khi cài.
3. Nhấp đúp **`build_exe_windows.bat`** (cần internet ở lần đầu để cài gói đóng gói).
4. Sau khi hoàn tất, mở **`dist\FileHubVN.exe`**.
5. Có thể **chép riêng `FileHubVN.exe`** sang máy Windows khác để chạy, không cần cài Python.

> **Lưu ý:** PyInstaller tạo EXE Windows **trên môi trường Windows**. Gói ZIP chứa mã nguồn, cấu hình, file .bat đóng gói và quy trình GitHub Actions; không giả mạo file .exe khi chưa build. Trên máy Windows, file `.exe` được tạo ở `dist\FileHubVN.exe`.

### Không muốn cài Python trên máy cá nhân?

Có thể dùng **GitHub Actions** có sẵn trong `.github/workflows/build-windows.yml`:

1. Tạo repository GitHub mới, tải toàn bộ nội dung dự án lên, bao gồm thư mục `.github`.
2. Vào **Actions** → **Build Windows portable EXE** → **Run workflow**.
3. Mở lần chạy thành công, tải artifact **FileHubVN-Windows-EXE**, giải nén để lấy `FileHubVN.exe`.

## Phím tắt

| Phím | Tác vụ |
| --- | --- |
| Ctrl + C | Sao chép các mục được chọn trong FileHub |
| Ctrl + X | Đánh dấu di chuyển các mục được chọn |
| Ctrl + V | Dán vào thư mục đang xem trong FileHub |
| Ctrl + A | Chọn toàn bộ mục trong danh sách |
| Ctrl + F | Chuyển tới ô tìm kiếm |
| F2 | Đổi tên một mục |
| Delete | Chuyển các mục đã chọn vào Thùng rác |
| F5 | Làm mới danh sách |
| Alt + ← / → | Về trước / tới sau |
| Alt + ↑ | Lên thư mục cha |
| Enter / nhấp đúp | Mở mục được chọn |

## Lưu ý an toàn và giới hạn

- **Xóa vào Thùng rác** qua thư viện `send2trash`, **không xóa vĩnh viễn**; khi thiếu thư viện, lệnh xóa sẽ bị chặn.
- Chương trình **không tải dữ liệu cá nhân lên máy chủ** và không yêu cầu tài khoản, không chạy ẩn.
- Hệ thống có thể yêu cầu quyền truy cập đối với thư mục hạn chế; chương trình **không tự nâng quyền admin**.
- Khi dán tên trùng sẽ tạo tên mới như `BaoCao - bản sao.xlsx`, không ghi đè file cũ.
- Việc di chuyển file lớn qua ổ đĩa có thể cần thời gian; tiến trình chạy nền.
- Chỉ hiển thị tối đa **10.000 kết quả mỗi lần quét** để giới hạn tài nguyên; thu hẹp từ khóa tìm kiếm nếu có nhiều kết quả hơn.
- Chức năng **Ctrl + C/V/X làm việc trong FileHub**; không xuất file dưới định dạng clipboard Windows Explorer. Nút sao chép đường dẫn chỉ sao chép văn bản.
- Công cụ quản lý **file/thư mục cục bộ**, không quản lý các shortcut cloud chưa đồng bộ nội dung về máy.
- File EXE không ký số có thể hiện cảnh báo SmartScreen; chỉ chạy bản EXE do chính bạn build từ mã nguồn tin cậy.

## Cấu trúc

- `app.py`: ứng dụng Python Tkinter.
- `assets/filehub.ico`: icon EXE.
- `requirements.txt`: thư viện xóa an toàn và đóng gói.
- `build_exe_windows.bat`: tạo file `.exe` portable.
- `run_python_windows.bat`: chạy mã nguồn trực tiếp (cần `pip install send2trash`).
- `.github/workflows/build-windows.yml`: build EXE bằng GitHub Actions trên Windows.
- `tests/test_fileops.py`: kiểm thử logic quản lý file và đường dẫn.
- `tests/test_gui_actions.py`: kiểm thử giao diện và tác vụ sao chép/di chuyển.
- `preview.png`: ảnh xem trước giao diện (dữ liệu minh họa).

## Dành cho lập trình viên

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python app.py
```

Ứng dụng ưu tiên tiếng Việt; yêu cầu Python 3.10+ và Windows 10/11 cho tệp `.exe`.
