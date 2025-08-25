import gspread
from google.oauth2.service_account import Credentials
from vnstock import Vnstock
from datetime import datetime, time
import pytz

# ====== 1. KIỂM TRA THỜI GIAN THỊ TRƯỜNG ======
def is_market_open():
    """Kiểm tra xem thị trường chứng khoán Việt Nam có đang mở cửa không"""
    # Lấy thời gian hiện tại ở múi giờ Việt Nam
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
def get_realtime_price(vs, ticker_clean):
    """Lấy giá realtime của mã cổ phiếu"""
    import time
    
    try:
        # Thêm delay để tránh bị block
        time.sleep(0.5)
        
        # Sử dụng stock method với timeout
        stock_data = vs.stock(symbol=ticker_clean)
        quote_dict = vars(stock_data.quote)
        
        # Debug: In ra tất cả các key có sẵn (chỉ cho 3 mã đầu tiên)
        if ticker_clean in ['GEG', 'NVL', 'DCM']:
            print(f"🔍 Debug {ticker_clean}: Các key có sẵn: {list(quote_dict.keys())}")
        
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
                                return latest_data['lastPrice'], "realtime (today lastPrice - market open)"
                            elif 'close' in latest_data and latest_data['close'] is not None:
                                return latest_data['close'], "realtime (today close - market open)"
                        else:
                            if 'lastPrice' in latest_data and latest_data['lastPrice'] is not None:
                                return latest_data['lastPrice'], "realtime (today close - market closed)"
                            elif 'close' in latest_data and latest_data['close'] is not None:
                                return latest_data['close'], "realtime (today close - market closed)"
                    else:
                        if 'lastPrice' in latest_data and latest_data['lastPrice'] is not None:
                            return latest_data['lastPrice'], "realtime (latest lastPrice)"
                        elif 'close' in latest_data and latest_data['close'] is not None:
                            return latest_data['close'], "realtime (latest close)"
        except Exception as hist_error:
            if ticker_clean in ['GEG', 'NVL', 'DCM']:
                print(f"⚠️  Không thể lấy dữ liệu từ data_source cho {ticker_clean}: {hist_error}")
        
        # Thử các key khác trong quote_dict
        price = None
        price_source = "unknown"
        
        for key in ['lastPrice', 'close', 'price', 'currentPrice', 'last_price']:
            if key in quote_dict and quote_dict[key] is not None:
                price = quote_dict[key]
                price_source = key
                break
        
        if price is not None:
            return price, f"realtime ({price_source})"
        else:
            return "N/A", "không có dữ liệu realtime"
            
    except Exception as e:
        return "Lỗi", f"Lỗi realtime: {e}"

# ====== 3. LẤY GIÁ ĐÓNG CỬA ======
def get_closing_price(vs, ticker_clean):
    """Lấy giá đóng cửa gần nhất của mã cổ phiếu"""
    try:
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
            return close_price, f"đóng cửa ({trading_date})"
        else:
            return "N/A", "không có dữ liệu lịch sử"
    except Exception as e:
        return "Lỗi", f"Lỗi đóng cửa: {e}"

