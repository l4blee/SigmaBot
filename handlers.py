import os
import datetime
import asyncio
import logging
import traceback
import pymongo
from telethon import events, types, Button, errors

from client import ClientType
from database import DBUser
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
    db_user = await DBUser.fromID(event.original_update.user_id)
    query: str = event.data.decode('utf-8')

    try:
        match query.split('_'):
            case 'awards', *_:
                tasklist = ((await client.db.tasks.find_one({'id': db_user.id})) or {}).get('pending', [])
                ignore = [i[0] for i in tasklist]
                await client.send_message(db_user.id,
                                          client.lang.get_phrase_by_key(db_user, 'awards_msg'),
                                          buttons=views.tasks(db_user, 
                                                              ignore_adm=True, 
                                                              ignore=[f'sn_{sn}' for sn in ignore]
                                                              ) + views.settings(db_user))
            case 'task', *_:
                tasklist = ((await client.db.tasks.find_one({'id': db_user.id})) or {}).get('pending', [])
                ignore = [i[0] for i in tasklist]
                await client.send_message(db_user.id,
                                          client.lang.get_phrase_by_key(db_user, 'tasks_msg'),
                                          buttons=views.awards(db_user))
                await client.send_message(db_user.id,
                                          client.lang.get_phrase_by_key(db_user, 'tasks_msg2'),
                                          buttons=views.tasks(db_user, 
                                                              ignore_adm=True, 
                                                              ignore=[f'sn_{sn}' for sn in ignore]
                                                              ) + views.settings(db_user))
            case 'lang', selected_lang:
                db_user.language = selected_lang
                await asyncio.gather(
                    client.db.userlist.update_one({"id": db_user.id}, {"$set": {"language": selected_lang}}),
                    client.send_message(db_user.id,
                                        client.lang.get_phrase_by_key(db_user, 'lang_upd'))
                )
                
                await event.delete()
                await _start(client, db_user)
            case 'leaderboard', *_:
                await _leaderboard(client, db_user)
            case 'tokenomics', *_:
                await client.send_message(db_user.id,
                                          client.lang.get_phrase_by_key(db_user, 'tokenomics_msg'),
                                          file=client.assets.tokenomics)
            case 'social', 'networks', *_:
                await client.send_message(db_user.id,
                                          client.lang.get_phrase_by_key(db_user, 'social_networks_msg'))
            case 'contacts', *_:
                await client.send_message(db_user.id,
                                          client.lang.get_phrase_by_key(db_user, 'contacts_msg'))
            case 'user', 'agreement', *_:
                await client.send_message(db_user.id,
                                          client.lang.get_phrase_by_key(db_user, 'user_agreement_msg'))
            case _:
                return
    except (errors.FilePart0MissingError, errors.FilePartMissingError):
        # query is the cmd here, and an image name as well, if required
        client.assets.__setattr__(query, await client.upload_file(f"assets/{query}.jpg"))
        await on_inline(event)
    except Exception:
        traceback.print_exc()

@events.register(events.NewMessage())
async def on_msg(event: types.Message):
    client: ClientType = event.client
    db_user = await DBUser.fromID(event.peer_id.user_id)

    # Check if is referal
    if event.message.message.startswith('/start'):
        _, *ref = event.message.message.split(' ')
        if ref != [] and\
                int(ref[0][1:]) != event.peer_id.user_id and\
                not await client.db.userlist.find_one({'id': event.peer_id.user_id}): 
            # has ref_id in /start, not self and not registered yet, so IS a ref
            await client.db.referals.insert_one({
                'referal': event.peer_id.user_id,  # Who is a referal
                'referrer': int(ref[0][1:])  # Whose link was used
            })

    # Check subscriptions
    if not await _has_joined(client, event.peer_id.user_id):
        await client.send_message(event.peer_id.user_id,
                                  client.lang.get_phrase_by_key(db_user, 'check_channel'),
                                  buttons=views.channels(db_user))
        return
    
    # If subscribed and not registered, then do it and proceed
    if db_user is None:
        db_user = await _register_user(client, 
                                       await client.get_entity(event.peer_id.user_id))

    try:
        await _handle_command(client, event.message.message, db_user)
    except errors.common.AlreadyInConversationError:
        convs = client._conversations.get(db_user.id)
        if convs:
            for conv in convs:
                await conv.cancel_all()

        await _handle_command(client, event.message.message, db_user)
    except Exception:
        traceback.print_exc()

        await client.send_message(
            event.chat_id,
            client.lang.get_phrase_by_key(db_user, 'error'),
            buttons=views.main(db_user)
        )


