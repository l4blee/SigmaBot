import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Sequence

import pymongo
from motor import motor_asyncio
from telethon.types import User
from bson.codec_options import TypeRegistry

logger = logging.getLogger('database')

# Database entries interfaces
@dataclass
class Admin:
    username: str
    id: int

@dataclass
class DBUser:
    id: int
    username: str
    language: str
    wallet: str = ''
    tasks_balance: int = 0
    referals: list[int] = field(default_factory=list) # list of referals IDs

    @classmethod
    def fromUserEntity(cls, user_entity: User):
        data = database.userlist.find_one({"id": user_entity.id})
        if data is None:
            return None
        return cls.fromJSON(data)

    @classmethod
    def fromJSON(cls, data: dict):
        return cls(
            data.get('id'), 
            data.get('username'),
            data.get('language'), 
            data.get('wallet'),
            data.get('tasks_balance'), 
            data.get('referals')
        )

    def toJSON(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "language": self.language,
            "wallet": self.wallet,
            "tasks_balance": self.tasks_balance,
            "referals": self.referals
        }

@dataclass
class DBUserShort:
    id: int
    username: str
    total: int
    language: str


class Database(motor_asyncio.AsyncIOMotorClient):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        logger.info('Initialized MongoDB connection')

        self.userlist = self.users.list
        self.admins: dict[str, int] = {}
        self.tasks = self.users.tasks
        self.referals = self.users.referals

        logger.info('Admin IDs parsed, proceeding ...')

    async def parse_adm(self):
        self.admins = {i['username']:i['id'] async for i in self.users.admins.find()}


database = Database(os.getenv('MONGO_URL'))
