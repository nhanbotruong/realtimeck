import gspread
from google.oauth2.service_account import Credentials
import vnstock
from datetime import datetime, time, timedelta
import pytz
import os
import json
import time as time_module
import numpy as np

# ====== CẤU HÌNH GITHUB ACTIONS ======
SHEET_URL = "https://docs.google.com/spreadsheets/d/1xuU1VzRtZtVlNE_GLzebROre4I5ZvwLnU3qGskY10BQ/edit?usp=sharing"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

# Cache cho Google Sheets client
_worksheet_cache = None

# Biến để theo dõi lỗi liên tục
_error_count = 0
_max_errors = 5  # Số lỗi tối đa trước khi restart

# Biến để theo dõi thời gian chạy (GitHub Actions timeout: 6 giờ = 360 phút)
_start_time = None
_max_runtime_minutes = 350  # Restart trước 6 giờ để tránh timeout

# Biến để theo dõi restart count
_restart_count = 0
_max_restarts = float('inf')  # Vô hạn restart - chỉ dừng khi cancel thủ công

def load_restart_count():
    """Load restart count từ file"""
    global _restart_count
    try:
        if os.path.exists('restart_count.txt'):
            with open('restart_count.txt', 'r') as f:
                _restart_count = int(f.read().strip())
        else:
            _restart_count = 0
    except:
        _restart_count = 0

def save_restart_count():
    """Lưu restart count vào file"""
    try:
        with open('restart_count.txt', 'w') as f:
            f.write(str(_restart_count))
    except:
        pass

# ====== 1. KIỂM TRA THỜI GIAN THỊ TRƯỜNG ======
def is_market_open():
    """Kiểm tra xem thị trường chứng khoán Việt Nam có đang mở cửa không"""
    vn_tz = pytz.timezone('Asia/Ho_Chi_Minh')
    now = datetime.now(vn_tz)
    
    # Thời gian mở cửa: 9:00 - 15:00 (giờ Việt Nam)
    market_open = time(9, 0)
    market_close = time(15, 0)
    
    # Kiểm tra xem có phải ngày làm việc không (thứ 2-6)
    is_weekday = now.weekday() < 5  # 0=Monday, 4=Friday
    
    # Kiểm tra thời gian
    is_time_ok = market_open <= now.time() <= market_close
    
    return is_weekday and is_time_ok

# ====== 2. LẤY GIÁ REALTIME ======
def get_realtime_price(ticker_clean):
    """Lấy giá realtime của mã cổ phiếu"""
    try:
        # Sử dụng API mới của vnstock với timeout ngắn
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        
        # Tạo session với timeout ngắn
        session = requests.Session()
        retry = Retry(connect=1, backoff_factor=0.1)
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        
        # Sử dụng API mới của vnstock
        stock_data = vnstock.stock_intraday_data(symbol=ticker_clean, page_size=1)
        if stock_data is not None and len(stock_data) > 0:
            last_price = stock_data.iloc[0]['close']
            # Chuyển đổi numpy types thành Python native types
            if isinstance(last_price, (np.integer, np.floating)):
                last_price = float(last_price)
            # Chia cho 1000 để hiển thị đúng đơn vị (VND)
            if isinstance(last_price, (int, float)) and last_price > 1000:
                last_price = last_price / 1000
            return last_price, "realtime"
        else:
            return "N/A", "không có dữ liệu realtime"
    except Exception as e:
        return "Lỗi", f"Lỗi realtime: {e}"

