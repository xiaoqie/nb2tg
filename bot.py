import asyncio
import json
import time
import urllib.request
import traceback
import imageio.v3 as iio
import nonebot
from nonebot import on, on_command, logger
from nonebot.rule import is_type
from nonebot.params import CommandArg
import nonebot.adapters.onebot.v11 as v11
import nonebot.adapters.telegram as tg
import database as DB
from utils import qq_emoji_text_list, download_file

nonebot.init()
driver = nonebot.get_driver()
driver.register_adapter(v11.Adapter)
driver.register_adapter(tg.Adapter)
nonebot.load_from_toml("pyproject.toml")

db = DB.Database("nb2tg.db")
forum_topic_lock = asyncio.Lock()
group_list_lock = asyncio.Lock()
_group_list = {}
tg_bots_last_message_timestamp = {}


def telegram_master():
    b: tg.Bot = next(bot for bot in nonebot.get_bots().values() if bot.type == "Telegram")
    return b


def is_telegram_master(bot: tg.Bot):
    return bot is telegram_master()


def v11_bot() -> v11.Bot:
    return next(bot for bot in nonebot.get_bots().values() if bot.type == "OneBot V11")


def telegram_load_balance(force_bot_id: int = None):
    if force_bot_id:
        return nonebot.get_bot(str(force_bot_id))

    b: tg.Bot = sorted(filter(lambda bot: bot.type == "Telegram", nonebot.get_bots().values()), 
                       key=lambda bot: tg_bots_last_message_timestamp.get(bot.self_id, 0))[0]
    tg_bots_last_message_timestamp[b.self_id] = time.time()
    return b


async def get_forum_topic(unique_id: int, name: str):
    async with forum_topic_lock:
        forum_topic_id = db.select_tg_forum_topic_id(qq_unique_id=unique_id)
        if not forum_topic_id:
            logger.info(f"creating forum topic for {unique_id} {name}")
            forum_topic = await telegram_master().create_forum_topic(driver.config.chat_id, name)
            forum_topic_id = forum_topic.message_thread_id
            logger.info(f"forum topic {forum_topic_id} created")
            db.insert_forum_topic(DB.ForumTopic(forum_topic_id, unique_id))
        return forum_topic_id


async def get_group_info(bot: v11.Bot, group_id: int):
    async with group_list_lock:
        if group_id not in _group_list:
            group_list = await bot.call_api("get_group_list")
            for group in group_list:
                _group_list[group['group_id']] = group
        return _group_list[group_id]


async def convert_message(message: v11.Message):
    entities = ""
    text = ""
    for seg in message:
        try:
            match seg.type:
                case "text":
                    text += seg.data['text']
                case "at":
                    text += f"@{seg.data['qq']} "
                case "face":
                    if int(seg.data['id']) in qq_emoji_text_list:
                        text += f"[{qq_emoji_text_list[int(seg.data['id'])]}]"
                    else:
                        text += f"[face:{seg.data['id']}]"
                case "mface":
                    text += f"[mface]"
                case "image":
                    text += "[image]"
                    data = await download_file(seg.data['url'])
                    if not data:
                        text += "[error: failed to download image]"
                        logger.error(f"failed to download image {seg.data['url']}")
                    else:
                        meta = iio.immeta(data, plugin="pyav")
                        if meta['codec'] == "gif":
                            entities += tg.message.File.animation(("image.gif", data))
                        else:
                            entities += tg.message.File.photo(data)
                case "record":
                    text += "[record]"
                    data = await download_file(seg.data['url'])
                    entities += tg.message.File.voice(data)
                case "video":
                    text += "[video]"
                    data = await download_file(seg.data['url'])
                    entities += tg.message.File.video(data)
                case "file":
                    text += "[file]"
                    data = await download_file(seg.data['url'])
                    entities += tg.message.File.document((seg.data['name'], data))
                case "json":
                    data = json.loads(seg.data['data'])
                    match data['app']:
                        case "com.tencent.miniapp_01":
                            text += f"[miniapp]{data['meta']['detail_1']['qqdocurl']}"
                        # case "com.tencent.structmsg":
                        #     text += f"[structmsg]{data['meta']['news']['jumpUrl']}"
                        case _:
                            logger.warning(f"unsupported json app {repr(data)}")
                            text += f"[json]\n{json.dumps(data, ensure_ascii=False, indent=2)}"
                case _:
                    text += f"[{seg.type}]"
                    logger.warning(f"unsupported message segment {repr(seg)}")
        except Exception as e:
            text += f"\n[ERROR]\n{repr(e)}\non {repr(seg)}\n[\ERROR]"
            traceback.print_exc()
    return text, entities


