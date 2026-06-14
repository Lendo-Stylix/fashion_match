@echo off
setlocal enabledelayedexpansion

:: Di chuyển vào thư mục chứa file bat (thư mục gốc dự án)
cd /d "%~dp0"

:: Đường dẫn mặc định tới Chrome trên Windows
set CHROME_BIN="C:\Program Files\Google\Chrome\Application\chrome.exe"
set PORT=9222

:: Định nghĩa thư mục profile riêng biệt tại gốc dự án
set PROFILE_DIR="%~dp0chrome_profile"

echo =================================================
echo   KHOI CHAY CHROME CHO DU AN CRAWLER (PORT %PORT%)
echo   Profile: %PROFILE_DIR%
echo =================================================

:: Tạo thư mục profile nếu chưa tồn tại
if not exist %PROFILE_DIR% mkdir %PROFILE_DIR%

:: Flags khởi chạy tối ưu cho kết nối CDP và cào dữ liệu
set FLAGS=--remote-debugging-port=%PORT% --user-data-dir=%PROFILE_DIR% --force-renderer-accessibility --disable-background-timer-throttling --no-first-run --no-default-browser-check --win-http-proxy-resolver

:: Khởi chạy Chrome
start "" %CHROME_BIN% %FLAGS%

echo ✅ Trình duyệt Chrome đã sẵn sàng điều khiển!
echo 💡 Profile tách biệt hoàn toàn tại: %PROFILE_DIR%

timeout /t 3 >nul
exit
