import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Any

import motor
import motor.motor_asyncio
from telethon.types import User

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
    tasks_done: int = 0
    referals: list[int] = field(default_factory=list) # list of referals IDs
    from_where: str = ''
    
    @classmethod
    async def fromID(cls, uid: int):
        data = await database.userlist.find_one({"id": uid})
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
            data.get('tasks_done'),
            data.get('referals')
        )

    def toJSON(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "language": self.language,
            "wallet": self.wallet,
            "tasks_balance": self.tasks_balance,
            "tasks_done": self.tasks_done,
            "referals": self.referals,
            "from_where": self.from_where
        }


class Database(motor.motor_asyncio.AsyncIOMotorClient):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        logger.info('Initialized MongoDB connection')

        self.userlist = self.users.list
        self.admins: dict[str, int] = {}
        self.tasks = self.users.tasks
        self.referals = self.users.referals
        self.metrics = self.users.metrics
        self.pending = self.users.pending

        logger.info('Admin IDs parsed, proceeding ...')

    async def parse_adm(self):
        self.admins = {i['username']:i['id'] async for i in self.users.admins.find({})}


database = Database(os.getenv('MONGO_URL'))