async def _handle_command(client: ClientType, text: str, db_user: DBUser):
    # No images in admin commands
    ADMIN_CMDS = {
        'Админ панель': _admin_panel,
        'Массовая рассылка': _admin_spam,
        'Проверить задания': _check_tasks,
        'Метрики': _metrics
    }
    if text in ADMIN_CMDS.keys() and db_user.id in client.db.admins.values():
        await ADMIN_CMDS[text](client, db_user)
        return
    
    if text.startswith('/start'):
        cmd = 'start'
    else:
        cmd = client.lang.get_key_by_phrase(db_user, text)

    if cmd is None:
        return
    
    # Have images here, need try/except
    try:
        match cmd.split('_'):
            case 'sn', social_network:
                await _handle_snetwork(client, social_network, db_user)
            case _: # Otherwise
                await eval(f'_{cmd}')(client, db_user)
    except errors.FilePart0MissingError:
        if cmd == 'back':
            cmd = 'start'
        client.assets.__setattr__(cmd, await client.upload_file(f"assets/{cmd}.jpg"))
        await _handle_command(client, text, db_user)


async def _has_joined(client: ClientType, uid: int) -> bool:
    try:
        coroutines = [client.get_permissions(i, uid) for i in client.subscribe_channels]
        await asyncio.gather(*coroutines)

        return True
    except errors.UserNotParticipantError:
        return False
    

async def _register_user(client: ClientType, user_entity: types.User):
    # User is on pending referals list
    if (db_entry := await client.db.referals.find_one({'referal': user_entity.id})):
        asyncio.gather(
            client.db.userlist.update_one({'id': db_entry.get('referrer')}, 
                                        {'$push': {'referals': user_entity.id}}),
            client.db.referals.delete_one({'referal': user_entity.id}),
            client.db.metrics.update_one({'date': datetime.date.today().strftime('%d-%m-%Y')}, 
                                        {'$inc': {'referals': 1}}, 
                                        upsert=True)
        )
        ref_db_user = await DBUser.fromID(db_entry.get('referrer'))

        await client.send_message(
            ref_db_user.id,
            client.lang.get_phrase_by_key(ref_db_user, 'referral'),
            buttons=views.main(ref_db_user)
        )

    db_user = DBUser(user_entity.id, 
                     user_entity.username, 
                     user_entity.lang_code if user_entity.lang_code in AVAILABLE_LANGUAGES else 'ru')
        
    await asyncio.gather(
        client.db.userlist.insert_one(db_user.toJSON()),
        client.db.metrics.update_one({'date': datetime.date.today().strftime('%d-%m-%Y')}, 
                                    {'$inc': {'new_users': 1}}, 
                                    upsert=True)
    )
    logger.info(f"Created new user: {db_user.toJSON()}")
    
    return db_user


async def _start(client: ClientType, db_user: DBUser):
    await client.send_message(db_user.id, 
                              client.lang.get_phrase_by_key(db_user, 'start'), 
                              file=client.assets.start,
                              buttons=views.main(db_user))


async def _balance(client: ClientType, db_user: DBUser):
    await client.send_message(
        db_user.id,
        client.lang.get_phrase_by_key(db_user, 'balance_msg') % {
            'total_balance': db_user.tasks_balance + len(db_user.referals) * REF_PAYMENT,
            'ref_balance': len(db_user.referals) * REF_PAYMENT,
            'tasks_balance': db_user.tasks_balance
        },
        buttons=[
            [
                Button.inline(client.lang.get_phrase_by_key(db_user, 'leaderboard'), data='leaderboard')
            ],
            [
                Button.inline(client.lang.get_phrase_by_key(db_user, 'tasks'), data='task'),
                Button.url(client.lang.get_phrase_by_key(db_user, 'invite'),
                           url=f'https://t.me/share/url?url=https://t.me/SIGMADropbot?start=r{db_user.id}')
            ]
        ],
        file=client.assets.balance
    )