async def handle_message(event: v11.event.MessageEvent, qq_unique_id: int, forum_topic_id: int, name: str):
    message = event.get_message()
    print(repr(message))

    if event.reply:
        reply_to_message = db.select_message_where_qq(qq_unique_id, event.reply.message_id)
    elif reply_seg := [seg for seg in message if seg.type == "reply"]:
        reply_to_message = db.select_message_where_qq(qq_unique_id, reply_seg[0].data["id"])
    else:
        reply_to_message = None
        reply_tg_bot_id = None
        reply_tg_msg_id = None

    if reply_to_message:
        reply_tg_bot_id = reply_to_message.tg_bot_id
        reply_tg_msg_id = reply_to_message.tg_msg_id


    text, entities = await convert_message(message)
    if event.reply:
        text = "[reply]" + text
    converted_message = entities + tg.message.Entity.underline(name + ": ") + "\n" + text

    tg_bot = telegram_load_balance(reply_tg_bot_id)
    tg_messages = await tg_bot.send_to(driver.config.chat_id, converted_message, message_thread_id=forum_topic_id, reply_to_message_id=reply_tg_msg_id)
    if isinstance(tg_messages, list):
        for tg_message in tg_messages:
            db.insert_message(DB.Message(qq_unique_id, event.message_id, int(tg_bot.self_id), forum_topic_id, tg_message.message_id))
    else:
        tg_message = tg_messages
        db.insert_message(DB.Message(qq_unique_id, event.message_id, int(tg_bot.self_id), forum_topic_id, tg_message.message_id))


@on(rule=is_type(v11.event.GroupMessageEvent), block=True).handle()
async def handle_group_message(event: v11.event.GroupMessageEvent, bot: v11.Bot):
    try:
        qq_unique_id = -event.group_id  # negative id for groups
        name = event.sender.card or event.sender.nickname
        group_info = await get_group_info(bot, event.group_id)
        forum_topic_id = await get_forum_topic(qq_unique_id, group_info['group_name'])
        await handle_message(event, qq_unique_id, forum_topic_id, name)
    except Exception as e:
        error_msg = f"\n[ERROR]\n{repr(e)}\non {repr(event)}\n[\ERROR]"
        await telegram_master().send_to(driver.config.chat_id, error_msg)
        traceback.print_exc()


@on(rule=is_type(v11.event.PrivateMessageEvent), block=True).handle()
async def handle_private_message(event: v11.event.PrivateMessageEvent, bot: v11.Bot):
    try:
        qq_unique_id = event.sender.user_id
        name = event.sender.card or event.sender.nickname
        forum_topic_id = await get_forum_topic(qq_unique_id, name)
        await handle_message(event, qq_unique_id, forum_topic_id, name)
    except Exception as e:
        error_msg = f"\n[ERROR]\n{repr(e)}\non {repr(event)}\n[\ERROR]"
        await telegram_master().send_to(driver.config.chat_id, error_msg)
        traceback.print_exc()


@on(rule=is_type(v11.event.HeartbeatMetaEvent), block=True).handle()
async def handle_heartbeat_message(event: v11.Event, bot: v11.Bot):
    logger.info(f"received heartbeat {repr(event)}")


@on(rule=is_type(v11.Event), priority=10).handle()
async def handle_v11_message(event: v11.Event, bot: v11.Bot):
    logger.warning(f"unsupported event {repr(event)}")


@on_command("id", rule=is_type(tg.event.GroupMessageEvent) & is_telegram_master, block=True).handle()
async def handle_ls(event: tg.event.GroupMessageEvent, bot: tg.Bot):
    await bot.send(event, f"{event.chat.id}")


@on_command("ls", rule=is_type(tg.event.GroupMessageEvent) & is_telegram_master, block=True).handle()
async def handle_ls(event: tg.event.GroupMessageEvent, bot: tg.Bot):
    friend_list = await v11_bot().call_api("get_friend_list")
    formatted = "FRIENDS:\n"
    for friend in friend_list:
        formatted += f"{friend['user_remark'] or friend['user_name']}({friend['user_id']})"
        formatted += "\n"
    group_list = await v11_bot().call_api("get_group_list")
    formatted += "\n\nGROUPS:\n"
    for group in group_list:
        formatted += f"{group['group_name']}({-group['group_id']})"
        formatted += "\n"
    await bot.send(event, formatted)


