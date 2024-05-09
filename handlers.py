import os
import asyncio
import logging
import traceback
import pymongo
from telethon import events, types, Button, errors

from client import ClientType
from database import DBUser, DBUserShort
from language import AVAILABLE_LANGUAGES
import views

REF_PAYMENT = int(os.getenv('REF_PAYMENT'))
FLAG_EMOJIS = {
    'ru': '🇷🇺',
    'en': '🇺🇸'
}
logger = logging.getLogger('handlers')

@events.register(events.CallbackQuery())
async def on_inline(event: events.CallbackQuery.Event):
    client: ClientType = event.client
    user_entity: types.User = await client.get_entity(event.original_update.user_id)
    query: str = event.data.decode('utf-8')

    try:
        match query.split('_'):
            case 'awards', *_:
                tasklist = (client.db.tasks.find_one({'id': user_entity.id}) or {}).get('pending', [])
                ignore = [i[0] for i in tasklist]
                await client.send_message(user_entity,
                                          client.lang.get_phrase_by_key(user_entity, 'awards_msg'),
                                          buttons=views.tasks(user_entity, 
                                                              ignore_adm=True, 
                                                              ignore=[f'sn_{sn}' for sn in ignore]
                                                              ) + views.settings(user_entity))
            case 'task', *_:
                tasklist = (client.db.tasks.find_one({'id': user_entity.id}) or {}).get('pending', [])
                ignore = [i[0] for i in tasklist]
                await client.send_message(user_entity,
                                          client.lang.get_phrase_by_key(user_entity, 'tasks_msg'),
                                          buttons=views.awards(user_entity))
                await client.send_message(user_entity,
                                          client.lang.get_phrase_by_key(user_entity, 'tasks_msg2'),
                                          buttons=views.tasks(user_entity, 
                                                              ignore_adm=True, 
                                                              ignore=[f'sn_{sn}' for sn in ignore]
                                                              ) + views.settings(user_entity))
            case 'lang', selected_lang:
                client.db.userlist.update_one({"id": user_entity.id}, {"$set": {"language": selected_lang}})
                await client.send_message(user_entity,
                                          client.lang.get_phrase_by_key(user_entity, 'lang_upd'))
                
                await event.delete()
                await _start(client, user_entity)
            case 'leaderboard', *_:
                await _leaderboard(client, user_entity)
            case 'tokenomics', *_:
                await client.send_message(user_entity,
                                          client.lang.get_phrase_by_key(user_entity, 'tokenomics_msg'),
                                          file=client.assets.tokenomics)
            case 'social', 'networks', *_:
                await client.send_message(user_entity,
                                          client.lang.get_phrase_by_key(user_entity, 'social_networks_msg'))
            case 'contacts', *_:
                await client.send_message(user_entity,
                                          client.lang.get_phrase_by_key(user_entity, 'contacts_msg'))
            case 'user', 'agreement', *_:
                await client.send_message(user_entity,
                                          client.lang.get_phrase_by_key(user_entity, 'user_agreement_msg'))
            case _:
                return
    except errors.FilePart0MissingError:
        # query is the cmd here, as language handling has no images
        # so these are: leaderboard and tokenomics
        client.assets.__setattr__(query, await client.upload_file(f"assets/{query}.jpg"))
        await on_inline(event)
    except Exception:
        traceback.print_exc()

@events.register(events.NewMessage())
async def on_msg(event: types.Message):
    client: ClientType = event.client
    user_entity = await client.get_entity(event.peer_id)
    try:
        await _handle_command(event)
    except errors.common.AlreadyInConversationError:
        convs = client._conversations.get(user_entity.id)
        if convs:
            for conv in convs:
                await conv.cancel_all()

        await _handle_command(event)
    except Exception:
        traceback.print_exc()

        await client.send_message(
            event.chat_id,
            client.lang.get_phrase_by_key(user_entity, 'error'),
            buttons=views.main(user_entity)
        )