async def _wallet(client: ClientType, db_user: DBUser):
    try:
        async with client.conversation(db_user.id) as conv:
            await conv.send_message(
                client.lang.get_phrase_by_key(db_user, 'wallet_msg') % {
                    'wallet': db_user.wallet or client.lang.get_phrase_by_key(db_user, 'no_wallet')
                },
                file=client.assets.wallet
            )

            await conv.send_message(
                client.lang.get_phrase_by_key(db_user, 'wallet_enter'),
                buttons=views.settings(db_user)
            )

            addr = (await conv.get_response()).message
            if addr == client.lang.get_phrase_by_key(db_user, 'back') or addr.startswith('/start'):
                return

            await client.db.userlist.update_one({'id': db_user.id}, {'$set': {'wallet': addr}})

            await conv.send_message(
                client.lang.get_phrase_by_key(db_user, 'wallet_msg') % {
                    'wallet': addr
                },
                buttons=views.main(db_user)
            )
    except asyncio.exceptions.TimeoutError:
        await client.send_message(db_user.id,
                                  'Время вышло!',
                                  buttons=views.main(db_user))
        await _start(client, db_user)


async def _terms(client: ClientType, db_user: DBUser):
    await client.send_message(
        db_user.id,
        client.lang.get_phrase_by_key(db_user, 'terms_msg'),
        buttons=[Button.url(client.lang.get_phrase_by_key(db_user, 'invite'),
                            url=f'https://t.me/share/url?url=https://t.me/SIGMADropbot?start=r{db_user.id}')],
        file=client.assets.terms
    )


async def _settings(client: ClientType, db_user: DBUser):
    await client.send_message(db_user.id, 
                              "Выберите язык | Choose language", 
                              buttons=views.settings(db_user))
    await client.send_message(db_user.id,
                              "Доступные языки | Available languages:", 
                              buttons=views.langs)


async def _back(client: ClientType, db_user: DBUser):
    convs = client._conversations.get(db_user.id)
    if convs:
        coroutines = [conv.cancel_all() for conv in convs]
        await asyncio.gather(*coroutines)

    await _start(client, db_user)


async def _admin_spam(client: ClientType, db_user: DBUser):
    try:
        async with client.conversation(db_user.id) as conv:
            await conv.send_message("Введите сообщение для рассылки:", buttons=views.settings(db_user))

            res = await conv.get_response()
            if res.message == '/start' or client.lang.get_key_by_phrase(db_user, res.message) == 'back':
                return
            
            await conv.send_message('Подтвердите сообщение:')
            await conv.send_message(res.message, file=res.media, 
                                    buttons=[Button.inline('Да✔️'), Button.inline('Нет❌')])
            
            e = await conv.wait_event(events.CallbackQuery)
            d = e.data.decode('utf-8')
            if d == 'Да✔️':
                await client.send_message(db_user.id, 'Сообщение отправлено!', buttons=views.main(db_user))
                users = client.db.userlist.find({'id': {'$ne': db_user.id}})
                coroutines = [
                    client.send_message(u.get('id'), res.message, file=res.media)
                    async for u in users
                ]
                asyncio.gather(*coroutines)
            else:
                await conv.send_message(
                    'Отправка отменена',
                    buttons=views.main(db_user)
                )

            await e.delete()
    except asyncio.exceptions.TimeoutError:
        await client.send_message(db_user.id,
                                  'Время вышло!',
                                  buttons=views.main(db_user))
    

async def _info(client: ClientType, db_user: DBUser):
    await client.send_message(db_user.id,
                              client.lang.get_phrase_by_key(db_user, 'info_msg'),
                              buttons=views.info(db_user))


async def _handle_snetwork(client: ClientType, social_network: str, db_user: DBUser):
    try:
        async with client.conversation(db_user.id) as conv:
            if social_network == 'other':
                await conv.send_message(client.lang.get_phrase_by_key(db_user, 'sn_check'))

            await conv.send_message(client.lang.get_phrase_by_key(db_user, 'sn_msg'), 
                                    buttons=views.clear(db_user))

            link = (await conv.get_response()).message
            if link == '/start':
                return

            asyncio.gather(
                client.db.tasks.update_one({'id': db_user.id},
                                          {'$push': {'pending': [social_network, link]}},
                                          upsert=True),
                client.db.metrics.update_one({'date': datetime.date.today().strftime('%d-%m-%Y')}, 
                                            {'$inc': {'tasks_done': 1}}, 
                                            upsert=True)
            )

            await conv.send_message(client.lang.get_phrase_by_key(db_user, 'sn_accepted'), buttons=views.main(db_user))
    except asyncio.exceptions.TimeoutError:
        pass


