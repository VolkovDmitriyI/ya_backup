from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
import shutil
from typing import Iterable

import telebot
import yadisk

ARCHIVE_FORMAT = "zip"
ARCHIVE_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"
MAX_BACKUPS_PER_SOURCE = 5


class BackupError(RuntimeError):
    """Domain error for backup operations."""


@dataclass(slots=True)
class Settings:
    bot_api_key: str
    telegram_chat: str
    yandex_disk_token: str
    yandex_disk_catalog: str
    backup_catalogs: list[Path]

    @classmethod
    def from_file(cls, config_path: Path) -> "Settings":
        with config_path.open("r", encoding="utf-8") as config_file:
            raw = json.load(config_file)

        required_keys = {
            "BotApiKey": "bot_api_key",
            "TelegramChat": "telegram_chat",
            "YaDiskToken": "yandex_disk_token",
            "YaDiskCatalog": "yandex_disk_catalog",
            "BackupCatalog": "backup_catalogs",
        }

        missing = [key for key in required_keys if key not in raw]
        if missing:
            missing_as_text = ", ".join(missing)
            raise BackupError(f"В конфигурации отсутствуют обязательные поля: {missing_as_text}")

        backup_catalogs_raw = raw["BackupCatalog"]
        if not isinstance(backup_catalogs_raw, list) or not backup_catalogs_raw:
            raise BackupError("Поле BackupCatalog должно быть непустым списком путей")

        return cls(
            bot_api_key=str(raw["BotApiKey"]),
            telegram_chat=str(raw["TelegramChat"]),
            yandex_disk_token=str(raw["YaDiskToken"]),
            yandex_disk_catalog=str(raw["YaDiskCatalog"]).strip("/"),
            backup_catalogs=[Path(item) for item in backup_catalogs_raw],
        )


class Notifier:
    def __init__(self, bot_api_key: str, chat_id: str) -> None:
        self._bot = telebot.TeleBot(bot_api_key)
        self._chat_id = chat_id

    def send(self, message: str) -> None:
        self._bot.send_message(self._chat_id, message)


class YandexBackupService:
    def __init__(self, settings: Settings, notifier: Notifier) -> None:
        self._settings = settings
        self._notifier = notifier
        self._disk = yadisk.YaDisk(token=settings.yandex_disk_token)

    def validate(self) -> None:
        if not self._disk.check_token():
            raise BackupError("Токен Яндекс Диска невалиден")

        if not self._disk.exists(self._remote_dir.as_posix()):
            self._disk.mkdir(self._remote_dir.as_posix())

    @property
    def _remote_dir(self) -> PurePosixPath:
        return PurePosixPath("/") / self._settings.yandex_disk_catalog

    def run(self) -> None:
        self.validate()
        self._notifier.send("Запуск резервного копирования")

        for source_dir in self._settings.backup_catalogs:
            self._backup_single_directory(source_dir)

        self._notifier.send("Резервное копирование успешно завершено")

    def _backup_single_directory(self, source_dir: Path) -> None:
        source_dir = source_dir.resolve()
        if not source_dir.exists() or not source_dir.is_dir():
            raise BackupError(f"Каталог '{source_dir}' не существует или не является директорией")

        archive_name = f"{source_dir.name}_{datetime.now().strftime(ARCHIVE_TIMESTAMP_FORMAT)}"

        with TemporaryDirectory(prefix="ya-backup-") as temp_dir:
            temp_root = Path(temp_dir)
            archive_base = temp_root / archive_name
            archive_path = Path(f"{archive_base}.{ARCHIVE_FORMAT}")

            created_archive = Path(
                shutil_make_archive(
                    archive_base=archive_base,
                    source_dir=source_dir,
                    archive_format=ARCHIVE_FORMAT,
                )
            )
            archive_size = created_archive.stat().st_size
            self._ensure_enough_disk_space(archive_size, source_dir.name)

            remote_path = (self._remote_dir / archive_path.name).as_posix()
            self._disk.upload(created_archive.as_posix(), remote_path, overwrite=False)
            logging.info("Uploaded %s to %s", created_archive, remote_path)

        self._rotate_backups(source_dir.name)

    def _ensure_enough_disk_space(self, archive_size: int, source_name: str) -> None:
        disk_info = self._disk.get_disk_info()
        free_space = int(getattr(disk_info, "free_space", 0))
        if archive_size > free_space:
            raise BackupError(
                f"Недостаточно места на Яндекс Диске для '{source_name}'. "
                f"Требуется: {archive_size} байт, доступно: {free_space} байт"
            )

    def _rotate_backups(self, source_name: str) -> None:
        matching_files = [
            item
            for item in self._list_remote_files()
            if item.type == "file" and item.name.startswith(f"{source_name}_") and item.name.endswith(f".{ARCHIVE_FORMAT}")
        ]

        ordered = sorted(matching_files, key=lambda item: str(getattr(item, "modified", item.name)), reverse=True)
        to_delete = ordered[MAX_BACKUPS_PER_SOURCE:]

        for item in to_delete:
            self._disk.remove(item.path, permanently=True)
            logging.info("Removed old backup: %s", item.path)

    def _list_remote_files(self) -> Iterable:
        return list(self._disk.listdir(self._remote_dir.as_posix()))


def shutil_make_archive(archive_base: Path, source_dir: Path, archive_format: str) -> str:
    return shutil.make_archive(
        base_name=archive_base.as_posix(),
        format=archive_format,
        root_dir=source_dir.as_posix(),
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backup local directories to Yandex Disk")
    parser.add_argument(
        "config",
        type=Path,
        help="Path to JSON config file",
    )
    return parser.parse_args(argv)


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = parse_args(argv or sys.argv[1:])

    try:
        settings = Settings.from_file(args.config)
        notifier = Notifier(settings.bot_api_key, settings.telegram_chat)
        service = YandexBackupService(settings, notifier)
        service.run()
        return 0
    except Exception as exc:  # noqa: BLE001
        logging.exception("Backup failed: %s", exc)
        try:
            if "notifier" in locals():
                notifier.send(f"Ошибка резервного копирования: {exc}")
        except Exception:
            logging.exception("Failed to send telegram notification")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())