# ====== 4. HIỂN THỊ MENU LỰA CHỌN ======
def show_menu():
    """Hiển thị menu lựa chọn chế độ lấy dữ liệu"""
    print("\n" + "="*60)
    print("📊 CHỌN CHẾ ĐỘ LẤY DỮ LIỆU CỔ PHIẾU VIỆT NAM")
    print("="*60)
    print()
    print("1️⃣  REALTIME - Giá thời gian thực")
    print("    ✅ Ưu điểm: Dữ liệu mới nhất, chính xác")
    print("    ⚠️  Hạn chế: Chỉ hoạt động khi thị trường mở (9:00-15:00, Thứ 2-6)")
    print("    💡 Phù hợp: Theo dõi giá trong giờ giao dịch")
    print()
    print("2️⃣  ĐÓNG CỬA - Giá đóng cửa gần nhất")
    print("    ✅ Ưu điểm: Hoạt động 24/7, dữ liệu ổn định")
    print("    📅 Dữ liệu: Giá đóng cửa của ngày giao dịch gần nhất")
    print("    💡 Phù hợp: Phân tích dài hạn, báo cáo cuối ngày")
    print()
    print("3️⃣  AUTO - Tự động chọn thông minh")
    print("    🤖 Tự động: Thị trường mở → REALTIME, Thị trường đóng → ĐÓNG CỬA")
    print("    ✅ Ưu điểm: Tối ưu nhất, không cần suy nghĩ")
    print("    💡 Phù hợp: Sử dụng hàng ngày, tự động hóa")
    print()
    print("4️⃣  MÃ RIÊNG - Cập nhật 1 mã cổ phiếu cụ thể")
    print("    🎯 Tính năng: Nhập mã cổ phiếu (VD: VCB, HPG, VNM...)")
    print("    ✅ Ưu điểm: Nhanh chóng, chỉ cần 1 mã")
    print("    💡 Phù hợp: Kiểm tra nhanh, test thử nghiệm")
    print()
    print("5️⃣  VÒNG LẶP - Tự động cập nhật định kỳ")
    print("    🔄 Tính năng: Chạy liên tục với khoảng thời gian tùy chọn")
    print("    ⏰ Tùy chọn: 1, 5, 15, 30 phút hoặc tùy chỉnh")
    print("    💡 Phù hợp: Theo dõi giá liên tục, tự động hóa hoàn toàn")
    print()
    print("="*60)
    print("💡 GHI CHÚ:")
    print("   • Thị trường VN mở cửa: 9:00-15:00 (Thứ 2-6)")
    print("   • Ngoài giờ giao dịch: Chọn lựa chọn 2 hoặc 3")
    print("   • Lần đầu sử dụng: Khuyến nghị chọn 3 (AUTO)")
    print("   • Mã cổ phiếu: Nhập mã 3 ký tự (VD: VCB, HPG, VNM)")
    print("   • Vòng lặp: Nhấn Ctrl+C để dừng")
    print("="*60)
    
    while True:
        choice = input("\n🎯 Nhập lựa chọn của bạn (1/2/3/4/5): ").strip()
        if choice in ['1', '2', '3', '4', '5']:
            return choice
        else:
            print("❌ Lựa chọn không hợp lệ. Vui lòng nhập 1, 2, 3, 4 hoặc 5.")
            print("💡 Gợi ý: Nhập '3' để sử dụng chế độ tự động thông minh!")

# ====== 5. LẤY MÃ CỔ PHIẾU RIÊNG ======
def get_single_ticker():
    """Lấy mã cổ phiếu từ người dùng"""
    print("\n" + "="*50)
    print("🎯 NHẬP MÃ CỔ PHIẾU CẦN CẬP NHẬT")
    print("="*50)
    print("💡 Ví dụ: VCB, HPG, VNM, FPT, MSN, VIC...")
    print("💡 Lưu ý: Nhập mã 3 ký tự, không cần dấu cách")
    print("="*50)
    
    while True:
        ticker = input("\n📈 Nhập mã cổ phiếu: ").strip().upper()
        if len(ticker) >= 2 and len(ticker) <= 5:  # Kiểm tra độ dài hợp lý
            return ticker
        else:
            print("❌ Mã cổ phiếu không hợp lệ. Vui lòng nhập mã 2-5 ký tự.")
            print("💡 Ví dụ: VCB, HPG, VNM, FPT...")

