import asyncio
import html
from io import BytesIO
import json
from pathlib import Path
from pprint import pprint
import nonebot
from nonebot import on, on_message, logger
from nonebot.adapters.red import Adapter, Message, MessageEvent, Bot, MessageSegment
from nonebot.adapters.red.api.model import ChatType
import telegram
from telegram import Update, InputMediaPhoto, InputMediaDocument, InputMediaAudio, InputMediaVideo
from telegram.ext import ContextTypes, filters
from telegram_app import TelegramApp
from database import DBForumTopic, DBMessage, Database

nonebot.init()
driver = nonebot.get_driver()
driver.register_adapter(Adapter)
nonebot.load_from_toml("pyproject.toml")

import nonebot_plugin_localstore as store

forum_topic_lock = asyncio.Lock()
db = Database(store.get_config_file("nb2tg", "nb2tg.db"))

async def get_forum_topic(unique_id: int, name: str):
    async with forum_topic_lock:
        unique_id = str(unique_id)
        forum_topic_id = db.select_tg_forum_topic_id(unique_id)
        if not forum_topic_id:
            logger.info(f"creating forum topic for {name}")
            forum_topic = await telegram_master().create_forum_topic(name)
            logger.info(f"forum topic {name} created")
            forum_topic_id = forum_topic.message_thread_id
            db.insert_forum_topic(DBForumTopic(forum_topic_id, unique_id))
        return forum_topic_id


async def convert_message(message: Message):
    text = ""
    media = []
    for seg in message:
        match seg.type:
            case "text":
                text += html.escape(seg.data['text'])
            case "at":
                text += f'<a href="tg://user?id={telegram_master().me.id}">@{html.escape(seg.data["user_name"])}</a>'
            case "face":
                text += f"[face:{seg.data['face_id']}]"
            case "market_face":
                text += f"[market_face:{seg.data['face_name']}]"
            case "image":
                text += f"[image]"
                media.append(InputMediaPhoto(await seg.download(nonebot.get_bot())))
            case "file":
                print(seg.data)
                text += f"[file]"
                media.append(InputMediaDocument(await seg.download(nonebot.get_bot())))
            case "voice":
                print(seg.data)
                text += f"[voice]"
                media.append(InputMediaAudio(await seg.download(nonebot.get_bot())))
            case "video":
                print(seg.data)
                text += f"[video]"
                media.append(InputMediaVideo(await seg.download(nonebot.get_bot())))
            # case "json":
            #     data = json.loads(seg.data['data'])
            #     match data['app']:
            #         case "com.tencent.miniapp_01":
            #             text += f"[{data['meta']['detail_1']['qqdocurl']}]"
            #         case "com.tencent.structmsg":
            #             """[CQ:json,data={"app":"com.tencent.structmsg"&#44;"config":{"ctime":1695301163&#44;"forward":true&#44;"token":"57a15aa133fa8ea922e5c21c0ae68c85"&#44;"type":"normal"}&#44;"desc":"音乐"&#44;"extra":{"app_type":1&#44;"appid":100495085&#44;"msg_seq":7281263043479285785&#44;"uin":627696862}&#44;"meta":{"music":{"action":""&#44;"android_pkg_name":""&#44;"app_type":1&#44;"appid":100495085&#44;"ctime":1695301163&#44;"desc":"ずっと真夜中でいいのに。"&#44;"jumpUrl":"https://y.music.163.com/m/song?id=1399788801&amp;uct2=eSp1d2IlPa4DIaUNQvk03w%3D%3D&amp;dlt=0846&amp;app_version=8.10.71"&#44;"musicUrl":"http://music.163.com/song/media/outer/url?id=1399788801&amp;userid=45803009&amp;sc=wm&amp;tn="&#44;"preview":"https://p1.music.126.net/jWFFWk-XoYFTVh09nWjBGg==/109951165005758203.jpg?imageView=1&amp;thumbnail=1440z3088&amp;type=webp&amp;quality=80"&#44;"sourceMsgId":"0"&#44;"source_icon":"https://i.gtimg.cn/open/app_icon/00/49/50/85/100495085_100_m.png"&#44;"source_url":""&#44;"tag":"网易云音乐"&#44;"title":"Dear Mr 「F」 (亲爱的F先生)"&#44;"uin":627696862}}&#44;"prompt":"&#91;分享&#93;Dear Mr 「F」 (亲爱的F先生)"&#44;"ver":"0.0.0.1"&#44;"view":"music"}]"""
            #             text += f"[{data['meta']['news']['jumpUrl']}]"
            #         case _:
            #             logger.warning(f"unsupported json app {repr(data)}")
            #             text += f"[json/{data['app']}]"
            case _:
                text += f"[{seg.type}]"
                logger.warning(f"unsupported message segment {repr(seg)}")
    return (text, media)