# ====== 3. LẤY GIÁ ĐÓNG CỬA ======
def get_closing_price(ticker_clean):
    """Lấy giá đóng cửa gần nhất của mã cổ phiếu"""
    try:
        # Sử dụng API mới của vnstock
        from datetime import datetime, timedelta
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        end_date = datetime.now().strftime('%Y-%m-%d')
        
        stock_data = vnstock.stock_historical_data(symbol=ticker_clean, start_date=start_date, end_date=end_date)
        
        if stock_data is not None and len(stock_data) > 0:
            # Lấy giá đóng cửa của ngày giao dịch gần nhất
            latest_data = stock_data.iloc[-1]  # Lấy dòng cuối cùng
            close_price = latest_data['close']
            trading_date = latest_data['time']
            
            # Chuyển đổi numpy types thành Python native types
            if isinstance(close_price, (np.integer, np.floating)):
                close_price = float(close_price)
            if isinstance(trading_date, np.datetime64):
                trading_date = str(trading_date)
            
            # Chia cho 1000 để hiển thị đúng đơn vị (VND)
            if isinstance(close_price, (int, float)) and close_price > 1000:
                close_price = close_price / 1000
            
            return close_price, f"đóng cửa ({trading_date})"
        else:
            return "N/A", "không có dữ liệu lịch sử"
    except Exception as e:
        return "Lỗi", f"Lỗi đóng cửa: {e}"

# ====== 4. KẾT NỐI GOOGLE SHEETS ======
def connect_google_sheets():
    """Kết nối đến Google Sheets sử dụng credentials từ biến môi trường"""
    global _worksheet_cache
    
    # Sử dụng cache nếu đã có
    if _worksheet_cache is not None:
        return _worksheet_cache
    
    try:
        # Lấy credentials từ biến môi trường
        credentials_json = os.getenv('GOOGLE_CREDENTIALS_JSON')
        if not credentials_json:
            # Thử đọc từ file nếu không có biến môi trường
            if os.path.exists('google_credentials.json'):
                with open('google_credentials.json', 'r') as f:
                    credentials_json = f.read()
            else:
                print("❌ Không tìm thấy Google credentials. Vui lòng cấu hình GOOGLE_CREDENTIALS_JSON.")
                return None
        
        # Parse JSON credentials
        credentials_dict = json.loads(credentials_json)
        
        # Tạo credentials từ JSON
        creds = Credentials.from_service_account_info(credentials_dict, scopes=SCOPES)
        client = gspread.authorize(creds)
        
        # Thiết lập timeout cho Google Sheets API
        client.timeout = 30  # 30 giây timeout
        
        spreadsheet = client.open_by_url(SHEET_URL)
        worksheet = spreadsheet.worksheet("Data_CP")
        
        # Cache worksheet để tái sử dụng
        _worksheet_cache = worksheet
        
        print("✅ Kết nối Google Sheets thành công!")
        return worksheet
    except Exception as e:
        print(f"❌ Lỗi khi kết nối Google Sheets: {e}")
        return None

