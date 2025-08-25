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
    import time
    
    try:
        # Thêm delay để tránh bị block
        time.sleep(0.5)
        
        # Sử dụng stock method với timeout
        vs = vnstock.Vnstock()
        stock_data = vs.stock(symbol=ticker_clean)
        quote_dict = vars(stock_data.quote)
        
        # Thử truy cập trực tiếp vào data_source để lấy dữ liệu gần nhất
        try:
            if hasattr(stock_data.quote, 'data_source') and stock_data.quote.data_source is not None:
                # Lấy dữ liệu gần nhất (có thể là realtime)
                from datetime import datetime, timedelta
                start_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
                historical_data = stock_data.quote.data_source.history(start_date)
                
                if historical_data is not None and len(historical_data) > 0:
                    latest_data = historical_data.iloc[-1]
                    
                    # Kiểm tra xem dữ liệu có phải là hôm nay không
                    trading_date = latest_data.get('time', '')
                    today = datetime.now().strftime('%Y-%m-%d')
                    
                    # Kiểm tra thời gian hiện tại để xác định loại dữ liệu
                    vn_tz = pytz.timezone('Asia/Ho_Chi_Minh')
                    now = datetime.now(vn_tz)
                    current_time = now.time()
                    
                    # Kiểm tra xem có phải ngày hôm nay không (chỉ so sánh phần ngày)
                    trading_date_only = str(trading_date).split(' ')[0] if trading_date else ''
                    
                    # Kiểm tra xem có phải ngày hôm nay không
                    if trading_date_only == today:
                        # Kiểm tra thị trường có đang mở không
                        if 9 <= current_time.hour < 15:
                            if 'lastPrice' in latest_data and latest_data['lastPrice'] is not None:
                                price = latest_data['lastPrice']
                                if isinstance(price, (np.integer, np.floating)):
                                    price = float(price)
                                return price, "realtime (today lastPrice - market open)"
                            elif 'close' in latest_data and latest_data['close'] is not None:
                                price = latest_data['close']
                                if isinstance(price, (np.integer, np.floating)):
                                    price = float(price)
                                return price, "realtime (today close - market open)"
                        else:
                            if 'lastPrice' in latest_data and latest_data['lastPrice'] is not None:
                                price = latest_data['lastPrice']
                                if isinstance(price, (np.integer, np.floating)):
                                    price = float(price)
                                return price, "realtime (today close - market closed)"
                            elif 'close' in latest_data and latest_data['close'] is not None:
                                price = latest_data['close']
                                if isinstance(price, (np.integer, np.floating)):
                                    price = float(price)
                                return price, "realtime (today close - market closed)"
                    else:
                        if 'lastPrice' in latest_data and latest_data['lastPrice'] is not None:
                            price = latest_data['lastPrice']
                            if isinstance(price, (np.integer, np.floating)):
                                price = float(price)
                            return price, "realtime (latest lastPrice)"
                        elif 'close' in latest_data and latest_data['close'] is not None:
                            price = latest_data['close']
                            if isinstance(price, (np.integer, np.floating)):
                                price = float(price)
                            return price, "realtime (latest close)"
        except Exception as hist_error:
            pass
        
        # Thử các key khác trong quote_dict
        price = None
        price_source = "unknown"
        
        for key in ['lastPrice', 'close', 'price', 'currentPrice', 'last_price']:
            if key in quote_dict and quote_dict[key] is not None:
                price = quote_dict[key]
                price_source = key
                break
        
        if price is not None:
            if isinstance(price, (np.integer, np.floating)):
                price = float(price)
            return price, f"realtime ({price_source})"
        else:
            return "N/A", "không có dữ liệu realtime"
            
    except Exception as e:
        return "Lỗi", f"Lỗi realtime: {e}"

