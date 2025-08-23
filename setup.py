#!/usr/bin/env python3
"""
Setup script cho Auto Stock Price Updater
Hướng dẫn cấu hình GitHub Actions và Google Sheets
"""

import os
import json
import sys

def print_banner():
    """In banner chào mừng"""
    print("="*60)
    print("📊 AUTO STOCK PRICE UPDATER - SETUP")
    print("="*60)
    print("Hướng dẫn cấu hình GitHub Actions và Google Sheets")
    print("="*60)

def check_requirements():
    """Kiểm tra các yêu cầu cơ bản"""
    print("\n🔍 KIỂM TRA YÊU CẦU...")
    
    # Kiểm tra Python version
    if sys.version_info < (3, 8):
        print("❌ Python 3.8+ là bắt buộc")
        return False
    
    print("✅ Python version:", sys.version.split()[0])
    
    # Kiểm tra các file cần thiết
    required_files = [
        'github_stock_updater.py',
        'requirements.txt',
        '.github/workflows/stock_updater.yml'
    ]
    
    for file in required_files:
        if os.path.exists(file):
            print(f"✅ {file}")
        else:
            print(f"❌ {file} - Không tìm thấy")
            return False
    
    print("✅ Tất cả file cần thiết đã có")
    return True

def setup_google_credentials():
    """Hướng dẫn setup Google credentials"""
    print("\n🔑 CẤU HÌNH GOOGLE CREDENTIALS...")
    print("1. Truy cập https://console.cloud.google.com/")
    print("2. Tạo project mới hoặc chọn project có sẵn")
    print("3. Bật Google Sheets API:")
    print("   - Vào 'APIs & Services' > 'Library'")
    print("   - Tìm 'Google Sheets API' và bật")
    print("4. Tạo Service Account:")
    print("   - Vào 'IAM & Admin' > 'Service Accounts'")
    print("   - Click 'Create Service Account'")
    print("   - Đặt tên: 'stock-updater'")
    print("   - Tạo key JSON và download")
    print("5. Chia sẻ Google Sheets với email service account")
    
    # Hỏi người dùng có muốn tạo file credentials mẫu không
    create_sample = input("\nBạn có muốn tạo file credentials mẫu không? (y/n): ").lower()
    if create_sample == 'y':
        sample_credentials = {
            "type": "service_account",
            "project_id": "your-project-id",
            "private_key_id": "your-private-key-id",
            "private_key": "-----BEGIN PRIVATE KEY-----\nYOUR_PRIVATE_KEY_HERE\n-----END PRIVATE KEY-----\n",
            "client_email": "stock-updater@your-project.iam.gserviceaccount.com",
            "client_id": "your-client-id",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/stock-updater%40your-project.iam.gserviceaccount.com"
        }
        
        with open('sample_credentials.json', 'w') as f:
            json.dump(sample_credentials, f, indent=2)
        
        print("✅ Đã tạo file sample_credentials.json")
        print("💡 Thay thế các giá trị 'your-*' bằng thông tin thực từ Google Cloud Console")

def setup_github_secrets():
    """Hướng dẫn setup GitHub secrets"""
    print("\n🔐 CẤU HÌNH GITHUB SECRETS...")
    print("1. Vào repository GitHub của bạn")
    print("2. Vào Settings > Secrets and variables > Actions")
    print("3. Click 'New repository secret'")
    print("4. Tên secret: GOOGLE_CREDENTIALS_JSON")
    print("5. Value: Copy toàn bộ nội dung file JSON credentials")
    print("6. Click 'Add secret'")
    
    print("\n💡 Lưu ý:")
    print("- Không bao giờ commit file credentials vào git")
    print("- Secret sẽ được mã hóa và chỉ có thể truy cập trong Actions")
    print("- Mỗi khi cập nhật credentials, cần update secret")

def setup_google_sheets():
    """Hướng dẫn setup Google Sheets"""
    print("\n📊 CẤU HÌNH GOOGLE SHEETS...")
    print("1. Tạo Google Sheets mới")
    print("2. Tạo sheet tên 'Data_CP'")
    print("3. Cấu trúc cột:")
    print("   - Cột C: Danh sách mã cổ phiếu")
    print("   - Cột H: Giá cổ phiếu (sẽ được cập nhật tự động)")
    print("4. Chia sẻ với email service account")
    print("5. Copy URL và cập nhật trong github_stock_updater.py")
    
    # Hỏi người dùng có muốn cập nhật URL không
    update_url = input("\nBạn có muốn cập nhật SHEET_URL trong code không? (y/n): ").lower()
    if update_url == 'y':
        new_url = input("Nhập URL Google Sheets: ").strip()
        if new_url:
            try:
                with open('github_stock_updater.py', 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Thay thế URL
                import re
                content = re.sub(
                    r'SHEET_URL = ".*?"',
                    f'SHEET_URL = "{new_url}"',
                    content
                )
                
                with open('github_stock_updater.py', 'w', encoding='utf-8') as f:
                    f.write(content)
                
                print("✅ Đã cập nhật SHEET_URL")
            except Exception as e:
                print(f"❌ Lỗi khi cập nhật URL: {e}")

def test_setup():
    """Test setup cơ bản"""
    print("\n🧪 TEST SETUP...")
    
    # Test import các thư viện
    try:
        import gspread
        import vnstock
        import pytz
        print("✅ Tất cả thư viện có thể import")
    except ImportError as e:
        print(f"❌ Lỗi import: {e}")
        print("💡 Chạy: pip install -r requirements.txt")
        return False
    
    # Test kết nối Google Sheets (nếu có credentials)
    if os.path.exists('google_credentials.json'):
        try:
            from github_stock_updater import connect_google_sheets
            worksheet = connect_google_sheets()
            if worksheet:
                print("✅ Kết nối Google Sheets thành công")
            else:
                print("⚠️ Không thể kết nối Google Sheets")
        except Exception as e:
            print(f"⚠️ Lỗi kết nối Google Sheets: {e}")
    else:
        print("⚠️ Chưa có file credentials để test")
    
    return True

def main():
    """Hàm chính"""
    print_banner()
    
    if not check_requirements():
        print("\n❌ Setup không thành công. Vui lòng kiểm tra lại.")
        return
    
    print("\n📋 MENU SETUP:")
    print("1. Cấu hình Google Credentials")
    print("2. Cấu hình GitHub Secrets")
    print("3. Cấu hình Google Sheets")
    print("4. Test setup")
    print("5. Tất cả các bước trên")
    print("0. Thoát")
    
    while True:
        choice = input("\nChọn option (0-5): ").strip()
        
        if choice == '0':
            print("👋 Tạm biệt!")
            break
        elif choice == '1':
            setup_google_credentials()
        elif choice == '2':
            setup_github_secrets()
        elif choice == '3':
            setup_google_sheets()
        elif choice == '4':
            test_setup()
        elif choice == '5':
            setup_google_credentials()
            setup_github_secrets()
            setup_google_sheets()
            test_setup()
            print("\n✅ Setup hoàn tất!")
            print("🚀 Bây giờ bạn có thể push code lên GitHub và Actions sẽ tự động chạy")
            break
        else:
            print("❌ Lựa chọn không hợp lệ")

if __name__ == "__main__":
    main()