# ====== 5. CẬP NHẬT GIÁ CỔ PHIẾU ======
def update_stock_prices(worksheet):
    """Cập nhật giá cổ phiếu vào Google Sheets"""
    try:
        # Lấy danh sách mã cổ phiếu từ cột C
        tickers = worksheet.col_values(3)[1:]  # Bỏ qua header
        print(f"🔍 Tìm thấy {len(tickers)} mã cổ phiếu để cập nhật.")
        
        # Xác định chế độ dựa trên thời gian thị trường
        if is_market_open():
            mode = "realtime"
            print("🤖 Thị trường đang mở → Sử dụng REALTIME")
        else:
            mode = "closing"
            print("🤖 Thị trường đóng cửa → Sử dụng ĐÓNG CỬA")
        
        # Lấy giá và cập nhật
        prices_to_update = []
        success_count = 0
        
        # Tối ưu hóa: xử lý batch để giảm thời gian
        batch_size = 10  # Xử lý 10 mã một lần
        for i in range(0, len(tickers), batch_size):
            batch_tickers = tickers[i:i+batch_size]
            
            for ticker in batch_tickers:
                if not ticker:
                    prices_to_update.append([""])
                    continue
                
                ticker_clean = str(ticker).strip().upper()
                
                if mode == "realtime":
                    price, info = get_realtime_price(ticker_clean)
                else:
                    price, info = get_closing_price(ticker_clean)
                
                # Đảm bảo giá trị là string hoặc number, không phải numpy types
                if isinstance(price, (np.integer, np.floating)):
                    price = float(price)
                elif price not in ['N/A', 'Lỗi', '']:
                    price = str(price)
                
                prices_to_update.append([price])
                if price not in ['N/A', 'Lỗi', '']:
                    success_count += 1
                
                # Giảm logging để tăng tốc
                if i % 20 == 0:  # Chỉ log mỗi 20 mã
                    print(f"  - {ticker_clean}: {price} ({info})")
        
        # Cập nhật Google Sheets - sử dụng batch update để tăng tốc
        if prices_to_update:
            try:
                # Sử dụng batch update để tăng tốc
                range_to_update = f"H2:H{len(prices_to_update) + 1}"
                worksheet.update(values=prices_to_update, range_name=range_to_update)
                print(f"\n✅ Cập nhật thành công {success_count}/{len(tickers)} mã!")
            except Exception as e:
                print(f"⚠️ Lỗi khi cập nhật Google Sheets: {e}")
                # Thử lại với phương pháp khác
                try:
                    for i, price in enumerate(prices_to_update, start=2):
                        worksheet.update(f'H{i}', price)
                    print(f"✅ Cập nhật thành công với phương pháp thay thế!")
                except Exception as e2:
                    print(f"❌ Không thể cập nhật Google Sheets: {e2}")
                    return False
            
            # Thống kê
            success_rate = (success_count / len(tickers)) * 100 if tickers else 0
            print(f"📊 Tỷ lệ thành công: {success_rate:.1f}%")
            
            # Thông báo thời gian
            vn_tz = pytz.timezone('Asia/Ho_Chi_Minh')
            now = datetime.now(vn_tz)
            mode_text = "REALTIME" if mode == "realtime" else "ĐÓNG CỬA"
            print(f"🕐 Thời gian cập nhật: {now.strftime('%H:%M:%S %d/%m/%Y')}")
            print(f"📊 Chế độ sử dụng: {mode_text}")
            
            return True
        else:
            print("❌ Không có dữ liệu để cập nhật.")
            return False
            
    except Exception as e:
        print(f"❌ Lỗi khi cập nhật giá cổ phiếu: {e}")
        return False