async def _leaderboard(client: ClientType, db_user: DBUser):
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

    if db_user.id in client.db.admins.values():
        stringify = lambda user: f'[{user.get("username") or "Anonym"}](tg://user?id={user.get("id")}) {FLAG_EMOJIS[user.get("language")]} | {user.get("total")} $RLSGM'
    else:
        stringify = lambda user: f'{user.get("username") or "Anonym"} {FLAG_EMOJIS[user.get("language")]} | {user.get("total")} $RLSGM'
    
    res = []
    index = 1
    async for u in users:
        res.append(f'{index}. {stringify(u)}')
        index = index + 1
    
    await client.send_message(db_user.id, 
                              client.lang.get_phrase_by_key(db_user, 'leaderboard') + '\n\n' + '\n'.join(res),
                              file=client.assets.leaderboard)


async def _admin_panel(client: ClientType, db_user: DBUser):
    await client.send_message(db_user.id, 'Выбери действие:', buttons=views.admin())


async def _check_tasks(client: ClientType, db_user: DBUser):
    try:
        async with client.conversation(db_user.id) as conv:
            await conv.send_message('Задания на проверку:', buttons=views.settings(db_user))
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
            while (task := await tasks.next()):
                await conv.send_message(f"[{'Пользователь'}](tg://user?id={task.get('id')})\nСоц. сеть: {task.get('task')[0].capitalize()}\nURL: {task.get('task')[1]}",
                                        buttons=[Button.inline('Подтвердить', 'ok'),
                                                 Button.inline('Отклонить', 'deny')])
                
                e = await conv.wait_event(events.CallbackQuery)
                res = e.data.decode('utf-8')
                if res == 'ok':
                    msg1 = await conv.send_message('Введите награду (в $RLSGM):')

                    msg2 = await conv.get_response()
                    ans = msg2.message
                    if ans == '/start' or client.lang.get_key_by_phrase(db_user, ans) == 'back':
                        return

                    await client.db.userlist.update_one({'id': task.get('id')},
                                                        {'$inc': {'tasks_balance': int(ans)}})
                    
                    db_rew = await DBUser.fromID(task.get('id'))
                    await client.send_message(db_rew.id, 
                                              client.lang.get_phrase_by_key(db_rew, 'awards_checked') % {'awarded': int(ans)})

                    await msg1.delete()
                    await msg2.delete()
                
                # Anyways, we remove the task
                cursor = client.db.tasks.aggregate([
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
                await cursor.to_list(None)

                await e.delete()
    except asyncio.exceptions.TimeoutError:
        await client.send_message(db_user.id,
                                  client.lang.get_phrase_by_key(db_user, 'time_out'),
                                  buttons=views.main(db_user))
    except StopAsyncIteration:
        await client.send_message(db_user.id, 'Задания закончились!', buttons=views.main(db_user))
    
    await client.db.tasks.delete_many({'pending.0': {'$exists': False}})


async def _metrics(client: ClientType, db_user: DBUser):
    data, users_total, tasks_pending = await asyncio.gather(
        client.db.metrics.find_one({'date': datetime.date.today().strftime('%d-%m-%Y')}),
        client.db.userlist.count_documents({}),
        client.db.tasks.count_documents({})
    )

    if not data:
        await client.send_message(db_user.id, 'Недостаточно данных за текущий день.', buttons=views.main(db_user))
        return
    
    response = [
        f'**Всего пользователей**: {users_total} 👥',
        f'**Новых пользователей сегодня**: {data.get("new_users")} 👤',
        f'**Из них рефералов**: {data.get("referals", 0)} 🫂',
        f'**Сегодня выполнено заданий**: {data.get("tasks_done", 0)} 📝',
        f'**Ждёт проверки**: {tasks_pending} ✍🏼'
    ]
    await client.send_message(db_user.id, '\n'.join(response), buttons=views.main(db_user))