# ====== 6. CẤU HÌNH VÒNG LẶP ======
def get_loop_config():
    """Lấy cấu hình vòng lặp từ người dùng"""
    print("\n" + "="*50)
    print("🔄 CẤU HÌNH VÒNG LẶP TỰ ĐỘNG")
    print("="*50)
    print("⏰ Chọn khoảng thời gian giữa các lần cập nhật:")
    print("   1️⃣  1 phút  - Cập nhật rất nhanh")
    print("   2️⃣  5 phút  - Cập nhật nhanh (khuyến nghị)")
    print("   3️⃣  15 phút - Cập nhật vừa phải")
    print("   4️⃣  30 phút - Cập nhật chậm")
    print("   5️⃣  Tùy chỉnh - Nhập số phút tùy ý")
    print("="*50)
    
    while True:
        interval_choice = input("\n⏰ Chọn khoảng thời gian (1/2/3/4/5): ").strip()
        if interval_choice == '1':
            return 1
        elif interval_choice == '2':
            return 5
        elif interval_choice == '3':
            return 15
        elif interval_choice == '4':
            return 30
        elif interval_choice == '5':
            while True:
                try:
                    custom_minutes = int(input("⏰ Nhập số phút: "))
                    if 1 <= custom_minutes <= 1440:  # Tối đa 24 giờ
                        return custom_minutes
                    else:
                        print("❌ Vui lòng nhập số từ 1-1440 phút.")
                except ValueError:
                    print("❌ Vui lòng nhập số hợp lệ.")
        else:
            print("❌ Lựa chọn không hợp lệ. Vui lòng nhập 1, 2, 3, 4 hoặc 5.")

# ====== 7. CHẠY VÒNG LẶP ======
def run_loop_mode(worksheet, vs, interval_minutes):
    """Chạy chế độ vòng lặp"""
    import time
    from datetime import datetime, timedelta
    
    print(f"\n🔄 BẮT ĐẦU CHẾ ĐỘ VÒNG LẶP")
    print(f"⏰ Khoảng thời gian: {interval_minutes} phút")
    print(f"💡 Nhấn Ctrl+C để dừng vòng lặp")
    print("="*60)
    
    loop_count = 0
    
    try:
        while True:
            loop_count += 1
            vn_tz = pytz.timezone('Asia/Ho_Chi_Minh')
            now = datetime.now(vn_tz)
            
            print(f"\n🔄 LẦN CẬP NHẬT THỨ {loop_count}")
            print(f"🕐 Thời gian: {now.strftime('%H:%M:%S %d/%m/%Y')}")
            print("-" * 40)
            
            # Xác định chế độ dựa trên thời gian thị trường
            if is_market_open():
                mode = "realtime"
                print("🤖 Thị trường đang mở → Sử dụng REALTIME")
            else:
                mode = "closing"
                print("🤖 Thị trường đóng cửa → Sử dụng ĐÓNG CỬA")
            
            # Lấy danh sách mã cổ phiếu
            tickers = worksheet.col_values(3)[1:]
            print(f"🔍 Cập nhật {len(tickers)} mã cổ phiếu...")
            
            # Lấy giá và cập nhật
            prices_to_update = []
            success_count = 0
            
            for ticker in tickers:
                if not ticker:
                    prices_to_update.append([""])
                    continue
                
                ticker_clean = str(ticker).strip().upper()
                
                if mode == "realtime":
                    price, info = get_realtime_price(vs, ticker_clean)
                else:
                    price, info = get_closing_price(vs, ticker_clean)
                
                prices_to_update.append([price])
                if price not in ['N/A', 'Lỗi', '']:
                    success_count += 1
                
                print(f"  - {ticker_clean}: {price} ({info})")
            
            # Cập nhật Google Sheets
            try:
                range_to_update = f"H2:H{len(prices_to_update) + 1}"
                worksheet.update(values=prices_to_update, range_name=range_to_update)
                print(f"\n✅ Cập nhật thành công {success_count}/{len(tickers)} mã!")
            except Exception as e:
                print(f"❌ Lỗi khi cập nhật Google Sheets: {e}")
            
            # Thống kê
            success_rate = (success_count / len(tickers)) * 100 if tickers else 0
            print(f"📊 Tỷ lệ thành công: {success_rate:.1f}%")
            
            # Tính thời gian chờ tiếp theo
            next_update = now + timedelta(minutes=interval_minutes)
            print(f"⏰ Lần cập nhật tiếp theo: {next_update.strftime('%H:%M:%S')}")
            print("=" * 60)
            
            # Chờ đến lần cập nhật tiếp theo
            if loop_count < 999999:  # Tránh vòng lặp vô hạn
                print(f"⏳ Đang chờ {interval_minutes} phút... (Nhấn Ctrl+C để dừng)")
                time.sleep(interval_minutes * 60)
            else:
                print("🛑 Đã đạt giới hạn vòng lặp. Dừng chương trình.")
                break
                
    except KeyboardInterrupt:
        print(f"\n🛑 ĐÃ DỪNG VÒNG LẶP")
        print(f"📊 Tổng số lần cập nhật: {loop_count}")
        print("👋 Tạm biệt!")
    except Exception as e:
        print(f"\n❌ Lỗi trong vòng lặp: {e}")
        print("🔄 Thử lại sau 1 phút...")
        time.sleep(60)
        run_loop_mode(worksheet, vs, interval_minutes)