@on().handle()
async def handle_message(event: MessageEvent, bot: Bot):
    # pprint(event.dict())
    match event.get_event_name():
        case "message.group":
            message = event.get_message()
            unique_id = -int(event.peerUin)
            name = event.sendMemberName or event.sendNickName
            forum_topic_id = await get_forum_topic(unique_id, event.peerName)
            reply_to_message = db.select_message_where_qq(unique_id, int(event.reply.replayMsgSeq)) if event.reply else None

            text, media = await convert_message(message)
            text = f"<u><b>{name}</b>:</u>\n" + text
            tg_message = await tg_send_message(text, media, reply_to_message, forum_topic_id)
            db.insert_message(DBMessage(unique_id, int(event.msgSeq), tg_message.from_user.id, forum_topic_id, tg_message.message_id))
        case "message.private":
            message = event.get_message()
            unique_id = int(event.peerUin)
            name = event.sendNickName
            forum_topic_id = await get_forum_topic(event.peerUin, name)
            reply_to_message = db.select_message_where_qq(unique_id, int(event.reply.replayMsgSeq)) if event.reply else None

            text, media = await convert_message(message)
            tg_message = await tg_send_message(text, media, reply_to_message, forum_topic_id)
            db.insert_message(DBMessage(unique_id, int(event.msgSeq), tg_message.from_user.id, forum_topic_id, tg_message.message_id))
        case _:
            logger.warning(f"unsupported event {str(event)}")


telegrams = [TelegramApp(token, driver.config.chat_id)
             for token in driver.config.telegram_tokens]

def telegram_load_balance():
    return sorted(telegrams, key=lambda t: t.last_send_timestamp)[0]

def telegram_master():
    return telegrams[0]

def telegram_by_id(id: int):
    for tg in telegrams:
        if tg.me.id == id:
            return tg
    return None

async def tg_send_message(text, media, reply_to_message: DBMessage, message_thread_id, *args, **kwargs):
    if not text:
        text = "(empty)"
    reply_to_message_id = None
    if reply_to_message:
        tg = telegram_by_id(reply_to_message.tg_bot_id)
        reply_to_message_id = reply_to_message.tg_message_id
    else:
        tg = telegram_load_balance()
    if media:
        msgs = await tg.send_media_group(media,
                                    reply_to_message_id=reply_to_message_id,
                                    message_thread_id=message_thread_id,
                                    caption=text,
                                    parse_mode=telegram.constants.ParseMode.HTML, 
                                    *args, **kwargs)
        return msgs[0]
    else:
        return await tg.send_message(text, 
                                    parse_mode=telegram.constants.ParseMode.HTML, 
                                    reply_to_message_id=reply_to_message_id,
                                    message_thread_id=message_thread_id,
                                    *args, **kwargs)


