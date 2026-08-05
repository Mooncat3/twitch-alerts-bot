import socket
from dataclasses import dataclass
from typing import Any
from aiogram.client.session.aiohttp import AiohttpSession
from functions import *
from contextlib import suppress
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters.command import Command
from telegram_bot_pagination import InlineKeyboardPaginator
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter, \
    TelegramServerError, TelegramMigrateToChat
from aiohttp.client_exceptions import ClientConnectorError, ClientOSError, InvalidURL
import signal
from models import *
import asyncio

class IPv4OnlyAiohttpSession(AiohttpSession):
    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self._connector_init["family"] = socket.AF_INET

bot_session = IPv4OnlyAiohttpSession()

bot_props = DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True)
bot = Bot(token=config.bot_token, default=bot_props, session=bot_session)
dp = Dispatcher()

all_exceptions = (TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter,
                  TelegramServerError, ClientConnectorError, ClientOSError, asyncio.TimeoutError, InvalidURL,
                  TelegramMigrateToChat)


async def get_streams_data(loop):
    connector = aiohttp.TCPConnector(family=socket.AF_INET)
    async with aiohttp.ClientSession(connector=connector) as session:
        while True:
            config.update_config()
            session.headers.update(config.head)

            streams_past = streams.copy()
            streams.clear()
            channels_list = create_channels_list()
            got_error = False

            try:
                for chan_split_list in split_list(channels_list, 100):
                    if chan_split_list:
                        params = {"user_login": chan_split_list, "first": len(chan_split_list), "type": "live"}

                        async with session.get(config.url_stream, params=params) as response:
                            got_error = response.status != 200
                            if not got_error:
                                for channel_data in (await response.json(loads=deserialize_func))["data"]:
                                    add_stream_to_streams(channel_data)
                            else:
                                if response.status == 401 and not (await update_oauth_token(session)):
                                    send_message_to_admins("Bot didn't change OAuth. Shutdown", error=True)
                                    return
                                break
            except all_exceptions:
                got_error = True

            if got_error:
                streams.clear()
                streams.update(streams_past)
            else:
                for channel_name in channels_list:
                    if channel_name not in streams:
                        streams.update({channel_name: StreamObject()})

            delete_users_in_queue()
            await send_messages_in_queue()
            changes = check_changes(streams_past)
            loop.create_task(send_alerts(changes, loop))

            update_last_seen_nicknames(streams_past, channels_list)
            update_category_history(streams_past, changes)
            loop.create_task(updating_streamer_list(loop))

            await asyncio.sleep(config.update_time)


async def _send_message_to_admins(text):
    for admin_id in config.admins:
        await send(admin_id, text)


def send_message_to_admins(text, error=False):
    if error:
        logging.error(text)
    else:
        logging.info(text)
    loop = asyncio.get_running_loop()
    loop.create_task(_send_message_to_admins(text))


async def update_oauth_token(session):
    async with session.post(config.url_token, params=config.params_to_get_oauth) as response:
        if response.status == 200:
            logging.info("Changing OAuth...")
            access_token = await response.json(loads=deserialize_func)
            change_config("oauth", access_token["access_token"])
        return response.status == 200


