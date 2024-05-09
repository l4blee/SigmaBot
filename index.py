import dotenv; dotenv.load_dotenv('.env')
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s - %(name)s - %(message)s', datefmt='%H:%M:%S')

import inspect
import os
from types import SimpleNamespace

from telethon import TelegramClient

import handlers
from client import ClientType
from language import lang_handler
from database import database


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s - %(name)s - %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger('index')


async def uploads(client: ClientType):
    client.assets.start = await client.upload_file('assets/start.jpg')
    client.assets.terms = await client.upload_file('assets/terms.jpg')
    client.assets.wallet = await client.upload_file('assets/wallet.jpg')
    client.assets.balance = await client.upload_file('assets/balance.jpg')
    client.assets.leaderboard = await client.upload_file('assets/leaderboard.jpg')
    client.assets.tokenomics = await client.upload_file('assets/tokenomics.jpg')

    client.subscribe_channels = [
        await client.get_entity(i)
        for i in os.getenv('SUB_CHANNELS').split(',')
    ]


def init() -> ClientType:
    client: ClientType = TelegramClient('main2', os.getenv('API_ID'), os.getenv('API_HASH'))

    client.assets = SimpleNamespace()
    client.db = database
    client.lang = lang_handler
    client.uploads = uploads

    logger.info('Telegram client initialized and database attached, starting...')
    client = client.start(bot_token=os.getenv('BOT_TOKEN'))

    return client


async def notify_admin(client: ClientType, message: str):
    for _id in client.db.admins.values():
        await client.send_message(await client.get_entity(_id), message)


if __name__ == '__main__':
    client = init()

    for name, val in handlers.__dict__.items():
        if callable(val) and not inspect.isclass(val) and name[0] != '_':
            logger.info(f'Registered callback: {name}')
            client.add_event_handler(val)

    with client:
        client.loop.run_until_complete(client.uploads(client))
        # client.loop.run_until_complete(notify_admin(client, 'The bot has started'))
        client.loop.run_until_complete(client.send_message('l4blee', 'bot started'))
        client.run_until_disconnected()

