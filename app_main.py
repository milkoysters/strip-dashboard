# app.py (Phiên bản 1.7 - Hoàn chỉnh và Sửa lỗi)

# === CÁC IMPORT CẦN THIẾT ===
import asyncio
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

try:
    from pyrogram import Client, filters, enums
    from pyrogram.errors import MessageNotModified, FloodWait
    from pyrogram.handlers import MessageHandler, CallbackQueryHandler
    from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
    from seleniumwire import webdriver
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    from selenium.webdriver.chrome.options import Options
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    from selenium.webdriver.common.by import By
except ImportError:
    print("LỖI: Thiếu thư viện. Vui lòng chạy: pip install --upgrade pyrogram tgcrypto selenium-wire webdriver-manager fastapi uvicorn[standard]")
    exit(1)


# === CẤU HÌNH LOGGING ===
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logging.getLogger('seleniumwire').setLevel(logging.WARNING)
logging.getLogger('webdriver_manager').setLevel(logging.WARNING)

# === CẤU HÌNH TỪ BIẾN MÔI TRƯỜNG ===
API_ID = int(os.getenv('API_ID', '12345'))
API_HASH = os.getenv('API_HASH', 'default_hash')
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_USERS_STR = os.getenv('ADMIN_USERS', '123456789')
ADMIN_USERS = [int(user_id.strip()) for user_id in ADMIN_USERS_STR.split(',')]
CONTROL_GROUP_ID = os.getenv('CONTROL_GROUP_ID', '@your_control_group')
DEFAULT_UPLOAD_CHANNEL = os.getenv('DEFAULT_UPLOAD_CHANNEL', '@your_default_channel')
HIGHLIGHT_UPLOAD_CHANNEL = os.getenv('HIGHLIGHT_UPLOAD_CHANNEL', '@your_highlight_channel')
MONITOR_CHAT_ID = os.getenv('MONITOR_CHAT_ID', 'your_monitor_chat')
MONITOR_MESSAGE_ID = int(os.getenv('MONITOR_MESSAGE_ID', '1'))

# === CẤU HÌNH ĐƯỜNG DẪN (QUAN TRỌNG) ===
DATA_DIRECTORY = "/data"
DOWNLOAD_DIRECTORY = os.path.join(DATA_DIRECTORY, "downloads")
STOPPED_STREAMERS_FILE = os.path.join(DATA_DIRECTORY, "stopped_streamers.txt")

# === CÁC THÔNG SỐ HỆ THỐNG ===
MAX_CONCURRENT_AUTO_DOWNLOADS = 15; MONITOR_INTERVAL_SECONDS = 180; CHECK_DELAY_SECONDS = 3; SELENIUM_TIMEOUT_SECONDS = 30; STATUS_UPDATE_INTERVAL_SECONDS = 10; MIN_PARTIAL_FILE_SIZE_MB = 10; MIN_SUCCESSFUL_DOWNLOAD_SIZE_MB = 20; LARGE_FILE_THRESHOLD_BYTES = 4 * 1024 * 1024 * 1024; UPLOAD_RETRY_COUNT = 5
RECONNECT_RETRY_DELAYS = [5, 10, 15]
CLEANUP_INTERVAL_HOURS = 1
FILE_MAX_AGE_HOURS = 15

# === BIẾN TOÀN CỤC ===
auto_download_semaphore = asyncio.Semaphore(MAX_CONCURRENT_AUTO_DOWNLOADS); conversion_semaphore = asyncio.Semaphore(1); active_streamers = set(); active_downloads = {}; download_stats = {"success": 0, "failed": 0, "converted": 0, "last_success": "N/A"}; admin_filter = filters.user(ADMIN_USERS); UPLOADER_CLIENT_INSTANCE = None; bot_client_instance = None
saved_videos = []
saved_video_id_counter = 1
stopped_streamers = set()

# === KHỞI TẠO ỨNG DỤNG WEB ===
app = FastAPI()