@on_command("touch", rule=is_type(tg.event.GroupMessageEvent) & is_telegram_master, block=True).handle()
async def handle_touch(event: tg.event.GroupMessageEvent, bot: tg.Bot, message: tg.Message = CommandArg()):
    if user_id := message.extract_plain_text():
        if user_id.startswith("-"):
            group_list = await v11_bot().call_api("get_group_list")
            for group in group_list:
                if str(-group['group_id']) == user_id:
                    forum_topic_id = await get_forum_topic(-group['group_id'], group['group_name'])
                    await bot.send(event, f"successfully created topic {forum_topic_id}")
                    break
            else:
                await bot.send(event, f"failed to create forum topic for {user_id}")
        else:
            friend_list = await v11_bot().call_api("get_friend_list")
            for friend in friend_list:
                if str(friend['user_id']) == user_id:
                    forum_topic_id = await get_forum_topic(friend['user_id'], friend['user_remark'] or friend['user_name'])
                    await bot.send(event, f"successfully created topic {forum_topic_id}")
                    break
            else:
                await bot.send(event, f"failed to create forum topic for {user_id}")
    else:
        await bot.send(event, "Usage: /touch USER_ID or /touch -GROUP_ID")


@on(rule=is_type(tg.event.ForumTopicMessageEvent) & is_telegram_master, block=True).handle()
async def handle_topic_message(event: tg.event.ForumTopicMessageEvent, bot: tg.Bot):
    forum_topic_id = event.message_thread_id
    qq_unique_id = db.select_qq_unique_id(tg_forum_topic_id=forum_topic_id)

    converted_message = ""
    for seg in event.get_message():
        match seg.type:
            case _ if seg.is_text():
                converted_message += seg.data.get("text", "")
            case "photo":
                file = await bot.get_file(file_id=seg.data["file"])
                url = f"https://api.telegram.org/file/bot{bot.bot_config.token}/{file.file_path}"
                data = await download_file(url)
                converted_message += v11.message.MessageSegment.image(data)
            case "video":
                file = await bot.get_file(file_id=seg.data["file"])
                url = f"https://api.telegram.org/file/bot{bot.bot_config.token}/{file.file_path}"
                data = await download_file(url)
                # converted_message += v11.message.MessageSegment.video(data)
            case "document":
                file = await bot.get_file(file_id=seg.data["file"])
                url = f"https://api.telegram.org/file/bot{bot.bot_config.token}/{file.file_path}"
                # print(url)
                # data = await download_file(url)
                await v11_bot().call_api("upload_private_file", user_id=qq_unique_id, file=url, name=file.file_path)
            case "sticker" | "animation":
                file = await bot.get_file(file_id=seg.data["file"])
                url = f"https://api.telegram.org/file/bot{bot.bot_config.token}/{file.file_path}"
                frames = iio.imread(await download_file(url), index=None, plugin="pyav", format="rgba")
                data = iio.imwrite("<bytes>", frames, extension=".gif", duration=50, loop=0)
                converted_message += v11.message.MessageSegment.image(data)
            case _:
                converted_message += seg.type

    if not converted_message:
        return

    event_dict = {}
    if qq_unique_id > 0:
        event_dict['user_id'] = qq_unique_id
    else:
        event_dict['group_id'] = -qq_unique_id
    if event.reply_to_message:
        reply_to_db_message = db.select_message_where_tg(tg_forum_topic_id=forum_topic_id, 
                                                         tg_msg_id=event.reply_to_message.message_id)
        if reply_to_db_message:
            event_dict['message_id'] = reply_to_db_message.qq_msg_id
    pseudo_event = lambda: None
    pseudo_event.dict = lambda: event_dict

    res = await v11_bot().send(pseudo_event, converted_message, reply_message='message_id' in event_dict)
    qq_msg_id = res['message_id']
    db.insert_message(DB.Message(qq_unique_id, qq_msg_id, int(telegram_master().self_id), forum_topic_id, event.message_id))


@on(rule=is_type(tg.Event) & is_telegram_master, priority=10).handle()
async def handle_tg_message(event: tg.Event, bot: tg.Bot):
    logger.warning(f"unsupported event {repr(event)}")


if __name__ == "__main__":
    nonebot.run()
