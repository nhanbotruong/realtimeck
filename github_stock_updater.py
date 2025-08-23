import gspread
from google.oauth2.service_account import Credentials
import vnstock
from datetime import datetime, time, timedelta
import pytz
import os
import json
import time as time_module

# ====== CẤU HÌNH GITHUB ACTIONS ======
SHEET_URL = "https://docs.google.com/spreadsheets/d/1xuU1VzRtZtVlNE_GLzebROre4I5ZvwLnU3qGskY10BQ/edit?usp=sharing"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

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
        # Sử dụng API mới của vnstock
        stock_data = vnstock.stock_intraday_data(symbol=ticker_clean, page_size=1)
        if stock_data is not None and len(stock_data) > 0:
            last_price = stock_data.iloc[0]['close']
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
            return close_price, f"đóng cửa ({trading_date})"
        else:
            return "N/A", "không có dữ liệu lịch sử"
    except Exception as e:
        return "Lỗi", f"Lỗi đóng cửa: {e}"

# ====== 4. KẾT NỐI GOOGLE SHEETS ======
def connect_google_sheets():
    """Kết nối đến Google Sheets sử dụng credentials từ biến môi trường"""
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
        spreadsheet = client.open_by_url(SHEET_URL)
        worksheet = spreadsheet.worksheet("Data_CP")
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
        
        for ticker in tickers:
            if not ticker:
                prices_to_update.append([""])
                continue
            
            ticker_clean = str(ticker).strip().upper()
            
            if mode == "realtime":
                price, info = get_realtime_price(ticker_clean)
            else:
                price, info = get_closing_price(ticker_clean)
            
            prices_to_update.append([price])
            if price not in ['N/A', 'Lỗi', '']:
                success_count += 1
            
            print(f"  - {ticker_clean}: {price} ({info})")
        
        # Cập nhật Google Sheets
        if prices_to_update:
            range_to_update = f"H2:H{len(prices_to_update) + 1}"
            worksheet.update(values=prices_to_update, range_name=range_to_update)
            print(f"\n✅ Cập nhật thành công {success_count}/{len(tickers)} mã!")
            
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
    """Chạy auto cập nhật với interval 1 phút"""
    print("🚀 BẮT ĐẦU AUTO CẬP NHẬT GIÁ CỔ PHIẾU")
    print("⏰ Khoảng thời gian: 1 phút")
    print("🔄 Chế độ: Auto (Realtime khi thị trường mở, Đóng cửa khi thị trường đóng)")
    print("="*60)
    
    # Kết nối Google Sheets
    worksheet = connect_google_sheets()
    if not worksheet:
        print("❌ Không thể kết nối Google Sheets. Thoát chương trình.")
        return
    
    loop_count = 0
    max_loops = 1440  # Tối đa 24 giờ (1440 phút)
    
    try:
        while loop_count < max_loops:
            loop_count += 1
            vn_tz = pytz.timezone('Asia/Ho_Chi_Minh')
            now = datetime.now(vn_tz)
            
            print(f"\n🔄 LẦN CẬP NHẬT THỨ {loop_count}")
            print(f"🕐 Thời gian: {now.strftime('%H:%M:%S %d/%m/%Y')}")
            print("-" * 40)
            
            # Cập nhật giá cổ phiếu
            success = update_stock_prices(worksheet)
            
            if not success:
                print("⚠️ Cập nhật không thành công, thử lại sau...")
            
            print("=" * 60)
            
            # Tính thời gian chờ tiếp theo
            next_update = now + timedelta(minutes=1)
            print(f"⏰ Lần cập nhật tiếp theo: {next_update.strftime('%H:%M:%S')}")
            
            # Chờ 1 phút trước khi cập nhật tiếp
            if loop_count < max_loops:
                print("⏳ Đang chờ 1 phút...")
                time_module.sleep(60)  # Chờ 60 giây
            else:
                print("🛑 Đã đạt giới hạn vòng lặp (24 giờ). Dừng chương trình.")
                break
                
    except KeyboardInterrupt:
        print(f"\n🛑 ĐÃ DỪNG AUTO CẬP NHẬT")
        print(f"📊 Tổng số lần cập nhật: {loop_count}")
    except Exception as e:
        print(f"\n❌ Lỗi trong auto cập nhật: {e}")
        print("🔄 Thử lại sau 1 phút...")
        time_module.sleep(60)
        run_auto_update()

# ====== 7. HÀM CHÍNH ======
if __name__ == "__main__":
    print("📊 GITHUB ACTIONS STOCK PRICE UPDATER")
    print("🔄 Auto cập nhật giá cổ phiếu Việt Nam mỗi 1 phút")
    print("="*60)
    
    # Chạy auto cập nhật
    run_auto_update()