async def streamers_page(user_id, page, message_id, update_event=True):
    user_lang = get_user_lang(user_id)
    max_pages = get_user_max_pages(user_id)
    page = limit_page(page, max_pages)
    if update_event:
        add_event_to_user(user_id, "in_streamer_list", page, message_id)

    paginator = InlineKeyboardPaginator(
        page_count=max_pages,
        current_page=page,
        data_pattern="streamers_page|{page}")

    b1 = InlineKeyboardButton(text=f"➕ {user_lang['add_streamers']}", callback_data="add_streamers")
    b2 = InlineKeyboardButton(text=f"❌ {user_lang['delete_streamers']}", callback_data="delete_streamers|1")
    b3 = InlineKeyboardButton(text=f"⚙️ {user_lang['settings']}", callback_data="settings")
    b4 = InlineKeyboardButton(text=f"🔄 {user_lang['refresh']}", callback_data=f"streamers_page|{page}")
    b5 = InlineKeyboardButton(text=f"📚 {user_lang['past_broadcasts_label']}", callback_data="choose_past_broadcast|1")

    paginator.add_after(b4)
    paginator.add_after(b5)
    paginator.add_after(b1, b2)
    paginator.add_after(b3)

    if get_number_of_user_streamers(user_id) == 0:
        text = f"{user_lang['empty_list']} {user_lang['please_add_streamers']}"
    else:
        len_list = f"{get_number_of_user_streamers(user_id)} / {config.streamers_limit_by_user}"
        result_list = create_user_list(user_id, page)
        result = f"{user_lang['show_list_of_streamers'].format(len_list)}\n{''.join(result_list)}"
        text = add_last_update(result, user_id, user_lang)
    return await edit(user_id, text, paginator, message_id=message_id)


async def delete_streamers(user_id, page, message_id):
    user_lang = get_user_lang(user_id)
    max_pages = get_user_max_pages(user_id)
    page = limit_page(page, max_pages)

    result_list = [InlineKeyboardButton(text=f"❌ {prettier_nicknames(elem)}", callback_data=f"delete|{elem}|{page}")
                   for elem in get_user_list(user_id, page)]

    paginator = InlineKeyboardPaginator(
        page_count=max_pages,
        current_page=page,
        data_pattern="delete_streamers|{page}")
    for element in result_list:
        paginator.add_before(element)
    paginator.add_after(create_back(user_lang))

    await edit(user_id, user_lang["delete_nicknames"], paginator, message_id=message_id)


async def edit_alerts(user_id, page, message_id):
    user_lang = get_user_lang(user_id)

    if get_number_of_user_streamers(user_id) == 0:
        await edit(user_id, f"{user_lang['empty_list']} {user_lang['please_add_streamers']}",
                   back_markup(user_lang), message_id=message_id)
    else:
        max_pages = get_user_max_pages(user_id)
        page = limit_page(page, max_pages)
        result_list = create_edit_buttons(user_id, page)

        paginator = InlineKeyboardPaginator(
            page_count=max_pages,
            current_page=page,
            data_pattern="edit_alerts|{page}")
        for element in result_list:
            paginator.add_before(*element)
        paginator.add_after(create_back(user_lang, settings=True))
        paginator.add_after(create_back(user_lang))

        await edit(user_id, user_lang["edit_alerts"], paginator, message_id=message_id)


async def users_info(user_id, page=1, message_id=None):
    if not is_admin(user_id) or not config.user_info:
        return

    session = db.get_session()
    try:
        total_users = session.query(User).count()
        page = limit_page(page, total_users)
        current_user = session.query(User).order_by(User.reg_date).offset(page - 1).limit(1).first()
        if not current_user:
            return
        user_info = create_user_info(current_user.id, admin_id=user_id)
        paginator = InlineKeyboardPaginator(
            page_count=total_users,
            current_page=page,
            data_pattern="users_info|{page}"
        )
        await edit(user_id, user_info, paginator, is_bold=False, message_id=message_id)
    finally:
        session.close()


async def open_settings(user_id, message_id):
    user_lang = get_user_lang(user_id)
    session = db.get_session()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            return

        time_range = change_timezone(user.time_range, user.timezone, back=True)
        if time_range == "00:00-23:59":
            time_range = user_lang["time_always"]
        is_turned_b3 = get_state(user.mute_alerts)
        is_turned_b5 = get_state(user.is_show_category)

        b1 = InlineKeyboardButton(text=user_lang["change_lang"], callback_data="change_language")
        b2 = InlineKeyboardButton(text=f"{user_lang['choose_time']} {time_range}", callback_data="change_time")
        b3 = InlineKeyboardButton(text=f"{is_turned_b3} {user_lang['mute_alerts']}", callback_data="mute_alerts_change")
        b4 = InlineKeyboardButton(text=user_lang["edit_alerts"], callback_data="edit_alerts|1")
        b5 = InlineKeyboardButton(text=f"{is_turned_b5} {user_lang['show_category_button']}",
                                  callback_data="show_category")

        markup = InlineKeyboardBuilder()
        for elem in [b5, b3, b2, b4, b1]:
            markup.row(elem)
        markup.row(create_back(user_lang))
        await edit(user_id, f"⚙️ {user_lang['settings']}", markup, message_id=message_id)
    finally:
        session.close()