@telegram_master().handle_command("chat_id")
async def _(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(update.effective_chat.id, 
                                   f"{update.effective_chat.id}", 
                                   reply_to_message_id=update.message.id, 
                                   message_thread_id=update.message.message_thread_id)

@telegram_master().handle_command("list_friend")
async def _(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot: Bot = nonebot.get_bot()
    friend_list = await bot.get_friends()
    print(friend_list)
    formatted = '\n'.join([f"{friend.uin} {friend.remark or friend.nick}" for friend in friend_list])
    await context.bot.send_message(update.effective_chat.id, 
                                   formatted, 
                                   reply_to_message_id=update.message.id, 
                                   message_thread_id=update.message.message_thread_id)

@telegram_master().handle_command("list_group")
async def _(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot: Bot = nonebot.get_bot()
    group_list = await bot.get_groups()
    formatted = '\n'.join([f"{group.groupCode} {group.groupName}" for group in group_list])
    await context.bot.send_message(update.effective_chat.id, 
                                   formatted, 
                                   reply_to_message_id=update.message.id, 
                                   message_thread_id=update.message.message_thread_id)

# @telegram_master().handle_command("init_friend")
async def _(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot = nonebot.get_bot()
    try:
        user_id = int(context.args[0])
        friend_list = await bot.call_api("get_friend_list")
        username = None
        for friend in friend_list:
            if friend['user_id'] == user_id:
                username = friend['remark'] or friend['nickname']
                break
        if not username:
            raise KeyError
    except (IndexError, ValueError, KeyError):
        await context.bot.send_message(update.effective_chat.id, 
                                       f"bad argument", 
                                       reply_to_message_id=update.message.id, 
                                       message_thread_id=update.message.message_thread_id)
        return
    
    forum_topic_id = await get_forum_topic(user_id, username)
    await context.bot.send_message(update.effective_chat.id, 
                                   f"successfully created topic {forum_topic_id}", 
                                   reply_to_message_id=update.message.id, 
                                   message_thread_id=update.message.message_thread_id)

# @telegram_master().handle_command("init_group")
async def _(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot = nonebot.get_bot()
    try:
        group_id = int(context.args[0])
        group_info = await get_group_info(bot, group_id)
    except (IndexError, ValueError, KeyError):
        await context.bot.send_message(update.effective_chat.id, 
                                       f"bad argument", 
                                       reply_to_message_id=update.message.id, 
                                       message_thread_id=update.message.message_thread_id)
        return
    
    forum_topic_id = await get_forum_topic(-group_id,  # negative id for groups
                                            group_info['group_name'])
    await context.bot.send_message(update.effective_chat.id, 
                                   f"successfully created topic {forum_topic_id}", 
                                   reply_to_message_id=update.message.id, 
                                   message_thread_id=update.message.message_thread_id)

@telegram_master().handle_message(filters.COMMAND)
async def _(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(update.effective_chat.id, 
                                   "unknown command!", 
                                   reply_to_message_id=update.message.id, 
                                   message_thread_id=update.message.message_thread_id)

@telegram_master().handle_message()
async def _(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot = nonebot.get_bot()
    forum_topic_id = update.message.message_thread_id
    qq_unique_id = db.select_qq_unique_id(forum_topic_id)
    message = []
    if update.message.photo:
        file = await update.message.photo[-1].get_file()
        data = BytesIO(await file.download_as_bytearray())
        message.append(MessageSegment.image(data))
    message.append(MessageSegment.text(update.message.text or update.message.caption))

    if qq_unique_id > 0:
        chatType = ChatType.FRIEND
        peerUin = str(qq_unique_id)
    else:
        chatType = ChatType.GROUP
        peerUin = str(-qq_unique_id)
    msg = await bot.send(None, message, chatType=chatType, peerUin=peerUin)
    db.insert_message(DBMessage(qq_unique_id, int(msg.msgSeq), telegram_master().me.id, forum_topic_id, update.message.id))
    logger.info(f"sent {message} to qq, qq message id")

if __name__ == "__main__":
    nonebot.run()
