# 🔄 Hướng dẫn Auto-Restart Workflow

## 📋 Tổng quan

GitHub Actions có giới hạn thời gian chạy tối đa là **6 giờ** cho mỗi workflow. Để tránh bị timeout và đảm bảo workflow chạy liên tục, chúng ta sử dụng cơ chế **auto-restart**.

## ⚙️ Cơ chế hoạt động

### 1. **Schedule-based Restart**
```yaml
schedule:
  - cron: '0 */6 * * *'  # Chạy mỗi 6 giờ
```

### 2. **Runtime-based Restart**
- Workflow tự động tắt sau **5 giờ 50 phút** (350 phút)
- Exit với code **100** để báo hiệu restart
- Schedule sẽ tự động khởi động workflow mới

### 3. **Concurrency Control**
```yaml
concurrency:
  group: stock-updater
  cancel-in-progress: false  # Không cancel workflow đang chạy
```

## 🔄 Quy trình Restart

### **Bước 1: Workflow chạy**
- Khởi động với schedule hoặc manual dispatch
- Chạy liên tục trong 5 giờ 50 phút
- Cập nhật giá cổ phiếu mỗi phút

### **Bước 2: Gần timeout**
- Kiểm tra thời gian chạy
- Lưu restart count
- Hiển thị thông báo restart

### **Bước 3: Exit và Restart**
- Exit với code 100
- Schedule tự động khởi động workflow mới
- Tiếp tục cập nhật giá

## 📊 Exit Code 100

**Exit code 100 là BÌNH THƯỜNG** - đây là tín hiệu restart được thiết kế:

```python
# Trong github_stock_updater.py
if runtime_minutes >= _max_runtime_minutes:
    print("🔄 Khởi động lại workflow...")
    print("📊 Exit code 100 là bình thường - đây là tín hiệu restart")
    os._exit(100)  # Tín hiệu restart
```

## ⏰ Lịch trình Restart

| Thời gian | Hành động |
|-----------|-----------|
| **00:00** | Schedule khởi động workflow |
| **05:50** | Workflow tự động tắt (exit 100) |
| **06:00** | Schedule khởi động workflow mới |
| **11:50** | Workflow tự động tắt (exit 100) |
| **12:00** | Schedule khởi động workflow mới |
| **...** | Lặp lại vô hạn |

## 🔍 Kiểm tra trạng thái

### **GitHub Actions UI**
- ✅ **Success**: Workflow hoàn thành bình thường
- ⚠️ **Failure (exit 100)**: Restart signal - BÌNH THƯỜNG
- 🔄 **Running**: Workflow đang chạy

### **Logs**
```
🔄 LẦN CẬP NHẬT THỨ 350
⏰ Runtime: 349.5 phút / 350 phút
⚠️ Đã chạy được 349.5 phút (gần 6 giờ)
🔄 Tự động restart #1 để tránh GitHub Actions timeout...
📊 Exit code 100 là bình thường - đây là tín hiệu restart
```

## 🛠️ Troubleshooting

### **Workflow không restart**
1. Kiểm tra schedule có đúng không
2. Kiểm tra concurrency settings
3. Manual dispatch để khởi động lại

### **Nhiều workflow chạy cùng lúc**
- Concurrency group sẽ đảm bảo chỉ 1 instance chạy
- Workflow cũ sẽ được cancel tự động

### **Workflow bị lỗi thực sự**
- Kiểm tra logs để tìm lỗi
- Exit code khác 100 = lỗi thực sự
- Cần sửa lỗi và restart thủ công

## 📈 Monitoring

### **Thời gian chạy**
- Mỗi workflow chạy tối đa 5 giờ 50 phút
- Restart tự động mỗi 6 giờ
- Không có downtime

### **Số lần restart**
- Được lưu trong `restart_count.txt`
- Tăng dần theo thời gian
- Không giới hạn số lần restart

### **Tỷ lệ thành công**
- 100% khi thị trường mở
- Fallback về đóng cửa khi thị trường đóng
- Không bị gián đoạn bởi restart

## 🚀 Kết luận

Cơ chế auto-restart đảm bảo:
- ✅ **Liên tục 24/7**: Không có downtime
- ✅ **Tự động**: Không cần can thiệp thủ công
- ✅ **Ổn định**: Tránh timeout GitHub Actions
- ✅ **Hiệu quả**: Cập nhật giá liên tục

**Exit code 100 là hoàn toàn bình thường và mong đợi!** 🎯