async def _handle_command(event: events.NewMessage.Event):
    client: ClientType = event.client
    text: str = event.message.message
    user_entity = await client.get_entity(event.peer_id)

    # Check subsctiptions
    if not await _has_joined(client, user_entity):
        if text.startswith('/start'):
            _, *ref = text.split(' ')
            if ref != [] and\
                    int(ref[0][1:]) != user_entity.id and\
                    not client.db.userlist.find_one({'id': user_entity.id}): # IS a referal
                client.db.referals.insert_one({
                    'referal': user_entity.id,  # Who is a referal
                    'referrer': int(ref[0][1:])  # Whose link was used
                })

        await client.send_message(user_entity,
                                  client.lang.get_phrase_by_key(user_entity, 'check_channel'),
                                  buttons=views.channels(user_entity))
        return

    if text.startswith('/start'):
        await _append_ref(client, user_entity)
        
        await _start(client, user_entity)
        return
    
    # No images here
    if text == 'Админ панель' and user_entity.id in client.db.admins.values():
        await _admin_panel(client, user_entity)
        return
    
    if text == 'Массовая рассылка' and user_entity.id in client.db.admins.values():
        await _admin_spam(client, user_entity)
        return
    
    if text == 'Проверить задания' and user_entity.id in client.db.admins.values():
        await _check_tasks(client, user_entity)
        return
    
    cmd = client.lang.get_key_by_phrase(user_entity, text)
    if cmd is None:
        return
    
    # Have images here, need try/except
    try:
        match cmd.split('_'):
            case 'sn', social_network:
                await _handle_snetwork(client, user_entity, social_network)
            case _: # Otherwise
                await eval(f'_{cmd}')(client, user_entity)
    except errors.FilePart0MissingError:
        if cmd == 'back':
            cmd = 'start'
        client.assets.__setattr__(cmd, await client.upload_file(f"assets/{cmd}.jpg"))
        await _handle_command(event)


async def _has_joined(client: ClientType, user_entity: types.User) -> bool:
    try:
        coroutines = [client.get_permissions(i, user_entity) for i in client.subscribe_channels]
        await asyncio.gather(*coroutines)

        return True
    except errors.UserNotParticipantError:
        return False

async def _start(client: ClientType, user_entity: types.User):
    entry = client.db.userlist.find_one({"id": user_entity.id})
    if entry is None:
        uform = DBUser(user_entity.id, 
                       user_entity.username, 
                       user_entity.lang_code if user_entity.lang_code in AVAILABLE_LANGUAGES else 'ru')
        client.db.userlist.insert_one(uform.toJSON())
        logger.info(f"Created new user: {uform.toJSON()}")

    await client.send_message(user_entity, 
                              client.lang.get_phrase_by_key(user_entity, 'start'), 
                              file=client.assets.start,
                              buttons=views.main(user_entity))


async def _append_ref(client: ClientType, user_entity: types.User):
     # if this user already exists or is himself(they're on userlist then, anyways), then they're not referal
    db_entry = client.db.referals.find_one({'referal': user_entity.id})
    if not db_entry:
        return
    
    ref_id = db_entry.get('referrer')
    if ref_id == user_entity.id or client.db.userlist.find_one({'id': user_entity.id}):
        return
    
    client.db.userlist.update_one({'id': ref_id}, 
                                  {'$push': {'referals': user_entity.id}})
    client.db.referals.delete_one({'referal': user_entity.id})
    referral = await client.get_entity(ref_id)
    await client.send_message(
        referral,
        client.lang.get_phrase_by_key(referral, 'referral'),
        buttons=views.main(referral)
    )


async def _balance(client: ClientType, user_entity: types.User):
    uform = DBUser.fromUserEntity(user_entity)

    await client.send_message(
        user_entity,
        client.lang.get_phrase_by_key(user_entity, 'balance_msg') % {
            'total_balance': uform.tasks_balance + len(uform.referals) * REF_PAYMENT,
            'ref_balance': len(uform.referals) * REF_PAYMENT,
            'tasks_balance': uform.tasks_balance
        },
        buttons=[
            [
                Button.inline(client.lang.get_phrase_by_key(user_entity, 'leaderboard'), data='leaderboard')
            ],
            [
                Button.inline(client.lang.get_phrase_by_key(user_entity, 'tasks'), data='task'),
                Button.url(client.lang.get_phrase_by_key(user_entity, 'invite'),
                           url=f'https://t.me/share/url?url=https://t.me/SIGMADropbot?start=r{user_entity.id}')
            ]
        ],
        file=client.assets.balance
    )