# ====== 6. HÀM CHÍNH CHẠY AUTO CẬP NHẬT ======
def run_auto_update():
    """Chạy auto cập nhật vô thời hạn cho đến khi cancel thủ công"""
    global _start_time, _restart_count
    
    print("🚀 BẮT ĐẦU AUTO CẬP NHẬT GIÁ CỔ PHIẾU")
    print("⏰ Chế độ: Vô thời hạn (chạy cho đến khi cancel thủ công)")
    print("🔄 Chế độ: Auto (Realtime khi thị trường mở, Đóng cửa khi thị trường đóng)")
    print("⏱️ Khoảng thời gian: 1 phút giữa các lần cập nhật")
    print("🛑 Để dừng: Cancel workflow trong GitHub Actions")
    print("⚠️ Tự động restart trước 6 giờ để tránh timeout")
    print("="*60)
    
    # Load restart count
    load_restart_count()
    
    # Ghi lại thời gian bắt đầu
    _start_time = datetime.now()
    
    print(f"📊 Restart count hiện tại: {_restart_count} (vô hạn)")
    
    # Tính thời gian tổng cộng đã chạy
    total_runtime_hours = (_restart_count * _max_runtime_minutes) / 60
    if _restart_count > 0:
        print(f"⏰ Thời gian tổng cộng đã chạy: {total_runtime_hours:.1f} giờ")
    
    # Kết nối Google Sheets
    worksheet = connect_google_sheets()
    if not worksheet:
        print("❌ Không thể kết nối Google Sheets. Thoát chương trình.")
        return
    
    loop_count = 0
    
    try:
        while True:  # Chạy vô thời hạn
            loop_count += 1
            vn_tz = pytz.timezone('Asia/Ho_Chi_Minh')
            now = datetime.now(vn_tz)
            
            # Kiểm tra thời gian chạy để tránh timeout
            if _start_time:
                runtime_minutes = (datetime.now() - _start_time).total_seconds() / 60
                if runtime_minutes >= _max_runtime_minutes:
                    _restart_count += 1
                    print(f"\n⚠️ Đã chạy được {runtime_minutes:.1f} phút (gần 6 giờ)")
                    print(f"🔄 Tự động restart #{_restart_count} để tránh GitHub Actions timeout...")
                    print(f"📊 Tổng số lần cập nhật: {loop_count}")
                    print(f"📊 Số lần restart: {_restart_count} (vô hạn)")
                    
                    print("🔄 Khởi động lại workflow...")
                    # Lưu restart count trước khi exit
                    save_restart_count()
                    # Trigger restart bằng cách exit với code đặc biệt
                    os._exit(100)  # Exit code 100 để trigger restart
            
            print(f"\n🔄 LẦN CẬP NHẬT THỨ {loop_count}")
            print(f"🕐 Thời gian: {now.strftime('%H:%M:%S %d/%m/%Y')}")
            print(f"📊 Thời gian chạy: {loop_count} phút")
            if _start_time:
                runtime_minutes = (datetime.now() - _start_time).total_seconds() / 60
                remaining_minutes = _max_runtime_minutes - runtime_minutes
                print(f"⏰ Runtime: {runtime_minutes:.1f} phút / {_max_runtime_minutes} phút")
                print(f"⏰ Thời gian còn lại trước restart: {remaining_minutes:.1f} phút")
            print("-" * 40)
            
            # Cập nhật giá cổ phiếu
            success = update_stock_prices(worksheet)
            
            if success:
                print("✅ Cập nhật thành công!")
                _error_count = 0  # Reset error count khi thành công
            else:
                print("⚠️ Cập nhật không thành công, thử lại sau...")
                _error_count += 1
                print(f"⚠️ Lỗi liên tục: {_error_count}/{_max_errors}")
                
                # Thử kết nối lại Google Sheets nếu cần
                worksheet = connect_google_sheets()
                if not worksheet:
                    print("❌ Không thể kết nối lại Google Sheets. Thử lại sau...")
                    _error_count += 1
                
                # Nếu quá nhiều lỗi liên tục, restart
                if _error_count >= _max_errors:
                    print("🔄 Quá nhiều lỗi liên tục. Khởi động lại...")
                    _error_count = 0
                    time_module.sleep(60)  # Chờ 1 phút trước khi restart
            
            print("=" * 60)
            
            # Tính thời gian chờ tiếp theo
            next_update = now + timedelta(minutes=1)
            print(f"⏰ Lần cập nhật tiếp theo: {next_update.strftime('%H:%M:%S')}")
            
            # Chờ 1 phút trước khi cập nhật tiếp
            print("⏳ Đang chờ 1 phút...")
            time_module.sleep(60)  # Chờ 60 giây (1 phút)
                
    except KeyboardInterrupt:
        print(f"\n🛑 ĐÃ DỪNG AUTO CẬP NHẬT (Cancel thủ công)")
        print(f"📊 Tổng số lần cập nhật: {loop_count}")
    except Exception as e:
        print(f"\n❌ Lỗi trong auto cập nhật: {e}")
        print(f"📊 Đã chạy được {loop_count} lần cập nhật")
        print("🔄 Thử lại sau 30 giây...")
        time_module.sleep(30)
        print("🔄 Khởi động lại auto cập nhật...")
        run_auto_update()

# ====== 7. HÀM CHÍNH ======
if __name__ == "__main__":
    print("📊 GITHUB ACTIONS STOCK PRICE UPDATER")
    print("🔄 Auto cập nhật giá cổ phiếu Việt Nam liên tục (chạy cho đến khi cancel)")
    print("="*60)
    
    # Chạy auto cập nhật
    run_auto_update()