# ====== 5. KẾT NỐI GOOGLE SHEETS ======
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
KEY_FILE = "create-462716-fb36b6cea72a.json"
SHEET_URL = "https://docs.google.com/spreadsheets/d/1xuU1VzRtZtVlNE_GLzebROre4I5ZvwLnU3qGskY10BQ/edit?usp=sharing"

try:
    creds = Credentials.from_service_account_file(KEY_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_url(SHEET_URL)
    worksheet = spreadsheet.worksheet("Data_CP")
    print("✅ Kết nối Google Sheets thành công!")
except FileNotFoundError:
    print(f"❌ Lỗi: Không tìm thấy file '{KEY_FILE}'.")
    exit()
except Exception as e:
    print(f"❌ Lỗi khi kết nối Google Sheets: {e}")
    exit()

# ====== 6. HIỂN THỊ MENU VÀ LẤY LỰA CHỌN ======
choice = show_menu()

# ====== 7. XÁC ĐỊNH CHẾ ĐỘ HOẠT ĐỘNG ======
if choice == '3':  # AUTO mode
    if is_market_open():
        mode = "realtime"
        print("🤖 Chế độ AUTO: Thị trường đang mở → Sử dụng REALTIME")
    else:
        mode = "closing"
        vn_tz = pytz.timezone('Asia/Ho_Chi_Minh')
        now = datetime.now(vn_tz)
        print(f"🤖 Chế độ AUTO: Thị trường đóng cửa → Sử dụng ĐÓNG CỬA")
        print(f"   Thời gian hiện tại: {now.strftime('%H:%M:%S %d/%m/%Y')}")
elif choice == '1':  # REALTIME mode
    mode = "realtime"
    if not is_market_open():
        vn_tz = pytz.timezone('Asia/Ho_Chi_Minh')
        now = datetime.now(vn_tz)
        print(f"⚠️  Cảnh báo: Thị trường đang đóng cửa!")
        print(f"   Thời gian hiện tại: {now.strftime('%H:%M:%S %d/%m/%Y')}")
        print(f"   Thị trường mở cửa: 9:00 - 15:00 (Thứ 2-6)")
        print("   Dữ liệu realtime có thể không có sẵn.")
elif choice == '4':  # SINGLE TICKER mode
    # Xác định chế độ cho mã riêng (sử dụng AUTO logic)
    if is_market_open():
        mode = "realtime"
        print("🎯 Chế độ MÃ RIÊNG: Thị trường đang mở → Sử dụng REALTIME")
    else:
        mode = "closing"
        vn_tz = pytz.timezone('Asia/Ho_Chi_Minh')
        now = datetime.now(vn_tz)
        print(f"🎯 Chế độ MÃ RIÊNG: Thị trường đóng cửa → Sử dụng ĐÓNG CỬA")
        print(f"   Thời gian hiện tại: {now.strftime('%H:%M:%S %d/%m/%Y')}")
    
    # Lấy mã cổ phiếu từ người dùng
    single_ticker = get_single_ticker()
    print(f"🎯 Đã chọn mã: {single_ticker}")
elif choice == '5':  # LOOP mode
    # Chế độ vòng lặp sẽ được xử lý riêng
    pass
else:  # CLOSING mode
    mode = "closing"
    print("📈 Chế độ ĐÓNG CỬA: Lấy giá đóng cửa gần nhất")

print()

# ====== 8. XỬ LÝ CHẾ ĐỘ VÒNG LẶP ======
if choice == '5':  # LOOP mode
    # Khởi tạo vnstock
    vs = Vnstock()
    # Lấy cấu hình vòng lặp và chạy
    interval_minutes = get_loop_config()
    run_loop_mode(worksheet, vs, interval_minutes)
    exit()  # Thoát sau khi chạy xong vòng lặp

# ====== 9. LẤY DANH SÁCH MÃ CỔ PHIẾU TỪ CỘT C ======
if choice == '4':  # SINGLE TICKER mode
    tickers = [single_ticker]  # Chỉ xử lý 1 mã
    print(f"🎯 Cập nhật mã cổ phiếu: {single_ticker}")
else:
    tickers = worksheet.col_values(3)[1:]
    print(f"🔍 Đã tìm thấy {len(tickers)} mã cổ phiếu để cập nhật.")

# ====== 10. LẤY GIÁ MỚI VÀ TỔNG HỢP VÀO MỘT LIST ======
vs = Vnstock()
prices_to_update = []
print("⏳ Đang lấy dữ liệu giá cổ phiếu...")

for ticker in tickers:
    if not ticker:
        prices_to_update.append([""])
        continue

    ticker_clean = str(ticker).strip().upper()
    
    if mode == "realtime":
        price, info = get_realtime_price(vs, ticker_clean)
        prices_to_update.append([price])
        print(f"  - {ticker_clean}: {price} ({info})")
    else:  # closing mode
        price, info = get_closing_price(vs, ticker_clean)
        prices_to_update.append([price])
        print(f"  - {ticker_clean}: {price} ({info})")

# ====== 11. CẬP NHẬT GOOGLE SHEETS ======
if prices_to_update:
    try:
        if choice == '4':  # SINGLE TICKER mode
            # Tìm vị trí của mã trong cột C và cập nhật cột H tương ứng
            all_tickers = worksheet.col_values(3)
            try:
                ticker_index = all_tickers.index(single_ticker) + 1  # +1 vì index bắt đầu từ 0
                cell_address = f"H{ticker_index}"
                worksheet.update(values=[[prices_to_update[0][0]]], range_name=cell_address)  # Use named arguments
                print(f"\n✅ Cập nhật thành công mã {single_ticker} vào ô {cell_address}!")
            except ValueError:
                print(f"\n⚠️  Mã {single_ticker} không tìm thấy trong Google Sheets.")
                print("💡 Mã sẽ được thêm vào cuối danh sách.")
                # Thêm vào cuối danh sách
                worksheet.append_row([single_ticker, "", "", "", "", "", "", prices_to_update[0][0]])
                print(f"✅ Đã thêm mã {single_ticker} vào cuối danh sách!")
        else:
            # Cập nhật toàn bộ cột H như cũ
            range_to_update = f"H2:H{len(prices_to_update) + 1}"
            worksheet.update(values=prices_to_update, range_name=range_to_update)
            print(f"\n✅ Cập nhật thành công {len(prices_to_update)} mã vào cột H!")
        
        # Thông báo thêm về thời gian và chế độ
        vn_tz = pytz.timezone('Asia/Ho_Chi_Minh')
        now = datetime.now(vn_tz)
        mode_text = "REALTIME" if mode == "realtime" else "ĐÓNG CỬA"
        print(f"🕐 Thời gian cập nhật: {now.strftime('%H:%M:%S %d/%m/%Y')}")
        print(f"📊 Chế độ sử dụng: {mode_text}")
        
    except Exception as e:
        print(f"❌ Lỗi khi cập nhật Google Sheets: {e}")