async def _wallet(client: ClientType, user_entity: types.User):
    uform = DBUser.fromUserEntity(user_entity)
    
    try:
        async with client.conversation(user_entity) as conv:
            await conv.send_message(
                client.lang.get_phrase_by_key(user_entity, 'wallet_msg') % {
                    'wallet': uform.wallet or client.lang.get_phrase_by_key(user_entity, 'no_wallet')
                },
                file=client.assets.wallet
            )

            await conv.send_message(
                client.lang.get_phrase_by_key(user_entity, 'wallet_enter'),
                buttons=views.settings(user_entity)
            )

            addr = (await conv.get_response()).message
            if addr == client.lang.get_phrase_by_key(user_entity, 'back') or addr.startswith('/start'):
                return

            client.db.userlist.update_one({'id': user_entity.id}, {'$set': {'wallet': addr}})

            await conv.send_message(
                client.lang.get_phrase_by_key(user_entity, 'wallet_msg') % {
                    'wallet': addr
                },
                buttons=views.main(user_entity)
            )
    except asyncio.exceptions.TimeoutError:
        await client.send_message(user_entity,
                                  'Время вышло!',
                                  buttons=views.main(user_entity))
        await _start(client, user_entity)


async def _terms(client: ClientType, user_entity: types.User):
    await client.send_message(
        user_entity,
        client.lang.get_phrase_by_key(user_entity, 'terms_msg'),
        buttons=[Button.url(client.lang.get_phrase_by_key(user_entity, 'invite'),
                            url=f'https://t.me/share/url?url=https://t.me/SIGMADropbot?start=r{user_entity.id}')],
        file=client.assets.terms
    )


async def _settings(client: ClientType, user_entity: types.User):
    await client.send_message(user_entity, 
                              "Выберите язык | Choose language", 
                              buttons=views.settings(user_entity))
    await client.send_message(user_entity,
                              "Доступные языки | Available languages:", 
                              buttons=views.langs)


async def _back(client: ClientType, user_entity: types.User):
    convs = client._conversations.get(user_entity.id)
    if convs:
        coroutines = [conv.cancel_all() for conv in convs]
        await asyncio.gather(*coroutines)

    await _start(client, user_entity)


async def _admin_spam(client: ClientType, user_entity: types.User):
    try:
        async with client.conversation(user_entity) as conv:
            await conv.send_message("Введите сообщение для рассылки:", buttons=views.settings(user_entity))

            res = await conv.get_response()
            if res.message == '/start' or client.lang.get_key_by_phrase(user_entity, res.message) == 'back':
                return
            
            await conv.send_message('Подтвердите сообщение:')
            await conv.send_message(res.message, file=res.media, 
                                    buttons=[Button.inline('Да✔️'), Button.inline('Нет❌')])
            
            e = await conv.wait_event(events.CallbackQuery)
            d = e.data.decode('utf-8')
            if d == 'Да✔️':
                await client.send_message(user_entity, 'Сообщение отправлено!', buttons=views.main(user_entity))
                users = client.db.userlist.find()
                for u in users:
                    _id = u.get('id')
                    if _id != user_entity.id:
                        await client.send_message(await client.get_entity(_id), res.message, file=res.media)
            else:
                await conv.send_message(
                    'Отправка отменена',
                    buttons=views.main(user_entity)
                )

            await e.delete()
    except asyncio.exceptions.TimeoutError:
        await client.send_message(user_entity,
                                  'Время вышло!',
                                  buttons=views.main(user_entity))
    

async def _info(client: ClientType, user_entity: types.User):
    await client.send_message(user_entity,
                              client.lang.get_phrase_by_key(user_entity, 'info_msg'),
                              buttons=views.info(user_entity))


async def _handle_snetwork(client: ClientType, user_entity: types.User, social_network: str):
    try:
        async with client.conversation(user_entity) as conv:
            if social_network == 'other':
                await conv.send_message(client.lang.get_phrase_by_key(user_entity, 'sn_check'))

            await conv.send_message(client.lang.get_phrase_by_key(user_entity, 'sn_msg'), 
                                    buttons=views.clear(user_entity))

            link = (await conv.get_response()).message
            if link == '/start':
                return
            
            # logger.info(f'Received task link: "{link}", network: "{social_network}"')

            client.db.tasks.update_one({'id': user_entity.id},
                                       {'$push': {'pending': [social_network, link]}},
                                       upsert=True)

            await conv.send_message(client.lang.get_phrase_by_key(user_entity, 'sn_accepted'), buttons=views.main(user_entity))
    except asyncio.exceptions.TimeoutError:
        pass


