# YA Backup

Утилита для запуска резервного копирования каталогов Linux-машины в Яндекс Диск из Docker-контейнера.

## Что делает скрипт

- Читает настройки из JSON-конфига.
- Создаёт ZIP-архив для каждого каталога из `BackupCatalog`.
- Проверяет валидность токена Яндекс Диска.
- Проверяет, хватает ли свободного места на Яндекс Диске перед загрузкой архива.
- Загружает архив в целевой каталог Яндекс Диска.
- Выполняет ротацию: хранит только **5 последних архивов для каждого исходного каталога**.
- Отправляет уведомления в Telegram о старте, успешном завершении и ошибках.

## Требования

- Python 3.11+
- Зависимости из `requirements.txt`
- Токен Яндекс Диска
- Telegram bot token и chat id

## Установка

```bash
pip install -r requirements.txt
```

## Конфигурация

Пример: `appsettings.json`.

Поля:

- `BotApiKey` — токен Telegram бота.
- `TelegramChat` — ID чата/канала для уведомлений.
- `YaDiskToken` — OAuth токен Яндекс Диска.
- `YaDiskCatalog` — каталог на Яндекс Диске, куда загружать архивы.
- `BackupCatalog` — список локальных директорий для резервного копирования.

## Запуск

```bash
python ya_backup.py appsettings.json
```

## Docker (пример)

```bash
docker run --rm \
  -v /path/to/local/data:/data:ro \
  -v $(pwd)/appsettings.json:/app/appsettings.json:ro \
  -w /app \
  python:3.11-slim \
  bash -lc "pip install -r requirements.txt && python ya_backup.py appsettings.json"
```

В `BackupCatalog` используйте пути внутри контейнера, например `/data`.