async def process_delete_commands(user_id, command, args, message_id):
    if command == "delete":
        session = db.get_session()
        try:
            channel_name = args[0]
            user = session.query(User).filter(User.id == user_id).first()
            if user:
                following = session.query(UserFollowing).filter(
                    UserFollowing.user_id == user_id,
                    UserFollowing.channel_name == channel_name
                ).first()
                if following:
                    session.delete(following)
                    session.commit()
        finally:
            session.close()
        args[0] = limit_page(int(args[1]), get_user_max_pages(user_id))

    if get_number_of_user_streamers(user_id) == 0:
        user_lang = get_user_lang(user_id)
        await edit(user_id, user_lang["empty_list"], back_markup(user_lang), message_id=message_id)
    else:
        await delete_streamers(user_id, int(args[0]), message_id)


async def edit_alert(user_id, channel_name, index, page, message_id):
    session = db.get_session()
    try:
        following = session.query(UserFollowing).filter(
            UserFollowing.user_id == user_id,
            UserFollowing.channel_name == channel_name
        ).first()

        if following:
            user_bin_list = bin_to_list(following.alert_settings)
            user_bin_list[index] = 0 if user_bin_list[index] else 1
            following.alert_settings = list_to_bin(user_bin_list)
            session.commit()
    finally:
        session.close()
    await edit_alerts(user_id, page, message_id)


async def process_command(command, args, user_id, message_id):
    reset_user_events(user_id, message_id)
    user_lang = get_user_lang(user_id)

    match command:
        case "start":
            session = db.get_session()
            try:
                user = session.query(User).filter(User.id == user_id).first()
                if user:
                    user.lang = args[0]
                    session.commit()
            finally:
                session.close()
            await process_command("menu", [], user_id, message_id)

        case "settings":
            await open_settings(user_id, message_id)

        case "menu":
            await menu(user_id, message_id)

        case "change_language":
            await start(user_id, message_id)

        case "change_time":
            add_event_to_user(user_id, "in_change_time", message_id, message_id)
            await edit(user_id, user_lang["enter_date"], back_markup(user_lang, add_settings=True),
                       message_id=message_id)

        case "mute_alerts_change":
            toggle_user_setting(user_id, "mute_alerts")
            await process_command("settings", [], user_id, message_id)

        case "show_category":
            toggle_user_setting(user_id, "is_show_category")
            await process_command("settings", [], user_id, message_id)

        case "add_streamers":
            add_event_to_user(user_id, "in_add_streamers", message_id=message_id)
            await edit(user_id, user_lang["enter_nicknames"], back_markup(user_lang), message_id=message_id)

        case "delete_streamers" | "delete":
            await process_delete_commands(user_id, command, args, message_id)

        case "edit_alert":
            await edit_alert(user_id, args[0], int(args[1]), int(args[2]), message_id)

        case "edit_alerts":
            await edit_alerts(user_id, int(args[0]), message_id)

        case "users_info":
            await users_info(user_id, int(args[0]), message_id)

        case "streamers_page":
            await streamers_page(user_id, int(args[0]), message_id)

        case "choose_past_broadcast":
            await choose_past_broadcast(user_id, int(args[0]), message_id)

        case "past_broadcasts":
            await open_past_broadcasts(user_id, args[0], int(args[1]), int(args[2]), message_id)

        case "search_vod":
            await process_search_vod(user_id, args[0], int(args[1]), int(args[2]), message_id)

        case "stream_titles":
            await stream_titles(user_id, args[0], int(args[1]), int(args[2]), int(args[3]), message_id)