async def _leaderboard(client: ClientType, user_entity: types.User):
    users = client.db.userlist.aggregate([
        {
            "$lookup": {
                'from': 'admins',
                'localField': 'id',
                'foreignField': 'id', 
                'as': 'result',
                'pipeline': [
                    {
                        '$project': {
                            'id': 1
                        }
                    }
                ]
            }
        },
        {
            '$match': {
                'result': {
                    '$size': 0
                }
            }
        },
        {
            '$project': {
                '_id': 0,
                'id': 1,
                'username': 1,
                'total': {
                    '$add': [ {'$multiply': [{'$size': '$referals'}, 10]}, '$tasks_balance']
                },
                'language': 1
        }   
        },
        {
            '$sort': {
                'total': pymongo.DESCENDING
            }
        },
        {
            '$limit': 10
        }
    ])

    res = []
    if user_entity.id in client.db.admins.values():
        stringify = lambda user: f'[{user.username or "Anonym"}](tg://user?id={user.id}) {FLAG_EMOJIS[user.language]} | {user.total} $RLSGM'
    else:
        stringify = lambda user: f'{user.username or "Anonym"} {FLAG_EMOJIS[user.language]} | {user.total} $RLSGM'
    
    for i, u in enumerate(users, 1):
        res.append(f'{i}. {stringify(DBUserShort(**u))}')
    
    await client.send_message(user_entity, 
                              client.lang.get_phrase_by_key(user_entity, 'leaderboard') + '\n\n' + '\n'.join(res),
                              file=client.assets.leaderboard)


async def _admin_panel(client: ClientType, user_entity: types.User):
    await client.send_message(user_entity, 'Выбери действие:', buttons=views.admin())


async def _check_tasks(client: ClientType, user_entity: types.User):
    try:
        async with client.conversation(user_entity) as conv:
            await conv.send_message('Задания на проверку:', buttons=views.settings(user_entity))
            tasks = client.db.tasks.aggregate([
                {
                    '$unwind': {
                        'path': '$pending',
                        'preserveNullAndEmptyArrays': False
                    }
                },
                {
                    '$project': {
                        "_id": 0,
                        'id': 1,
                        'task': '$pending'
                    }
                }
            ])
            while (task := tasks.next()):

                await conv.send_message(f"[{'Пользователь'}](tg://user?id={task.get('id')})\nСоц. сеть: {task.get('task')[0].capitalize()}\nURL: {task.get('task')[1]}",
                                        buttons=[Button.inline('Подтвердить', 'ok'),
                                                Button.inline('Отклонить', 'deny')])
                
                e = await conv.wait_event(events.CallbackQuery)
                res = e.data.decode('utf-8')
                if res == 'ok':
                    msg1 = await conv.send_message('Введите награду (в $RLSGM):')

                    msg2 = await conv.get_response()
                    ans = msg2.message
                    if ans == '/start' or client.lang.get_key_by_phrase(user_entity, ans) == 'back':
                        return

                    client.db.userlist.update_one({'id': task.get('id')},
                                                  {'$inc': {'tasks_balance': int(ans)}})
                    
                    rewarded = await client.get_entity(task.get('id'))
                    await client.send_message(rewarded, 
                                              client.lang.get_phrase_by_key(rewarded, 'awards_checked') % {'awarded': int(ans)})

                    await msg1.delete()
                    await msg2.delete()
                
                # Anyways, we remove the task
                client.db.tasks.aggregate([
                    {
                        '$match': {
                            'id': task.get('id')
                        }
                    },
                    {
                        '$set': {
                            'pending': {'$slice': ['$pending', 1, { '$size': '$pending' }]}
                        }
                    },
                    {
                        "$merge": {
                            'into': 'tasks'
                        }
                    }
                ])

                await e.delete()
    except asyncio.exceptions.TimeoutError:
        await client.send_message(user_entity,
                                  client.lang.get_phrase_by_key(user_entity, 'time_out'),
                                  buttons=views.main(user_entity))
    except StopIteration:
        await client.send_message(user_entity, 'Задания закончились!', buttons=views.main(user_entity))
    
    client.db.tasks.delete_many({'pending.0': {'$exists': False}})
