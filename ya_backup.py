import os.path
import platform
import shutil
import yadisk
import telebot
import sys
import json
from datetime import datetime


class Settings:
    __slots__ = (
        "BotApiKey",
        "TelegramChat",
        "YaDiskToken",
        "YaDiskCatalog",
        "BackupCatalog",
    )

    @staticmethod
    def handle_error(exc):
        print(exc)
        exit(-1)

    def __init__(self):
        try:
            settings_file = sys.argv[1]
            user_settings = json.load(open(settings_file))

            for user_settings_key in user_settings:
                setattr(self, user_settings_key, user_settings[user_settings_key])

        except IndexError as exc:
            self.handle_error(f"Provide config name. Exception: {exc}")
        except FileNotFoundError as exc:
            self.handle_error(f"File not found. Exception: {exc}")
        except json.JSONDecodeError as exc:
            self.handle_error(f"Json error. Exception: {exc}")
        except AttributeError as exc:
            self.handle_error(f"No settings available. Exception: {exc}")


disk = yadisk.YaDisk(token=Settings().YaDiskToken)
bot = telebot.TeleBot(Settings().BotApiKey)
chatId = Settings().TelegramChat


def send_message(message):
    bot.send_message(chatId, message)


if not disk.check_token():
    send_message("Токен яндекс диска не валиден")
    exit(-1)


def create_archive(path):
    if os.path.exists(path):
        dt = datetime.now()
        archivename = (os.path.basename(path) + '_' + dt.strftime('%d_%m_%Y'))
        shutil.make_archive(archivename, 'zip', path)
        disk.upload(archivename + '.zip', Settings().YaDiskCatalog + archivename)
    else:
        send_message(f"Путь {path} не существует")


for BackupCatalog in Settings().BackupCatalog:
    create_archive(BackupCatalog)
