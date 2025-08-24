# 📊 Auto Stock Price Updater - GitHub Actions

Ứng dụng tự động cập nhật giá cổ phiếu Việt Nam vào Google Sheets mỗi 1 phút sử dụng GitHub Actions.

## 🚀 Tính năng

- ✅ **Auto cập nhật realtime**: Tự động chọn chế độ realtime khi thị trường mở (9:00-15:00, Thứ 2-6)
- ✅ **Auto cập nhật đóng cửa**: Tự động chuyển sang giá đóng cửa khi thị trường đóng
- ✅ **Chạy mỗi 1 phút**: Cập nhật liên tục theo lịch trình
- ✅ **Tích hợp Google Sheets**: Cập nhật trực tiếp vào Google Sheets
- ✅ **Xử lý lỗi thông minh**: Tự động thử lại khi gặp lỗi
- ✅ **Logging chi tiết**: Theo dõi quá trình cập nhật

## 📋 Yêu cầu

- GitHub repository
- Google Cloud Project với Google Sheets API
- Service Account credentials
- Google Sheets với sheet "Data_CP"

## 🔧 Cài đặt

### 1. Fork/Clone Repository

```bash
git clone https://github.com/your-username/stock-price-updater.git
cd stock-price-updater
```

### 2. Tạo Google Service Account

1. Truy cập [Google Cloud Console](https://console.cloud.google.com/)
2. Tạo project mới hoặc chọn project có sẵn
3. Bật Google Sheets API
4. Tạo Service Account:
   - Vào "IAM & Admin" > "Service Accounts"
   - Click "Create Service Account"
   - Đặt tên và mô tả
   - Tạo key JSON và download

### 3. Cấu hình Google Sheets

1. Tạo Google Sheets mới
2. Tạo sheet tên "Data_CP"
3. Cấu trúc cột:
   - Cột C: Danh sách mã cổ phiếu (VCB, HPG, VNM...)
   - Cột H: Giá cổ phiếu (sẽ được cập nhật tự động)
4. Chia sẻ Google Sheets với email service account

### 4. Cấu hình GitHub Secrets

1. Vào repository > Settings > Secrets and variables > Actions
2. Tạo secret mới tên `GOOGLE_CREDENTIALS_JSON`
3. Copy toàn bộ nội dung file JSON credentials vào value

### 5. Cập nhật Sheet URL

Mở file `github_stock_updater.py` và cập nhật `SHEET_URL`:

```python
SHEET_URL = "https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit?usp=sharing"
```

## 🚀 Sử dụng

### Chạy tự động (GitHub Actions)

Repository sẽ tự động chạy mỗi 1 phút theo lịch trình:

```yaml
schedule:
  - cron: '* * * * *'  # Mỗi phút
```

### Chạy thủ công

1. Vào repository > Actions
2. Chọn workflow "Auto Stock Price Updater"
3. Click "Run workflow"

### Chạy local

```bash
# Cài đặt dependencies
pip install -r requirements.txt

# Set environment variable
export GOOGLE_CREDENTIALS_JSON='{"your":"json_content"}'

# Chạy script
python github_stock_updater.py
```

## 📊 Cấu trúc dữ liệu

### Google Sheets Format

| Cột | Mô tả | Ví dụ |
|-----|-------|-------|
| C | Mã cổ phiếu | VCB, HPG, VNM |
| H | Giá cổ phiếu | 85.5, 23.8, 67.2 |

### Log Output

```
🚀 BẮT ĐẦU AUTO CẬP NHẬT GIÁ CỔ PHIẾU
⏰ Khoảng thời gian: 1 phút
🔄 Chế độ: Auto (Realtime khi thị trường mở, Đóng cửa khi thị trường đóng)
============================================================
✅ Kết nối Google Sheets thành công!
🔍 Tìm thấy 10 mã cổ phiếu để cập nhật.
🤖 Thị trường đang mở → Sử dụng REALTIME
  - VCB: 85.5 (realtime)
  - HPG: 23.8 (realtime)
  - VNM: 67.2 (realtime)
✅ Cập nhật thành công 10/10 mã!
📊 Tỷ lệ thành công: 100.0%
🕐 Thời gian cập nhật: 14:30:25 15/12/2024
📊 Chế độ sử dụng: REALTIME
```

## ⚙️ Tùy chỉnh

### Thay đổi interval

Sửa file `.github/workflows/stock_updater.yml`:

```yaml
schedule:
  - cron: '*/5 * * * *'  # Mỗi 5 phút
  - cron: '0 */1 * * *'  # Mỗi giờ
```

### Thay đổi thời gian thị trường

Sửa function `is_market_open()` trong `github_stock_updater.py`:

```python
# Thời gian mở cửa: 9:00 - 15:00 (giờ Việt Nam)
market_open = time(9, 0)
market_close = time(15, 0)
```

## 🔍 Troubleshooting

### Lỗi kết nối Google Sheets

1. Kiểm tra Google Sheets API đã được bật
2. Kiểm tra Service Account có quyền truy cập
3. Kiểm tra secret `GOOGLE_CREDENTIALS_JSON` đã được cấu hình

### Lỗi lấy dữ liệu cổ phiếu

1. Kiểm tra mã cổ phiếu có đúng định dạng
2. Kiểm tra kết nối internet
3. Kiểm tra API vnstock có hoạt động

### Lỗi GitHub Actions

1. Kiểm tra logs trong Actions tab
2. Kiểm tra cron syntax
3. Kiểm tra permissions của workflow

## 📝 License

MIT License - Xem file LICENSE để biết thêm chi tiết.

## 🤝 Đóng góp

Mọi đóng góp đều được chào đón! Vui lòng:

1. Fork repository
2. Tạo feature branch
3. Commit changes
4. Push to branch
5. Tạo Pull Request

## 📞 Hỗ trợ

Nếu gặp vấn đề, vui lòng:

1. Kiểm tra Issues tab
2. Tạo issue mới với mô tả chi tiết
3. Đính kèm logs và screenshots nếu cần

---

**Lưu ý**: Đây là tool tự động, không đảm bảo 100% chính xác. Vui lòng kiểm tra dữ liệu trước khi sử dụng cho mục đích đầu tư.

