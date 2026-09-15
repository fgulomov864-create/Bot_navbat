FROM python:3.12-slim

# Loglar darhol ko'rinsin, .pyc fayllar yaratilmasin
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONIOENCODING=utf-8

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ma'lumotlar shu papkada saqlanadi. Railway'da shu yo'lga Volume ulanadi,
# shunda redeploy'dan keyin ham ma'lumot joyida qoladi.
RUN mkdir -p /data
ENV DATA_FILE=/data/data.json

# root bo'lmagan foydalanuvchi ostida ishlash xavfsizroq
RUN useradd --create-home --uid 1000 bot && chown -R bot:bot /app /data
USER bot

CMD ["python", "main.py"]