# ====== 3. LẤY GIÁ ĐÓNG CỬA ======
def get_closing_price(ticker_clean):
    """Lấy giá đóng cửa gần nhất của mã cổ phiếu"""
    import time
    
    try:
        # Thêm delay để tránh bị block
        time.sleep(0.5)
        
        # Sử dụng stock method với timeout
        vs = vnstock.Vnstock()
        stock_data = vs.stock(symbol=ticker_clean)
        
        # Lấy dữ liệu 7 ngày gần nhất
        from datetime import datetime, timedelta
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        historical_data = stock_data.quote.data_source.history(start_date)
        
        if historical_data is not None and len(historical_data) > 0:
            # Lấy giá đóng cửa của ngày giao dịch gần nhất
            latest_data = historical_data.iloc[-1]  # Lấy dòng cuối cùng
            close_price = latest_data.get('close', 'N/A')
            trading_date = latest_data.get('time', 'N/A')
            
            # Chuyển đổi numpy types thành Python native types
            if isinstance(close_price, (np.integer, np.floating)):
                close_price = float(close_price)
            if isinstance(trading_date, np.datetime64):
                trading_date = str(trading_date)
            
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
            # Thử đọc từ các file credentials có sẵn
            credential_files = [
                'google_credentials.json',
                'create-462716-fb36b6cea72a.json',
                'GOOGLE_CREDENTIALS_.json'
            ]
            
            for file_path in credential_files:
                if os.path.exists(file_path):
                    try:
                        with open(file_path, 'r') as f:
                            credentials_json = f.read()
                        print(f"✅ Đã tìm thấy credentials trong file: {file_path}")
                        break
                    except Exception as e:
                        print(f"⚠️ Không thể đọc file {file_path}: {e}")
                        continue
            
            if not credentials_json:
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
        
        # Lọc bỏ các mã rỗng
        tickers = [ticker for ticker in tickers if ticker and str(ticker).strip()]
        
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
        batch_size = 5  # Giảm batch size để tránh timeout
        for i in range(0, len(tickers), batch_size):
            batch_tickers = tickers[i:i+batch_size]
            
            for ticker in batch_tickers:
                if not ticker:
                    prices_to_update.append([""])
                    continue
                
                ticker_clean = str(ticker).strip().upper()
                
                # Bỏ qua các mã không hợp lệ
                if len(ticker_clean) < 2 or len(ticker_clean) > 5:
                    prices_to_update.append([""])
                    continue
                
                if mode == "realtime":
                    price, info = get_realtime_price(ticker_clean)
                else:
                    price, info = get_closing_price(ticker_clean)
                
                # Đảm bảo giá trị là string hoặc number, không phải numpy types
                if isinstance(price, (np.integer, np.floating)):
                    price = float(price)
                elif isinstance(price, (int, float)):
                    price = float(price)
                elif price not in ['N/A', 'Lỗi', '']:
                    try:
                        price = float(price)
                    except (ValueError, TypeError):
                        price = str(price)
                
                # Format giá trị để hiển thị đẹp hơn
                if isinstance(price, float):
                    # Làm tròn đến 2 chữ số thập phân
                    price = round(price, 2)
                
                # Đảm bảo giá trị hợp lệ trước khi thêm vào list
                if price not in ['N/A', 'Lỗi', '', None]:
                    prices_to_update.append([price])
                    success_count += 1
                else:
                    prices_to_update.append([""])
                
                # Giảm logging để tăng tốc - chỉ log mỗi 50 mã và các mã quan trọng
                if i % 50 == 0 or ticker_clean in ['VCB', 'HPG', 'VNM', 'FPT']:
                    print(f"  - {ticker_clean}: {price} ({info})")
        
        # Cập nhật Google Sheets - sử dụng batch update để tăng tốc
        if prices_to_update:
            try:
                # Sử dụng batch update để tăng tốc
                range_to_update = f"H2:H{len(prices_to_update) + 1}"
                
                # Đảm bảo tất cả giá trị đều hợp lệ
                valid_prices = []
                for price_list in prices_to_update:
                    price = price_list[0] if price_list else ""
                    if price and price not in ['N/A', 'Lỗi', '', None]:
                        valid_prices.append([price])
                    else:
                        valid_prices.append([""])
                
                worksheet.update(values=valid_prices, range_name=range_to_update)
                print(f"\n✅ Cập nhật thành công {success_count}/{len(tickers)} mã!")
                
                # Kiểm tra xem dữ liệu đã được cập nhật chưa
                try:
                    # Đọc lại một vài giá trị để kiểm tra
                    check_range = f"H2:H{min(5, len(valid_prices) + 1)}"
                    updated_values = worksheet.get(check_range)
                    print(f"🔍 Kiểm tra cập nhật: {len(updated_values)} giá trị đã được lưu")
                except Exception as check_error:
                    print(f"⚠️ Không thể kiểm tra dữ liệu đã cập nhật: {check_error}")
                
            except Exception as e:
                print(f"⚠️ Lỗi khi cập nhật Google Sheets: {e}")
                print(f"🔍 Debug: Số lượng giá trị: {len(prices_to_update)}")
                print(f"🔍 Debug: Giá trị đầu tiên: {prices_to_update[0] if prices_to_update else 'None'}")
                
                # Thử lại với phương pháp khác
                try:
                    print("🔄 Thử phương pháp cập nhật từng ô...")
                    for i, price_list in enumerate(prices_to_update, start=2):
                        price = price_list[0] if price_list else ""
                        if price and price not in ['N/A', 'Lỗi', '', None]:
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
                    print(f"⏰ Thời gian chạy: {runtime_minutes:.1f} phút / {_max_runtime_minutes} phút")
                    
                    print("🔄 Khởi động lại workflow...")
                    print("💡 Workflow sẽ được restart tự động bởi GitHub Actions schedule")
                    print("📊 Exit code 100 là bình thường - đây là tín hiệu restart")
                    
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
            
            # Thêm delay ngẫu nhiên để tránh bị block
            import random
            random_delay = random.uniform(55, 65)  # Delay 55-65 giây
            time_module.sleep(random_delay)
                
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