async def stream_titles(user_id, channel_name, main_page, stream_page, titles_page, message_id):
    user_lang = get_user_lang(user_id)
    max_pages = get_max_pages_of_stream_titles(channel_name, stream_page)
    titles_page = limit_page(titles_page, max_pages)
    title_history = "\n\n".join(get_stream_titles_list(channel_name, stream_page, titles_page))

    paginator = InlineKeyboardPaginator(
        page_count=max_pages,
        current_page=titles_page,
        data_pattern=f"stream_titles|{channel_name}|{main_page}|{stream_page}|" + "{page}")
    paginator.add_after(InlineKeyboardButton(text=f"⬅️ {user_lang['return_to_list']}",
                                             callback_data=f"past_broadcasts"
                                                           f"|{channel_name}|{main_page}|{stream_page}"))
    paginator.add_after(create_back(user_lang))

    await edit(user_id, title_history, paginator, message_id=message_id)


async def process_search_vod(user_id, channel_name, main_page, stream_page, message_id):
    stream_info = get_past_broadcasts(channel_name, stream_page - 1)
    if stream_info is not None:
        await search_vod(stream_info)
    await open_past_broadcasts(user_id, channel_name, main_page, stream_page, message_id)


async def choose_past_broadcast(user_id, page, message_id):
    user_lang = get_user_lang(user_id)
    session = db.get_session()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            return

        number = sum(past_broadcasts_condition(f.channel_name) for f in user.following)

        if number == 0:
            await edit(user_id, user_lang["empty_list"], back_markup(user_lang), message_id=message_id)
        else:
            max_pages = number_to_max_page(number)
            page = limit_page(page, max_pages)
            result_list = create_past_broadcasts_list(user_id, page)

            paginator = InlineKeyboardPaginator(
                page_count=max_pages,
                current_page=page,
                data_pattern="choose_past_broadcast|{page}")
            for element in result_list:
                paginator.add_before(element)
            paginator.add_after(create_back(user_lang))

            await edit(user_id, user_lang["past_broadcasts_select"], paginator, message_id=message_id)
    finally:
        session.close()


async def open_past_broadcasts(user_id, channel_name, main_page, stream_page, message_id):
    user_lang = get_user_lang(user_id)
    max_pages = get_number_of_past_broadcasts(channel_name)
    stream_page = limit_page(stream_page, max_pages)
    stream_info = get_past_broadcasts(channel_name, stream_page - 1)

    if stream_info is not None:
        paginator = InlineKeyboardPaginator(
            page_count=max_pages,
            current_page=stream_page,
            data_pattern=f"past_broadcasts|{channel_name}|{main_page}|" + "{page}")
        if stream_info.title_history:
            paginator.add_before(InlineKeyboardButton(text=f"📜 {user_lang['title_history']}",
                                                      callback_data=f"stream_titles"
                                                                    f"|{channel_name}|{main_page}|{stream_page}|1"))
        paginator.add_after(InlineKeyboardButton(text=f"⬅️ {user_lang['return_to_list']}",
                                                 callback_data=f"choose_past_broadcast|{main_page}"))
        paginator.add_after(create_back(user_lang))

        session = db.get_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            user_tz = user.timezone if user else 0
            _start, end = (stream_info.start_time.replace(tzinfo=pytz.utc).timestamp(),
                           stream_info.end_time.replace(tzinfo=pytz.utc).timestamp())

            @dataclass
            class Data:
                category_history: list
                is_full: bool

            category_history = parse_category_history(channel_name, Data(stream_info.category_history,
                                                                         stream_info.is_full), _start, end)

            duration = format_h_m_s(end - _start)
            text = user_lang["past_broadcast_card"].format(
                create_channel_link(channel_name),
                timestamp_to_date(_start, user_tz),
                timestamp_to_date(end, user_tz),
                duration,
                format_number(stream_info.avg_viewers),
                format_number(stream_info.max_viewers),
                category_history
            )

            if not stream_info.vod_id:
                paginator.add_before(InlineKeyboardButton(text=f"🔍 {user_lang['search_vod']}",
                                                          callback_data=f"search_vod"
                                                                        f"|{channel_name}|{main_page}|{stream_page}"))
            else:
                text += f"\n\n{create_vod_link(stream_info.vod_id, user_lang)}"

            await edit(user_id, text, paginator, message_id=message_id, is_bold=False)
        finally:
            session.close()