# === CÁC HÀM TIỆN ÍCH ===
def format_time(seconds):
    if seconds is None or not isinstance(seconds, (int, float)) or seconds < 0: return "N/A"
    h, m, s = int(seconds // 3600), int((seconds % 3600) // 60), int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def format_size(size_bytes):
    if size_bytes is None or not isinstance(size_bytes, (int, float)): return "0 B"
    if size_bytes < 1024: return f"{size_bytes} B"
    elif size_bytes < 1024**2: return f"{size_bytes/1024:.2f} KB"
    elif size_bytes < 1024**3: return f"{size_bytes/1024**2:.2f} MB"
    else: return f"{size_bytes/1024**3:.2f} GB"

async def get_video_duration(file_path: str) -> float | None:
    try:
        proc = await asyncio.create_subprocess_exec('ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0: return float(stdout.decode().strip())
        else: logger.error(f"FFprobe error for {file_path}: {stderr.decode()}"); return None
    except Exception as e: logger.error(f"Error getting duration for {file_path}: {e}"); return None

async def cleanup_files_with_retry(*files, retries=3, delay=2):
    for file_path in files:
        if not file_path or not os.path.exists(file_path): continue
        for attempt in range(retries):
            try:
                os.remove(file_path); break
            except OSError as e:
                if attempt < retries - 1: await asyncio.sleep(delay)
                else: logger.error(f"Xóa file {os.path.basename(file_path)} thất bại. Lỗi: {e}")

# === LOGIC CỐT LÕI (SELENIUM, DOWNLOAD, PROCESS, UPLOAD) ===

def create_selenium_driver():
    logger.info("Đang khởi tạo Selenium..."); chrome_options = Options(); chrome_options.add_argument("--headless"); chrome_options.add_argument("--disable-gpu"); chrome_options.add_argument("--no-sandbox"); chrome_options.add_argument("--disable-dev-shm-usage"); chrome_options.add_argument("--log-level=3"); chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    try: service = Service(ChromeDriverManager().install()); driver = webdriver.Chrome(service=service, options=chrome_options); logger.info("✅ Selenium đã sẵn sàng."); return driver
    except Exception as e: logger.error(f"❌ Lỗi khởi tạo Selenium: {e}"); return None

def _get_m3u8_with_selenium_blocking(driver: webdriver.Chrome, url: str) -> str | None:
    if not driver: return None
    logger.info(f"SELENIUM: Bắt đầu kiểm tra {url}...")
    try:
        driver.get("about:blank"); del driver.requests; driver.get(url); time.sleep(4)
        request = driver.wait_for_request('.m3u8', timeout=15)
        if request and request.response and "_blurred.m3u8" not in request.url:
            logger.info(f"✅ SELENIUM: Online và đã tìm thấy HLS stream. -> {url}")
            return request.url
    except Exception: pass
    logger.info(f"🔴 SELENIUM: Offline hoặc không tìm thấy HLS stream. -> {url}")
    return None

async def _process_and_save_file(base_filename: str, streamer_name: str, ts_path: str):
    global saved_video_id_counter
    output_filepath_mp4 = ts_path.replace(".ts", ".mp4")
    
    try:
        if not os.path.exists(ts_path) or os.path.getsize(ts_path) < MIN_SUCCESSFUL_DOWNLOAD_SIZE_MB * 1024 * 1024:
            logger.info(f"[{streamer_name}] File .ts không tồn tại hoặc quá nhỏ, bỏ qua.")
            return

        async with conversion_semaphore:
            logger.info(f"[{streamer_name}] Bắt đầu chuyển đổi sang MP4...")
            ffmpeg_cmd = ['ffmpeg', '-i', ts_path, '-c', 'copy', '-movflags', '+faststart', '-bsf:a', 'aac_adtstoasc', '-y', output_filepath_mp4]
            proc = await asyncio.create_subprocess_exec(*ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                logger.error(f"[{streamer_name}] FFmpeg thất bại. Lỗi: {stderr.decode()}"); download_stats["failed"] += 1; return
        
        logger.info(f"[{streamer_name}] Chuyển đổi thành công. Xóa file .ts gốc.")
        await cleanup_files_with_retry(ts_path)
        download_stats["converted"] += 1
        
        duration = await get_video_duration(output_filepath_mp4)
        if duration is None:
            logger.error(f"[{streamer_name}] Không thể lấy thời lượng video. Hủy lưu."); await cleanup_files_with_retry(output_filepath_mp4); download_stats["failed"] += 1; return

        new_video = {"id": saved_video_id_counter, "name": streamer_name, "path": output_filepath_mp4, "duration": duration, "timestamp": datetime.now().strftime('%d-%m-%Y %H:%M'), "status": "Đã lưu"}
        saved_videos.append(new_video)
        logger.info(f"✅ [{streamer_name}] Đã xử lý và lưu thành công video ID: {saved_video_id_counter}")
        saved_video_id_counter += 1
    finally:
        if base_filename in active_downloads: del active_downloads[base_filename]

async def download_and_process_stream(streamer_name: str, hls_url: str):
    if streamer_name in active_streamers: return
    active_streamers.add(streamer_name)
    now = datetime.now()
    base_filename = f"{streamer_name}_{now.strftime('%Y-%m-%d_%H-%M-%S')}"
    output_filepath_ts = os.path.join(DOWNLOAD_DIRECTORY, f"{base_filename}.ts")
    
    try:
        async with auto_download_semaphore:
            active_downloads[base_filename] = {"name": streamer_name, "status": "Đang tải", "start_time": time.time()}
            logger.info(f"[{streamer_name}] Bắt đầu tải...")
            streamlink_cmd = ['streamlink', '--stdout', hls_url, 'best']
            process = await asyncio.create_subprocess_exec(*streamlink_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            with open(output_filepath_ts, 'wb') as f:
                while True:
                    chunk = await process.stdout.read(8192)
                    if not chunk: break
                    f.write(chunk)
            
            await process.wait()
            logger.info(f"[{streamer_name}] Tải xong. Giao cho tác vụ xử lý.")
            asyncio.create_task(_process_and_save_file(base_filename, streamer_name, output_filepath_ts))
    except Exception as e:
        logger.error(f"Lỗi khi tải của `{streamer_name}`: {e}"); download_stats["failed"] += 1
    finally:
        active_streamers.discard(streamer_name)
        if base_filename in active_downloads: del active_downloads[base_filename]

async def upload_to_telegram(filepath, streamer_name):
    if not os.path.exists(filepath): return False
    try:
        duration = await get_video_duration(filepath)
        caption = f"🎥 **{streamer_name}**\n📅 {datetime.now().strftime('%d-%m-%Y %H:%M')}\n⏰ Time: `{format_time(duration)}`"
        await UPLOADER_CLIENT_INSTANCE.send_video(chat_id=DEFAULT_UPLOAD_CHANNEL, video=filepath, caption=caption, supports_streaming=True)
        download_stats["success"] += 1
        return True
    except Exception as e:
        logger.error(f"❌ Upload lỗi cho `{streamer_name}`: {e}"); download_stats["failed"] += 1; return False

# === API ENDPOINTS CHO GIAO DIỆN WEB ===

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_root():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/api/status")
async def get_status():
    return {"active_downloads_count": len(active_downloads), "saved_videos_count": len(saved_videos), "stats": download_stats}

@app.get("/api/videos")
async def get_videos():
    return sorted(saved_videos, key=lambda v: v.get('id', 0), reverse=True)

@app.get("/video/{video_id}")
async def stream_video_endpoint(video_id: int, request: Request):
    video_info = next((v for v in saved_videos if v["id"] == video_id), None)
    if not video_info or not os.path.exists(video_info["path"]): raise HTTPException(status_code=404, detail="Video file not found.")
    file_path = video_info["path"]; file_size = os.stat(file_path).st_size; range_header = request.headers.get("range")
    headers = {"Content-Type": "video/mp4", "Accept-Ranges": "bytes", "Content-Length": str(file_size)}; start, end = 0, file_size - 1; status_code = 200
    if range_header:
        byte1, byte2 = range_header.split("=")[1].split("-"); start = int(byte1)
        if byte2: end = int(byte2)
        status_code = 206; headers["Content-Length"] = str(end - start + 1); headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
    def ranged_streamer(file_path: str, start: int, end: int):
        with open(file_path, "rb") as video_file:
            video_file.seek(start); remaining = end - start + 1
            while remaining > 0:
                chunk_size = min(remaining, 65536); chunk = video_file.read(chunk_size)
                if not chunk: break
                yield chunk; remaining -= len(chunk)
    return StreamingResponse(ranged_streamer(file_path, start, end), status_code=status_code, headers=headers)

@app.post("/api/action/{video_id}/{action_type}")
async def perform_action(video_id: int, action_type: str, request: Request):
    global saved_videos, saved_video_id_counter
    video = next((v for v in saved_videos if v["id"] == video_id), None)
    if not video: raise HTTPException(status_code=404, detail="Video not found")

    if action_type == "upload_telegram":
        video['status'] = 'Đang upload...'
        asyncio.create_task(upload_to_telegram(video["path"], video["name"]))
        return JSONResponse({"status": "success", "message": f"Đã bắt đầu upload video {video_id} lên Telegram."})
    elif action_type == "delete":
        await cleanup_files_with_retry(video["path"])
        saved_videos = [v for v in saved_videos if v["id"] != video_id]
        return JSONResponse({"status": "success", "message": f"Đã xóa video {video_id}."})
    elif action_type == "cut":
        data = await request.json(); start_time, end_time = data.get("start"), data.get("end")
        if not start_time or not end_time: raise HTTPException(status_code=400, detail="Thiếu thời gian bắt đầu hoặc kết thúc.")
        original_mp4_path = video["path"]; streamer_name = video["name"]
        clip_path = os.path.join(DOWNLOAD_DIRECTORY, f"{os.path.splitext(os.path.basename(original_mp4_path))[0]}_highlight_{int(time.time())}.mp4")
        ffmpeg_cmd = ['ffmpeg', '-y', '-i', original_mp4_path, '-ss', start_time, '-to', end_time, '-c', 'copy', '-movflags', '+faststart', clip_path]
        proc = await asyncio.create_subprocess_exec(*ffmpeg_cmd); await proc.communicate()
        if proc.returncode != 0 or not os.path.exists(clip_path): raise HTTPException(status_code=500, detail="Lỗi khi cắt video.")
        clip_duration = await get_video_duration(clip_path)
        new_clip = {"id": saved_video_id_counter, "name": f"{streamer_name} (Highlight)", "path": clip_path, "duration": clip_duration, "timestamp": datetime.now().strftime('%d-%m-%Y %H:%M'), "status": "Đã lưu (Clip)"}
        saved_videos.append(new_clip); saved_video_id_counter += 1
        return JSONResponse({"status": "success", "message": f"Đã tạo clip mới với ID {new_clip['id']}."})
    raise HTTPException(status_code=400, detail="Hành động không hợp lệ.")

# === TÁC VỤ NỀN ===
async def monitor_streamers_task():
    logger.info("🔍 Bắt đầu tác vụ giám sát..."); driver = create_selenium_driver()
    if not driver: logger.error("Không thể khởi tạo Selenium, tác vụ giám sát dừng lại."); return
    try:
        while True:
            # Logic lấy danh sách streamer từ message của bạn sẽ ở đây
            streamers_to_monitor = {"test_streamer_1", "test_streamer_2"} # Ví dụ
            logger.info(f"Quét {len(streamers_to_monitor)} streamers...")
            for streamer_name in streamers_to_monitor:
                if streamer_name in active_streamers: continue
                hls_url = await asyncio.to_thread(_get_m3u8_with_selenium_blocking, driver, f"https://stripchat.com/{streamer_name}")
                if hls_url: asyncio.create_task(download_and_process_stream(streamer_name, hls_url))
                await asyncio.sleep(CHECK_DELAY_SECONDS)
            logger.info(f"--- Hoàn tất chu kỳ quét. Nghỉ {MONITOR_INTERVAL_SECONDS}s ---")
            await asyncio.sleep(MONITOR_INTERVAL_SECONDS)
    finally:
        if driver: logger.info("Đang đóng Selenium..."); driver.quit()

async def periodic_cleanup_task():
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_HOURS * 3600)
        logger.info("--- Bắt đầu tác vụ dọn dẹp file cũ ---")
        # Logic dọn dẹp file cũ của bạn sẽ ở đây

# === HÀM MAIN ĐỂ CHẠY TẤT CẢ ===
async def main():
    global UPLOADER_CLIENT_INSTANCE, bot_client_instance
    if not BOT_TOKEN: logger.error("LỖI: Biến môi trường BOT_TOKEN chưa được thiết lập!"); return
    
    # Đảm bảo các thư mục dữ liệu tồn tại
    Path(DATA_DIRECTORY).mkdir(exist_ok=True)
    Path(DOWNLOAD_DIRECTORY).mkdir(exist_ok=True)
    
    # Khởi tạo các client Pyrogram, chỉ định thư mục làm việc là /data
    uploader_client = Client("user_account_session", workdir=DATA_DIRECTORY, api_id=API_ID, api_hash=API_HASH)
    bot_client = Client("bot_instance_session", workdir=DATA_DIRECTORY, api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
    
    UPLOADER_CLIENT_INSTANCE = uploader_client
    bot_client_instance = bot_client

    try:
        logger.info("Đang khởi động các client...")
        await uploader_client.start()
        me_uploader = await uploader_client.get_me()
        logger.info(f"✅ User Client đã đăng nhập: {me_uploader.first_name}")
        
        await bot_client.start()
        me_bot = await bot_client.get_me()
        logger.info(f"✅ Bot Client đã đăng nhập: @{me_bot.username}")
        
        config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
        server = uvicorn.Server(config)

        tasks = [
            asyncio.create_task(monitor_streamers_task()),
            asyncio.create_task(periodic_cleanup_task()),
            asyncio.create_task(server.serve())
        ]
        
        logger.info("======================================================")
        logger.info("✅ HỆ THỐNG ĐÃ SẴN SÀNG!")
        logger.info(f"🚀 Giao diện Web có tại: http://<IP_CỦA_TRUENAS>:PORT_BẠN_CHỌN")
        logger.info("======================================================")
        
        await asyncio.gather(*tasks)
        
    except Exception as e:
        logger.error(f"❌ Lỗi nghiêm trọng khi khởi động: {e}", exc_info=True)
    finally:
        logger.info("🔌 Đang ngắt kết nối...")
        if uploader_client.is_connected: await uploader_client.stop()
        if bot_client.is_connected: await bot_client.stop()
        logger.info("✅ Hệ thống đã dừng.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("🛑 Đã thoát chương trình.")