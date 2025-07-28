# Dockerfile (Phiên bản 2.1 - Nền tảng mới)

# THAY ĐỔI QUAN TRỌNG: Sử dụng một base image Python ổn định hơn
FROM python:3.10-slim-bullseye

WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y \
    ffmpeg curl gnupg --no-install-recommends && \
    curl -sS -o - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - && \
    echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && apt-get install -y google-chrome-stable --no-install-recommends && \
    apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false && \
    rm -rf /var/lib/apt/lists/*

# Giữ nguyên danh sách cài đặt đầy đủ để đảm bảo
RUN pip install --no-cache-dir --upgrade \
    blinker \
    pyrogram \
    tgcrypto \
    selenium-wire \
    webdriver-manager \
    fastapi \
    "uvicorn[standard]" \
    streamlink

# Đổi tên file ứng dụng chính thành app.py bên trong container
COPY app_main.py /app/app.py
COPY ./static /app/static

ENV CHROME_BIN=/usr/bin/google-chrome
ENV CHROME_PATH=/usr/bin/google-chrome

# Sử dụng đường dẫn tuyệt đối để chắc chắn
CMD ["/usr/local/bin/python", "app.py"]