async def search_vod(stream_info):
    if not stream_info.vod_id:
        result = None
        user_id, stream_id = stream_info.user_id, stream_info.stream_id
        try:
            connector = aiohttp.TCPConnector(family=socket.AF_INET)
            async with aiohttp.ClientSession(connector=connector) as session:
                session.headers.update(config.head)
                params = {"type": "archive", "user_id": user_id}
                async with session.get(config.url_videos, params=params) as response:
                    if response.status == 200:
                        data = (await response.json(loads=deserialize_func))["data"]
                        for stream in data:
                            if stream["stream_id"] == stream_id:
                                result = stream["id"]
                                break
        except all_exceptions:
            pass

        session = db.get_session()
        try:
            stream_info_db = session.query(PastBroadcast).filter(
                PastBroadcast.id == stream_info.id
            ).first()
            if stream_info_db:
                stream_info_db.vod_id = (result or -1)
                session.commit()
        finally:
            session.close()


async def start(user_id, message_id=None):
    new_user = False
    session = db.get_session()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            new_user = True
            user = User(
                id=user_id,
                following=[],
                reg_date=datetime.now(pytz.utc),
                events=[]
            )
            session.add(user)
            session.commit()
    finally:
        session.close()

    choose_language_list = []
    markup = InlineKeyboardBuilder()
    for lang_code, lang in config.language.items():
        flag = lang["flag"]
        choose_language_list.append(f"{flag} {lang['choose_language']}")
        markup.row(InlineKeyboardButton(text=f"{flag} {lang['name']}", callback_data=f"start|{lang_code}"))

    message_id_edit = await edit(user_id, " | ".join(choose_language_list), markup, message_id=message_id)
    if message_id is None:
        get_user_events(user_id).clear()
        await update_menu_id(user_id, message_id_edit)
    return new_user


async def menu(user_id, message_id=None):
    if user_id in [u.id for u in db.get_session().query(User).all()]:
        message_id_edit = await streamers_page(user_id, 1, message_id)
        if message_id is None:
            await update_menu_id(user_id, message_id_edit)


@dp.callback_query(lambda call: True)
async def process_callback(callback):
    message = callback.message
    user_id = str(message.chat.id)

    with suppress(*all_exceptions):
        await callback.answer()

    session = db.get_session()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if user:
            message_id = int(message.message_id)
            args = callback.data.split("|")
            await process_command(args[0], args[1:], user_id, message_id)
    finally:
        session.close()


@dp.message(F.text, Command("start"))
async def start_command(message):
    if config.stop_registration:
        return
    user_id = str(message.chat.id)
    new_user = await start(user_id)
    update_username(message.from_user)
    if new_user:
        send_message_to_admins(f"Registered new user: {get_user_name(user_id)}")


@dp.message(F.text, Command("menu"))
async def menu_command(message):
    user_id = str(message.chat.id)
    await process_command("menu", [], user_id, message_id=None)
    update_username(message.from_user)


