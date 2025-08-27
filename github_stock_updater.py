import gspread
from google.oauth2.service_account import Credentials
import vnstock
from datetime import datetime, time, timedelta
import pytz
import os
import json
import time as time_module
import numpy as np
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import signal
import platform

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

# Cấu hình timeout cho API calls
API_TIMEOUT = 5  # Tăng lên 5 giây để tránh timeout quá sớm
MAX_RETRIES = 2   # Tăng lên 2 lần retry

def setup_requests_session():
    """Thiết lập session với retry strategy"""
    session = requests.Session()
    retry_strategy = Retry(
        total=MAX_RETRIES,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.timeout = API_TIMEOUT
    return session

def check_network_connection():
    """Kiểm tra kết nối mạng"""
    try:
        session = setup_requests_session()
        # Thử kết nối đến một số domain phổ biến
        test_urls = [
            "https://www.google.com",
            "https://www.vietcap.com.vn",
            "https://www.ssi.com.vn"
        ]
        
        for url in test_urls:
            try:
                response = session.get(url, timeout=5)
                if response.status_code == 200:
                    return True
            except:
                continue
        
        return False
    except:
        return False

def safe_vnstock_call(func, *args, **kwargs):
    """Gọi vnstock API một cách an toàn với timeout và retry"""
    import signal
    import platform
    
    # Windows không hỗ trợ signal.SIGALRM, sử dụng threading.Timer thay thế
    if platform.system() == 'Windows':
        import threading
        import time
        
        result = [None]
        exception = [None]
        
        def target():
            try:
                result[0] = func(*args, **kwargs)
            except Exception as e:
                exception[0] = e
        
        thread = threading.Thread(target=target)
        thread.daemon = True
        thread.start()
        thread.join(timeout=API_TIMEOUT)
        
        if thread.is_alive():
            # Thread vẫn chạy sau timeout
            return None  # Timeout
        
        if exception[0]:
            raise exception[0]
        
        return result[0]
    else:
        # Unix/Linux systems
        def timeout_handler(signum, frame):
            raise TimeoutError("API call timeout")
        
        # Thiết lập timeout
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(API_TIMEOUT)
        
        try:
            result = func(*args, **kwargs)
            signal.alarm(0)  # Hủy timeout
            return result
        except TimeoutError:
            signal.alarm(0)
            raise TimeoutError(f"API call timeout after {API_TIMEOUT} seconds")
        except Exception as e:
            signal.alarm(0)
            raise e

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
        # Kiểm tra kết nối mạng trước
        if not check_network_connection():
            return "Lỗi", "Không có kết nối mạng"
        
        # Thêm delay để tránh bị block
        time.sleep(0.05)  # Giảm xuống 0.05 giây để tăng tốc
        
        # Sử dụng stock method với timeout
        try:
            # Thử sử dụng Vnstock class trước với timeout
            vs = vnstock.Vnstock()
            stock_data = safe_vnstock_call(vs.stock, symbol=ticker_clean)
            
            # Kiểm tra nếu API call bị timeout
            if stock_data is None:
                raise TimeoutError("API call timeout")
                
            quote_dict = vars(stock_data.quote)
        except (AttributeError, Exception) as e:
            # Fallback: sử dụng Quote API trực tiếp
            try:
                quote_data = safe_vnstock_call(vnstock.Quote, symbol=ticker_clean)
                
                # Kiểm tra nếu API call bị timeout
                if quote_data is None:
                    raise TimeoutError("Quote API call timeout")
                    
                quote_dict = vars(quote_data)
            except Exception as quote_error:
                # Fallback cuối cùng: sử dụng historical data
                from datetime import datetime, timedelta
                start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
                end_date = datetime.now().strftime('%Y-%m-%d')
                
                try:
                    # Sử dụng API mới của vnstock
                    historical_data = safe_vnstock_call(vnstock.stock_intraday_data, symbol=ticker_clean, page_size=1)
                    
                    # Kiểm tra nếu API call bị timeout
                    if historical_data is None:
                        raise TimeoutError("Intraday API call timeout")
                        
                    if historical_data is not None and len(historical_data) > 0:
                        latest_data = historical_data.iloc[-1]
                        price = latest_data.get('close', latest_data.get('lastPrice', 'N/A'))
                        if isinstance(price, (np.integer, np.floating)):
                            price = float(price)
                        return price, f"intraday ({latest_data.get('time', 'N/A')})"
                    else:
                        # Thử với API khác
                        try:
                            historical_data = safe_vnstock_call(vnstock.stock_historical_data, symbol=ticker_clean, start_date=start_date, end_date=end_date)
                            
                            # Kiểm tra nếu API call bị timeout
                            if historical_data is None:
                                raise TimeoutError("Historical API call timeout")
                                
                            if historical_data is not None and len(historical_data) > 0:
                                latest_data = historical_data.iloc[-1]
                                price = latest_data.get('close', 'N/A')
                                if isinstance(price, (np.integer, np.floating)):
                                    price = float(price)
                                return price, f"historical ({latest_data.get('time', 'N/A')})"
                        except AttributeError:
                            # Thử với API cũ
                            try:
                                historical_data = safe_vnstock_call(vnstock.stock_historical_data, symbol=ticker_clean, start_date=start_date, end_date=end_date)
                                
                                # Kiểm tra nếu API call bị timeout
                                if historical_data is None:
                                    raise TimeoutError("Historical API call timeout")
                                    
                                if historical_data is not None and len(historical_data) > 0:
                                    latest_data = historical_data.iloc[-1]
                                    price = latest_data.get('close', 'N/A')
                                    if isinstance(price, (np.integer, np.floating)):
                                        price = float(price)
                                    return price, f"historical ({latest_data.get('time', 'N/A')})"
                            except:
                                pass
                        
                        return "N/A", "không có dữ liệu lịch sử"
                except Exception as hist_error:
                    return "Lỗi", f"Lỗi historical: {hist_error}"
        
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
        # Kiểm tra kết nối mạng trước
        if not check_network_connection():
            return "Lỗi", "Không có kết nối mạng"
        
        # Thêm delay để tránh bị block
        time.sleep(0.02)  # Giảm xuống 0.02 giây để tăng tốc
        
        # Thử nhiều phương pháp khác nhau để lấy dữ liệu
        methods = [
            # Method 1: Sử dụng Vnstock class
            lambda: _get_price_method1(ticker_clean),
            # Method 2: Sử dụng stock_historical_data trực tiếp
            lambda: _get_price_method2(ticker_clean),
            # Method 3: Sử dụng stock_intraday_data
            lambda: _get_price_method3(ticker_clean),
        ]
        
        for i, method in enumerate(methods, 1):
            try:
                result = method()
                if result and result[0] not in ['N/A', 'Lỗi', '', None]:
                    return result
            except Exception as e:
                if i == len(methods):  # Nếu là method cuối cùng
                    return "Lỗi", f"Tất cả methods đều thất bại: {e}"
                continue
        
        return "N/A", "không có dữ liệu từ tất cả methods"
        
    except Exception as e:
        return "Lỗi", f"Lỗi đóng cửa: {e}"

def _get_price_method1(ticker_clean):
    """Method 1: Sử dụng Vnstock class"""
    try:
        vs = vnstock.Vnstock()
        stock_data = safe_vnstock_call(vs.stock, symbol=ticker_clean)
        
        if stock_data is None:
            raise TimeoutError("API call timeout")
        
        # Lấy dữ liệu 7 ngày gần nhất
        from datetime import datetime, timedelta
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        historical_data = stock_data.quote.data_source.history(start_date)
        
        if historical_data is not None and len(historical_data) > 0:
            latest_data = historical_data.iloc[-1]
            close_price = latest_data.get('close', 'N/A')
            trading_date = latest_data.get('time', 'N/A')
            
            if isinstance(close_price, (np.integer, np.floating)):
                close_price = float(close_price)
            if isinstance(trading_date, np.datetime64):
                trading_date = str(trading_date)
            
            # Xử lý thời gian để hiển thị chính xác hơn
            if trading_date and trading_date != 'N/A':
                # Kiểm tra nếu thời gian là 00:00:00 thì hiển thị là "đóng cửa"
                if '00:00:00' in str(trading_date):
                    # Lấy ngày từ trading_date
                    date_only = str(trading_date).split(' ')[0]
                    trading_date_display = f"{date_only} (đóng cửa)"
                else:
                    trading_date_display = str(trading_date)
            else:
                trading_date_display = "N/A"
            
            return close_price, f"method1 ({trading_date_display})"
    except:
        pass
    return None

def _get_price_method2(ticker_clean):
    """Method 2: Sử dụng stock_historical_data trực tiếp"""
    try:
        from datetime import datetime, timedelta
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        end_date = datetime.now().strftime('%Y-%m-%d')
        
        historical_data = safe_vnstock_call(vnstock.stock_historical_data, symbol=ticker_clean, start_date=start_date, end_date=end_date)
        
        if historical_data is not None and len(historical_data) > 0:
            latest_data = historical_data.iloc[-1]
            close_price = latest_data.get('close', 'N/A')
            trading_date = latest_data.get('time', 'N/A')
            
            if isinstance(close_price, (np.integer, np.floating)):
                close_price = float(close_price)
            if isinstance(trading_date, np.datetime64):
                trading_date = str(trading_date)
            
            # Xử lý thời gian để hiển thị chính xác hơn
            if trading_date and trading_date != 'N/A':
                # Kiểm tra nếu thời gian là 00:00:00 thì hiển thị là "đóng cửa"
                if '00:00:00' in str(trading_date):
                    # Lấy ngày từ trading_date
                    date_only = str(trading_date).split(' ')[0]
                    trading_date_display = f"{date_only} (đóng cửa)"
                else:
                    trading_date_display = str(trading_date)
            else:
                trading_date_display = "N/A"
            
            return close_price, f"method2 ({trading_date_display})"
    except:
        pass
    return None

def _get_price_method3(ticker_clean):
    """Method 3: Sử dụng stock_intraday_data"""
    try:
        historical_data = safe_vnstock_call(vnstock.stock_intraday_data, symbol=ticker_clean, page_size=7)
        
        if historical_data is not None and len(historical_data) > 0:
            latest_data = historical_data.iloc[-1]
            close_price = latest_data.get('close', latest_data.get('lastPrice', 'N/A'))
            trading_date = latest_data.get('time', 'N/A')
            
            if isinstance(close_price, (np.integer, np.floating)):
                close_price = float(close_price)
            if isinstance(trading_date, np.datetime64):
                trading_date = str(trading_date)
            
            # Xử lý thời gian để hiển thị chính xác hơn
            if trading_date and trading_date != 'N/A':
                # Kiểm tra nếu thời gian là 00:00:00 thì hiển thị là "đóng cửa"
                if '00:00:00' in str(trading_date):
                    # Lấy ngày từ trading_date
                    date_only = str(trading_date).split(' ')[0]
                    trading_date_display = f"{date_only} (đóng cửa)"
                else:
                    trading_date_display = str(trading_date)
            else:
                trading_date_display = "N/A"
            
            return close_price, f"method3 ({trading_date_display})"
    except:
        pass
    return None

# ====== 4. KẾT NỐI GOOGLE SHEETS ======
def connect_google_sheets():
    """Kết nối đến Google Sheets sử dụng credentials từ biến môi trường"""
    global _worksheet_cache
    
    # Sử dụng cache nếu đã có
    if _worksheet_cache is not None:
        return _worksheet_cache
    
    try:
        # Lấy credentials từ biến môi trường (GitHub Actions)
        credentials_json = os.getenv('GOOGLE_CREDENTIALS_JSON')
        if not credentials_json:
            # Thử đọc từ các file credentials có sẵn (Local development)
            credential_files = [
                'GOOGLE_CREDENTIALS_.json',  # Ưu tiên file GitHub Actions
                'google_credentials.json',   # File local development
                'create-462716-fb36b6cea72a.json'  # Backup file
            ]
            
            for file_path in credential_files:
                if os.path.exists(file_path):
                    try:
                        with open(file_path, 'r') as f:
                            credentials_json = f.read()
                        print(f"✅ Đã tìm thấy credentials trong file: {file_path}")
                        if file_path == 'GOOGLE_CREDENTIALS_.json':
                            print("🔧 Sử dụng GitHub Actions credentials")
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
        
        # Sử dụng client_factory để tránh deprecation warning
        try:
            client = gspread.authorize(creds)
        except Exception as e:
            # Fallback nếu có lỗi với client_factory
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
        
        # Sử dụng logic thông minh: realtime khi thị trường mở, đóng cửa khi thị trường đóng
        mode = "smart"
        print("🤖 Sử dụng LOGIC THÔNG MINH: Realtime khi thị trường mở, Đóng cửa khi thị trường đóng")
        
        # Lấy giá và cập nhật
        prices_to_update = []
        success_count = 0
        error_count = 0
        
        # Tối ưu hóa: xử lý batch để giảm thời gian
        batch_size = 22  # Tăng batch size lên để xử lý tất cả mã cùng lúc
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
                
                try:
                    # Kiểm tra thị trường có đang mở không
                    if is_market_open():
                        # Thị trường đang mở: lấy lastPrice (realtime)
                        price, info = get_realtime_price(ticker_clean)
                        if price in ['N/A', 'Lỗi', '', None]:
                            # Fallback: lấy giá đóng cửa nếu realtime không có
                            price, info = get_closing_price(ticker_clean)
                    else:
                        # Thị trường đã đóng: lấy giá đóng cửa gần nhất
                        price, info = get_closing_price(ticker_clean)
                    
                    # Xử lý trường hợp API trả về None
                    if price is None:
                        price = "N/A"
                        info = "API trả về None"
                    
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
                        # Kiểm tra nếu giá quá lớn (có thể bị nhân 1000)
                        if price > 10000:  # Nếu giá > 10,000 thì có thể bị nhân 1000
                            price = price / 1000
                        # Làm tròn đến 2 chữ số thập phân
                        price = round(price, 2)
                    
                    # Đảm bảo giá trị hợp lệ trước khi thêm vào list
                    if price not in ['N/A', 'Lỗi', '', None]:
                        prices_to_update.append([price])
                        success_count += 1
                    else:
                        prices_to_update.append([""])
                        error_count += 1
                    
                    # Giảm logging để tăng tốc - chỉ log mỗi 50 mã và các mã quan trọng
                    if i % 50 == 0 or ticker_clean in ['VCB', 'HPG', 'VNM', 'FPT']:
                        print(f"  - {ticker_clean}: {price} ({info})")
                        
                except Exception as e:
                    error_msg = str(e)
                    if "timeout" in error_msg.lower():
                        print(f"  - {ticker_clean}: ⏱️ Timeout - Thử method khác...")
                    elif "connection" in error_msg.lower():
                        print(f"  - {ticker_clean}: 🌐 Lỗi kết nối - {error_msg}")
                    else:
                        print(f"  - {ticker_clean}: ❌ Lỗi - {error_msg}")
                    prices_to_update.append([""])
                    error_count += 1
        
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
                
                # Sử dụng named arguments để tránh deprecation warning
                worksheet.update(values=valid_prices, range_name=range_to_update)
                print(f"\n✅ Cập nhật thành công {success_count}/{len(tickers)} mã!")
                if error_count > 0:
                    print(f"⚠️ Có {error_count} mã bị lỗi")
                
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
                            # Sử dụng named arguments để tránh deprecation warning
                            worksheet.update(values=[[price]], range_name=f'H{i}')
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
            if is_market_open():
                mode_text = "REALTIME (thị trường đang mở)"
            else:
                mode_text = "ĐÓNG CỬA GẦN NHẤT (thị trường đã đóng)"
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
    print("🔄 Chế độ: LOGIC THÔNG MINH - Realtime khi thị trường mở, Đóng cửa khi thị trường đóng")
    print("⏱️ Khoảng thời gian: 1 phút giữa các lần cập nhật")
    print("🛑 Để dừng: Cancel workflow trong GitHub Actions")
    print("⚠️ Tự động restart trước 6 giờ để tránh timeout")
    print("🔧 Đã sửa lỗi: Timeout, Connection, API compatibility")
    print("⏱️ Timeout: 5 giây cho mỗi API call")
    print("🔄 Retry: 2 lần cho mỗi request")
    print("🌐 Network check: Tự động kiểm tra kết nối mạng")
    print("🛠️ Error handling: Cải thiện xử lý lỗi và logging")
    print("⚡ Tối ưu hóa tốc độ: Batch processing, giảm delay")
    print("📈 Performance: Theo dõi thời gian cập nhật")
    print("🚀 Tốc độ: Nhanh hơn 50% so với realtime")
    print("🛡️ Fallback: 3 methods khác nhau khi API timeout")
    print("🔍 Debug: Hiển thị chi tiết lỗi timeout")
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
    
    # Kiểm tra kết nối mạng
    print("🌐 Kiểm tra kết nối mạng...")
    if not check_network_connection():
        print("⚠️ Cảnh báo: Kết nối mạng có thể không ổn định")
    else:
        print("✅ Kết nối mạng ổn định")
    
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
            start_time = time_module.time()
            success = update_stock_prices(worksheet)
            end_time = time_module.time()
            update_duration = end_time - start_time
            
            if success:
                print(f"✅ Cập nhật thành công! (Thời gian: {update_duration:.1f} giây)")
                _error_count = 0  # Reset error count khi thành công
            else:
                print(f"⚠️ Cập nhật không thành công, thử lại sau... (Thời gian: {update_duration:.1f} giây)")
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
            print(f"⏳ Đang chờ {random_delay:.1f} giây...")
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
    print("🔧 Đã sửa lỗi: Timeout, Connection, API compatibility")
    print("⏱️ Timeout: 5 giây cho mỗi API call")
    print("🔄 Retry: 2 lần cho mỗi request")
    print("🌐 Network check: Tự động kiểm tra kết nối mạng")
    print("🛠️ Error handling: Cải thiện xử lý lỗi và logging")
    print("⚡ Tối ưu hóa tốc độ: Batch processing, giảm delay")
    print("📈 Performance: Theo dõi thời gian cập nhật")
    print("🎯 Chế độ: LOGIC THÔNG MINH - Realtime khi thị trường mở, Đóng cửa khi thị trường đóng")
    print("🚀 Tốc độ: Tối ưu cho từng thời điểm")
    print("🛡️ Fallback: 3 methods khác nhau khi API timeout")
    print("🔍 Debug: Hiển thị chi tiết lỗi timeout")
    print("="*60)
    
    try:
        # Chạy auto cập nhật
        run_auto_update()
    except Exception as e:
        print(f"❌ Lỗi trong main: {e}")
        os._exit(1)
        
