import sys
import os
import subprocess

print("======================================================")
print("=== BẮT ĐẦU CHẨN ĐOÁN MÔI TRƯỜNG PYTHON ===")
print("======================================================")

try:
    print(f"\n[INFO] Phiên bản Python đang chạy (sys.version):")
    print(sys.version)

    print(f"\n[INFO] Đường dẫn đến file thực thi Python (sys.executable):")
    print(sys.executable)

    print(f"\n[INFO] Thư mục làm việc hiện tại (os.getcwd()):")
    print(os.getcwd())

    print(f"\n[INFO] Danh sách đường dẫn tìm kiếm module (sys.path):")
    for path in sys.path:
        print(f"  - {path}")

    print("\n[INFO] Biến môi trường PYTHONPATH (os.environ.get('PYTHONPATH')):")
    print(os.environ.get('PYTHONPATH', '==> Không được thiết lập <=='))

    print("\n[INFO] Chạy lệnh 'pip list' từ bên trong script:")
    result = subprocess.run([sys.executable, '-m', 'pip', 'list'], capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print("\n[ERROR] Lỗi từ pip list:")
        print(result.stderr)

    print("\n======================================================")
    print("=== KẾT THÚC CHẨN ĐOÁN, BẮT ĐẦU IMPORT THƯ VIỆN ===")
    print("======================================================")

    # Bây giờ, chúng ta sẽ cố gắng import
    from pyrogram import Client
    print("✅ Import 'pyrogram' thành công!")
    from fastapi import FastAPI
    print("✅ Import 'fastapi' thành công!")
    from seleniumwire import webdriver
    print("✅ Import 'selenium-wire' thành công!")
    from uvicorn import Config
    print("✅ Import 'uvicorn' thành công!")

    print("\n\n>>> KẾT LUẬN: TẤT CẢ THƯ VIỆN ĐỀU CÓ THỂ IMPORT. NẾU BẠN THẤY DÒNG NÀY, LỖI NẰM Ở TRUENAS CACHING.")

except ImportError as e:
    print("\n\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    print(f"!!!!!! GẶP LỖI IMPORT NGAY SAU KHI CHẨN ĐOÁN !!!!!!")
    print(f"!!!!!! Lỗi cụ thể: {e}")
    print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    # In lại thông báo lỗi gốc để TrueNAS nhận diện
    print("\nLỖI: Thiếu thư viện. Vui lòng chạy: pip install --upgrade pyrogram tgcrypto selenium-wire webdriver-manager fastapi uvicorn[standard]")

except Exception as e:
    print(f"\n\n!!!!!! GẶP LỖI KHÁC KHÔNG PHẢI IMPORT ERROR: {e} !!!!!!")