@dp.message(F.text, Command("stats"))
async def stats_command(message):
    user_id = str(message.chat.id)
    text = config.logs

    if is_admin(user_id) and text:
        session = db.get_session()
        try:
            admin_tz = session.query(User).filter(User.id == user_id).first().timezone

            user = session.query(User).order_by(User.reg_date.desc()).first()
            d = timestamp_to_date(user.reg_date.replace(tzinfo=pytz.utc).timestamp(),
                                  admin_tz) if user else "N/A"

            total_users = session.query(User).count()
            muted_users = session.query(User).filter(User.mute_alerts).count()
            un_muted_users = session.query(User).filter(~User.mute_alerts).count()

            total_alerts = session.query(Stat.value).filter(Stat.name == "total_alerts").scalar() or 0

            text = text.format(
                len(create_channels_list()),
                total_users,
                d,
                muted_users,
                un_muted_users,
                total_alerts
            )
            await send(user_id, text)
        finally:
            session.close()


@dp.message(F.text, Command("users"))
async def users_command(message):
    await users_info(str(message.chat.id))


@dp.message(F.text, Command("ban"))
async def ban_command(message):
    user_id = str(message.chat.id)
    args = message.text.split()[1:] if len(message.text.split()) > 1 else None

    if is_admin(user_id) and args:
        user_to_ban = args[0]
        if not is_admin(user_to_ban):
            session = db.get_session()
            try:
                user = session.query(User).filter(User.id == user_to_ban).first()
                if user:
                    users_to_delete_queue.append(user_to_ban)
                    send_message_to_admins(f"Successfully banned {user_to_ban}!")
            finally:
                session.close()


@dp.message(F.text, Command("admin"))
async def admin_command(message):
    user_id = str(message.chat.id)
    args = message.text.split()[1:] if len(message.text.split()) > 1 else None

    if is_admin(user_id) and args and len(args) == 2:
        operation_name, _user_id = args
        session = db.get_session()
        try:
            if operation_name == "add":
                admin = session.query(Admin).filter(Admin.id == _user_id).first()
                if not admin:
                    session.add(Admin(id=_user_id))
                    session.commit()
            elif operation_name == "del":
                admin = session.query(Admin).filter(Admin.id == _user_id).first()
                if admin:
                    session.delete(admin)
                    session.commit()

            config.__init__()
        finally:
            session.close()


@dp.message(F.text)
async def get_text_messages(message):
    user_id = str(message.chat.id)

    session = db.get_session()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            return

        user_lang = get_user_lang(user_id)
        mess = message.text.strip()

        if is_admin(user_id) and mess == "sr":
            change_config("stop_registration", not config.stop_registration)
            await send(user_id, f"Stop registration: {'Yes' if config.stop_registration else 'No'}")
            return

        if "in_add_streamers" in get_user_events(user_id):
            user_channels = dict.fromkeys(mess.lower().split())
            added_channels, is_limit = add_channels_to_user(user_id, user_channels)
            if len(added_channels) > 0:
                await send(user_id, f"{user_lang['add_success']} {len(added_channels)} "
                                    f"({', '.join(added_channels)})")
            if is_limit:
                await send(user_id, user_lang["limit_streamers"].format(config.streamers_limit_by_user))
            await process_command("menu", [], user_id, message_id=None)

        elif "in_change_time" in get_user_events(user_id):
            message_id = get_user_events(user_id)["in_change_time"]

            filter_re = re.fullmatch(config.time_range_pattern, mess)
            if filter_re is None:
                try:
                    timezone_num = int(mess)
                except ValueError:
                    return
                if -12 <= timezone_num <= 14:
                    new_time = change_timezone(user.time_range, timezone_num)
                    user.time_range = new_time
                    user.timezone = timezone_num
                    session.commit()
                    await process_command("settings", [], user_id, message_id)
            else:
                await edit(user_id, user_lang["enter_timezone"], back_markup(user_lang, add_settings=True),
                           message_id=message_id)
                user.time_range = mess
                session.commit()
    finally:
        session.close()


