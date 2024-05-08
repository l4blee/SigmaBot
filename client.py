from abc import abstractmethod

from types import SimpleNamespace
from telethon import TelegramClient
from telethon.types import Channel

from database import Database
from language import LanguageHandler


class ClientType(TelegramClient):
    lang: LanguageHandler
    db: Database
    assets: SimpleNamespace
    subscribe_channels: list[Channel]