@dp.my_chat_member()
async def delete_user_event(message):
    status = message.new_chat_member.status
    user_id = str(message.chat.id)
    logging.info(f"status {user_id}: {status}")
    if status == "kicked" or status == "left":
        if user_id not in users_to_delete_queue:
            users_to_delete_queue.append(user_id)
    elif status == "member":
        if user_id in users_to_delete_queue:
            users_to_delete_queue.remove(user_id)


async def run_bot():
    while True:
        logging.info("Bot starting...")
        with suppress(*all_exceptions):
            await dp.start_polling(bot, handle_signals=False)
        logging.error(f"Bot shutdown... wait {config.update_time} sec")
        await asyncio.sleep(config.update_time)


async def updating_streamer_list(loop):
    session = db.get_session()
    try:
        users_with_events = session.query(User).join(UserEvent).filter(
            UserEvent.event_type == "in_streamer_list"
        ).all()

        for user in users_with_events:
            event = next((e for e in user.events if e.event_type == "in_streamer_list"), None)
            if event and get_number_of_user_streamers(user.id) > 0:
                loop.create_task(streamers_page(
                    user.id,
                    event.event_data.get("arg", 1),
                    user.menu_id,
                    update_event=False
                ))
    finally:
        session.close()


async def send_alerts(changes, loop):
    for channel_name, change_data in changes.items():
        stream = streams[channel_name]
        session = db.get_session()
        try:
            followers = session.query(UserFollowing).filter(
                UserFollowing.channel_name == channel_name
            ).all()

            for following in followers:
                user = following.user
                if user and in_time_range(user.time_range) and not user.mute_alerts:
                    user_lang = get_user_lang(user.id)
                    duration = timestamp_to_duration(stream.timestamp_start)
                    user_bin_list = bin_to_list(following.alert_settings)
                    viewers_and_duration = f"⌛ {duration}\n👤 {stream.viewers_str}"

                    answer = ""
                    for change_type in change_data:
                        if change_type == "go_online" and user_bin_list[1]:
                            answer = user_lang["stream_alert"].format(
                                create_channel_link(channel_name, True),
                                stream.title,
                                stream.category
                            )
                        elif change_type == "change_category" and user_bin_list[0]:
                            answer = user_lang["category_alert"].format(
                                create_channel_link(channel_name),
                                stream.category,
                                stream.title,
                                viewers_and_duration
                            )
                        elif change_type == "change_stream_name" and user_bin_list[2]:
                            answer = user_lang["stream_name_alert"].format(
                                create_channel_link(channel_name),
                                stream.title,
                                stream.category,
                                viewers_and_duration
                            )
                        if answer:
                            break

                    if answer:
                        url_button = InlineKeyboardButton(text=user_lang["go_to_stream"],
                                                          url=create_channel_url(channel_name))
                        alert = AlertObject(
                            user.id,
                            answer,
                            channel_name,
                            change_data,
                            stream.thumbnail_url,
                            url_button
                        )
                        loop.create_task(send_alert(alert))
        finally:
            session.close()


async def send_alert(alert):
    markup = InlineKeyboardBuilder([[alert.url_button]]) if alert.url_button is not None else None
    message_id = await send(alert.user_id, alert.text, photo=alert.photo_url, markup=markup)
    if message_id is not None:
        update_alerts_count(alert.user_id)
        logging.info(f"Send alert to {alert.log_data}")
    else:
        send_message_to_admins(f"Didn't send alert to {alert.log_data}", error=True)


async def shutdown(loop):
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    loop.stop()


async def main():
    loop = asyncio.get_event_loop()

    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda _loop: loop.create_task(shutdown(_loop)), loop)

    get_streams_data_task = loop.create_task(get_streams_data(loop))
    run_bot_task = loop.create_task(run_bot())
    tasks = [get_streams_data_task, run_bot_task]
    with suppress(asyncio.CancelledError):
        await asyncio.gather(*tasks)


async def update_menu_id(user_id, message_id):
    session = db.get_session()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if user:
            menu_id = user.menu_id
            user.menu_id = message_id
            session.commit()

            with suppress(*all_exceptions):
                if menu_id is not None:
                    await bot.unpin_chat_message(user_id, menu_id)
                await bot.pin_chat_message(user_id, message_id, disable_notification=True)
    finally:
        session.close()


@dp.message(F.content_type == types.ContentType.MIGRATE_TO_CHAT_ID)
async def migrate_event(message):
    if message.migrate_to_chat_id:
        session = db.get_session()
        try:
            old_id, new_id = str(message.chat.id), str(message.migrate_to_chat_id)
            user = session.query(User).filter(User.id == old_id).first()
            if user:
                user.id = new_id
                session.commit()
        finally:
            session.close()


def delete_users_in_queue():
    if len(users_to_delete_queue) != 0:
        session = db.get_session()
        try:
            for user_id in users_to_delete_queue:
                user = session.query(User).filter(User.id == user_id).first()
                if user:
                    send_message_to_admins(f"Delete user {get_user_name(user_id)}")
                    session.query(UserFollowing).filter(UserFollowing.user_id == user_id).delete()
                    session.query(UserEvent).filter(UserEvent.user_id == user_id).delete()
                    session.delete(user)
            session.commit()
            users_to_delete_queue.clear()
        finally:
            session.close()


async def send_messages_in_queue():
    if len(messages_queue) != 0:
        to_delete = []
        for index, message in enumerate(messages_queue):
            message_id = await process_operation(message)
            if message_id is not None:
                if message.user_id not in config.admins:
                    send_message_to_admins(f"Send message from queue to {message.user_name}")
                to_delete.append(index)
            else:
                logging.error(f"Didn't send message from queue to {message.user_name}")
        delete_several_indexes_from_list(messages_queue, to_delete)


async def process_operation(message):
    session = db.get_session()
    try:
        user = session.query(User).filter(User.id == message.user_id).first()
        if ((user or is_admin(message.user_id)) and
                message.user_id not in users_to_delete_queue):
            markup = message.markup

            if markup is not None:
                if isinstance(markup, InlineKeyboardPaginator):
                    markup = paginator_to_aiogram_markup(markup)
                if hasattr(markup, "as_markup") and callable(getattr(markup, "as_markup")):
                    markup = markup.as_markup()

            text = str(message.text)[:4089]
            text_result = f"<b>{text}</b>" if message.is_bold else text

            try:
                if message.operation == "edit":
                    if message.message_id is not None:
                        await bot.edit_message_text(
                            text_result,
                            message.user_id,
                            message.message_id,
                            reply_markup=markup,
                            **message.kwargs
                        )
                        return message.message_id
                    else:
                        message.operation = "send"

                if message.operation == "send":
                    if message.photo is not None and message.photo:
                        s = await bot.send_photo(
                            message.user_id,
                            message.photo,
                            caption=text_result,
                            reply_markup=markup,
                            **message.kwargs
                        )
                    else:
                        s = await bot.send_message(
                            message.user_id,
                            text_result,
                            reply_markup=markup,
                            **message.kwargs
                        )
                    return s.message_id
            except all_exceptions as e:
                if ((isinstance(e, TelegramBadRequest) and "chat not found" in str(e)) or
                     isinstance(e, TelegramMigrateToChat)):
                    users_to_delete_queue.append(message.user_id)
                elif message.operation != "edit" and message not in messages_queue:
                    messages_queue.append(message)
                    logging.error(e)
        return None
    finally:
        session.close()


async def edit(user_id, text, markup, is_bold=True, message_id=None, **kwargs):
    message = MessageObject("edit", user_id, text, markup, is_bold, message_id=message_id, kwargs=kwargs)
    return await process_operation(message)


async def send(user_id, text, markup=None, is_bold=False, photo=None, **kwargs):
    message = MessageObject("send", user_id, text, markup, is_bold, photo, kwargs=kwargs)
    return await process_operation(message)


if __name__ == "__main__":
    asyncio.run(main())
