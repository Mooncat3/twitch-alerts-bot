import re
import math
from datetime import timedelta
from time import gmtime, strftime
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dateutil.relativedelta import relativedelta
from settings import *
from models import *
import iso8601
from aiogram import html


def delete_several_indexes_from_list(lst, indexes):
    for i in range(len(indexes)):
        index = indexes[i]
        if index < len(lst):
            del lst[index]
            indexes = [e - 1 for e in indexes]


def prettier_nicknames(channel_name):
    session = db.get_session()
    try:
        streamer = session.query(Streamer).filter(Streamer.channel_name == channel_name).first()
        if streamer and streamer.display_name:
            return streamer.display_name
        return channel_name
    finally:
        session.close()


def format_number(number, separator=" "):
    number = str(number)
    result = ""
    for i, digit in enumerate(number[::-1]):
        if i % 3 == 0:
            result += separator
        result += digit
    return result[::-1][:-1]


def split_list(lst, n):
    if lst:
        for i in range(0, len(lst), n):
            yield lst[i:i + n]
    else:
        yield []


def calc_avg(number, current_avg, count):
    return (current_avg * count + number) / (count + 1)


def create_back(user_lang, settings=False):
    if settings:
        return InlineKeyboardButton(text=f"⬅️ {user_lang['return_to_settings']}", callback_data="settings")
    return InlineKeyboardButton(text=f"⬅️ {user_lang['return_to_menu']}", callback_data="menu")


def back_markup(user_lang, add_settings=False):
    markup = InlineKeyboardBuilder()
    if add_settings:
        markup.row(create_back(user_lang, settings=True))
    markup.row(create_back(user_lang))
    return markup


def get_user_lang(user_id):
    session = db.get_session()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if user and user.lang in config.language:
            return config.language[user.lang]
        return config.language["en"]
    finally:
        session.close()


def get_page(_list, page, count=None):
    if page is None:
        return _list
    if count is None:
        count = config.streamers_in_page
    return _list[((page - 1) * count):(page * count)]


def get_user_list(user_id, page=None):
    session = db.get_session()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if user:
            following = {f.channel_name: f.alert_settings for f in user.following}
            if page is not None:
                following_keys = list(following.keys())
                following_keys_page = get_page(following_keys, page)
                following = {k: following[k] for k in following_keys_page}
            return following
        return {}
    finally:
        session.close()


def get_number_of_user_streamers(user_id):
    session = db.get_session()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if user:
            return len(user.following)
        return 0
    finally:
        session.close()


def number_to_max_page(number):
    if number < 1:
        return 1
    return math.ceil(number / config.streamers_in_page)


def get_user_max_pages(user_id):
    return number_to_max_page(get_number_of_user_streamers(user_id))


def is_admin(user_id):
    return str(user_id) in config.admins


def create_edit_buttons(user_id, page):
    session = db.get_session()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            return []

        user_following = session.query(UserFollowing).filter(UserFollowing.user_id == user_id).all()
        user_dict = get_page(user_following, page)

        result_list = []
        cols = get_user_lang(user_id)["edit_alerts_text"].split("\n")

        for index, following in enumerate(user_dict):
            if index % config.streamers_in_page == 0:
                buttons_header = [InlineKeyboardButton(text="⠀", callback_data="|")]
                for col in cols:
                    buttons_header.append(InlineKeyboardButton(text=col, callback_data="|"))
                result_list.append(buttons_header)

            b_list = [InlineKeyboardButton(text=prettier_nicknames(following.channel_name), callback_data="|")]
            for i, value in enumerate(bin_to_list(following.alert_settings)):
                b_list.append(InlineKeyboardButton(text=get_state(value),
                                                   callback_data=f"edit_alert|{following.channel_name}|{i}|{page}"))
            result_list.append(b_list)
        return result_list
    finally:
        session.close()


def get_state(value):
    return "✅" if value else "❌"


def bin_to_list(value):
    cols = config.language["en"]["edit_alerts_text"].split("\n")
    bin_value = bin(int(value))[2:]
    while len(bin_value) < len(cols):
        bin_value = "0" + bin_value
    result = [int(e) for e in bin_value]
    return result


def list_to_bin(value):
    result = "".join(map(str, value))
    return int(result, 2)


def split_time_range(time):
    time = time.split("-")
    date1 = datetime.strptime(time[0], "%H:%M")
    date2 = datetime.strptime(time[1], "%H:%M")
    return date1, date2


def in_time_range(time):
    date1, date2 = split_time_range(time)
    date2 += timedelta(seconds=59, milliseconds=990)
    date_now = datetime.now(pytz.utc)
    date_now = datetime.strptime(str(timedelta(hours=date_now.hour,
                                               minutes=date_now.minute,
                                               seconds=date_now.second)), "%H:%M:%S")
    if date_now < date1:
        date_now += timedelta(days=1)
    if date1 > date2:
        date2 += timedelta(days=1)
    return date1 <= date_now <= date2


def change_timezone(time, timezone_num, back=False):
    date1, date2 = split_time_range(time)
    if back:
        date1 += timedelta(hours=timezone_num)
        date2 += timedelta(hours=timezone_num)
    else:
        date1 -= timedelta(hours=timezone_num)
        date2 -= timedelta(hours=timezone_num)
    return f"{datetime.strftime(date1, '%H:%M')}-{datetime.strftime(date2, '%H:%M')}"


def format_h_m_s(seconds):
    hours = int(seconds // 3600)
    duration = strftime("%M:%S", gmtime(seconds))
    return f"{hours:02d}:{duration}"


def timestamp_to_duration(timestamp):
    if timestamp == 0:
        return "00:00:00"
    duration = get_timestamp_utc() - timestamp
    return format_h_m_s(duration)


def timestamp_to_date(timestamp, to_timezone=0):
    d = datetime.fromtimestamp(timestamp, tz=pytz.utc)
    d += timedelta(hours=to_timezone)
    result_format = "%H:%M:%S UTC, %d %b %Y" if to_timezone == 0 else "%H:%M:%S, %d %b %Y"
    return d.strftime(result_format)


def update_last_seen_nicknames(streams_past, channels_list):
    session = db.get_session()
    try:
        for channel_name, stream in streams.items():
            if channel_name in streams_past and streams_past[channel_name].online and not stream.online:
                streamer = session.query(Streamer).filter(Streamer.channel_name == channel_name).first()
                if not streamer:
                    streamer = Streamer(channel_name=channel_name)
                    session.add(streamer)
                streamer.last_seen = datetime.now(pytz.utc)
                session.commit()

        existing_streamers = session.query(Streamer).all()
        for streamer in existing_streamers:
            if streamer.channel_name not in channels_list:
                streamer.last_seen = None
        session.commit()
    finally:
        session.close()


def update_temp_stream_info(session, channel_name, category_name, timestamp=None):
    timestamp_res = get_timestamp_utc() if timestamp is None else timestamp
    temp_info = session.query(TempStreamInfo).filter(TempStreamInfo.channel_name == channel_name).first()

    if not temp_info:
        temp_info = TempStreamInfo(
            channel_name=channel_name,
            is_full=(timestamp is not None),
            title_history=[],
            category_history=[{category_name: timestamp_res}]
        )
        session.add(temp_info)
    else:
        category_history = temp_info.category_history.copy() if temp_info.category_history else []
        category_history.append({category_name: timestamp_res})
        temp_info.category_history = category_history

    session.commit()


def update_viewers(channel_name, viewers):
    session = db.get_session()
    try:
        temp_info = session.query(TempStreamInfo).filter(TempStreamInfo.channel_name == channel_name).first()
        if not temp_info:
            return

        viewers_data = temp_info.viewers_data.copy() if temp_info.viewers_data else None
        if not viewers_data:
            viewers_data = {"avg": viewers, "count": 1, "max": viewers}
        else:
            viewers_data["avg"] = round(calc_avg(viewers, viewers_data["avg"], viewers_data["count"]), 4)
            viewers_data["count"] += 1
            if viewers > viewers_data["max"]:
                viewers_data["max"] = viewers

        temp_info.viewers_data = viewers_data
        session.commit()
    finally:
        session.close()


def update_alerts_count(user_id):
    session = db.get_session()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if user:
            user.alerts_count = (user.alerts_count or 0) + 1
            session.commit()

        stat = session.query(Stat).filter(Stat.name == "total_alerts").first()
        if not stat:
            stat = Stat(name="total_alerts", value=1)
            session.add(stat)
        else:
            stat.value += 1
        session.commit()
    finally:
        session.close()


def update_title_history(channel_name, stream_title):
    session = db.get_session()
    try:
        temp_info = session.query(TempStreamInfo).filter(TempStreamInfo.channel_name == channel_name).first()
        if temp_info:
            if not temp_info.title_history:
                temp_info.title_history = [stream_title]
            elif stream_title and stream_title != temp_info.title_history[-1]:
                title_history = temp_info.title_history.copy() if temp_info.title_history else []
                title_history.append(stream_title)
                temp_info.title_history = title_history
            session.commit()
    finally:
        session.close()


def update_category_history(streams_past, changes):
    session = db.get_session()
    try:
        for channel_name, stream in streams_past.items():
            if channel_name not in streams or (not stream.online and not streams[channel_name].online):
                session.query(TempStreamInfo).filter(TempStreamInfo.channel_name == channel_name).delete()
                session.commit()

        for channel_name, stream in streams.items():
            if channel_name in streams_past:
                if (stream.timestamp_start != streams_past[channel_name].timestamp_start and
                        streams_past[channel_name].timestamp_start):
                    update_past_broadcasts(channel_name, streams_past[channel_name])
                    session.query(TempStreamInfo).filter(TempStreamInfo.channel_name == channel_name).delete()
                    session.commit()

                if channel_name in changes and "go_online" in changes[channel_name]:
                    session.query(TempStreamInfo).filter(TempStreamInfo.channel_name == channel_name).delete()
                    update_temp_stream_info(session, channel_name, stream.category, stream.timestamp_start)

                elif stream.category and stream.category != streams_past[channel_name].category:
                    update_temp_stream_info(session, channel_name, stream.category)

            elif stream.online:
                temp_info = session.query(TempStreamInfo).filter(TempStreamInfo.channel_name == channel_name).first()
                if not temp_info or stream.category != list(temp_info.category_history[-1].keys())[0]:
                    update_temp_stream_info(session, channel_name, stream.category)

            update_viewers(channel_name, stream.viewers_int)
            update_title_history(channel_name, stream.title)
    finally:
        session.close()


def get_indent(is_now):
    if is_now:
        return " " * 10
    return ""


def parse_category_history(channel_name, data, timestamp_start=None, timestamp_end=None):
    is_now = timestamp_start is None
    is_full = data.is_full

    if timestamp_start is None:
        timestamp_start = streams[channel_name].timestamp_start
    if timestamp_end is None:
        timestamp_end = get_timestamp_utc()

    text = "<i>" if is_full else f"<i>\n{get_indent(is_now)}. . ."
    prev_durations = 0
    history = data.category_history

    for i, d in enumerate(history):
        category_name = list(d.keys())[0]
        text += f"\n{get_indent(is_now)}"

        if i == len(history) - 1:
            timestamp = timestamp_end
            if is_full:
                timestamp -= timestamp_start + prev_durations - (d[category_name] or 0)
            if is_now:
                text += "➡️ "
        else:
            timestamp = list(history[i + 1].values())[0]

        duration = timestamp - (d[category_name] or 0)
        prev_durations += duration
        duration = format_h_m_s(duration)

        if i == 0 and not is_full:
            duration = "no data"
        text += f"{category_name} [{duration}]"
    return f"{text}</i>"


def get_online(is_online):
    if is_online is None:
        return ""
    return "🔴 " if is_online else "⚫ "


def paginator_to_aiogram_markup(paginator):
    markup = InlineKeyboardBuilder()
    if paginator.markup is not None:
        buttons = deserialize_func(paginator.markup)["inline_keyboard"]
        for element in buttons:
            buttons_row = [InlineKeyboardButton(text=e["text"], callback_data=e["callback_data"]) for e in element]
            markup.row(*buttons_row)
    return markup.as_markup()


def create_channel_postfix(channel_name, user_id):
    user_lang = get_user_lang(user_id)

    if channel_name in streams:
        stream_data = streams[channel_name]
        duration = timestamp_to_duration(stream_data.timestamp_start)

        session = db.get_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if stream_data.online and user and user.is_show_category:
                result = f" | ⌛ {duration} | 👤 {stream_data.viewers_str}\n"
                temp_info = session.query(TempStreamInfo).filter(TempStreamInfo.channel_name == channel_name).first()
                if temp_info:
                    result += f"{parse_category_history(channel_name, temp_info)}\n"
            elif stream_data.online:
                result = f" | {stream_data.category} | ⌛ {duration} | 👤 {stream_data.viewers_str}\n"
            else:
                result = last_seen(channel_name, user_lang)
        finally:
            session.close()
    else:
        result = f" — {user_lang['not_checked']}"
    return result


def create_user_list(user_id, page=None):
    user_list = get_user_list(user_id)

    streamers_dataset = {channel_name: streams[channel_name] if channel_name in streams else StreamObject(online=None)
                         for channel_name in user_list}

    streamers_online = set(k for k, v in streamers_dataset.items() if v.online)
    streamers_offline_with_seen = set(k for k, v in streamers_dataset.items() if v.online is not None and not v.online
                                      and last_seen_condition(k))
    streamers_offline = set(streamers_dataset.keys()).difference(streamers_online.union(streamers_offline_with_seen))

    streamers_online = sorted(list(streamers_online), key=lambda k: streamers_dataset[k].viewers_int, reverse=True)
    streamers_offline_with_seen = sorted(list(streamers_offline_with_seen), key=lambda k: get_delta_last_seen(k)[1])
    streamers_offline = sorted(list(streamers_offline))

    streamers_data_list = streamers_online + streamers_offline_with_seen + streamers_offline
    streamers_data_list = get_page(streamers_data_list, page)

    streamers_list = [(f"\n{create_channel_link(e, streamers_dataset[e].online)}"
                       f"{create_channel_postfix(e, user_id)}") for e in streamers_data_list]
    return streamers_list


def create_past_broadcasts_list(user_id, page):
    user_list = get_user_list(user_id)
    session = db.get_session()
    try:
        result_list = []
        for element in user_list:
            count = session.query(PastBroadcast).filter(PastBroadcast.channel_name == element).count()
            if count > 0:
                result_list.append(
                    InlineKeyboardButton(
                        text=f"{prettier_nicknames(element)} ({count})",
                        callback_data=f"past_broadcasts|{element}|{page}|{count}"
                    )
                )
        return get_page(result_list, page)
    finally:
        session.close()


def format_time(delta, seconds, user_lang):
    if seconds < 60:
        return f"{seconds} {user_lang['seconds']}"
    elif seconds < 3600:
        return f"{delta.minutes} {user_lang['minutes']} {delta.seconds} {user_lang['seconds']}"
    elif seconds < 86400:
        return f"{delta.hours} {user_lang['hours']} {delta.minutes} {user_lang['minutes']}"
    elif (delta.years * 12) + delta.months == 0:
        return f"{delta.days} {user_lang['days']} {delta.hours} {user_lang['hours']}"
    elif delta.years == 0:
        return f"{delta.months} {user_lang['months']} {delta.days} {user_lang['days']}"
    return f"{delta.years} {user_lang['years']} {delta.months} {user_lang['months']}"


def last_seen_condition(channel_name):
    session = db.get_session()
    try:
        streamer = session.query(Streamer).filter(Streamer.channel_name == channel_name).first()
        return (streamer and streamer.last_seen is not None and
                channel_name in streams and not streams[channel_name].online)
    finally:
        session.close()


def get_delta_last_seen(channel_name):
    if last_seen_condition(channel_name):
        session = db.get_session()
        try:
            streamer = session.query(Streamer).filter(Streamer.channel_name == channel_name).first()
            date_now = datetime.now(pytz.utc)
            _last_seen = streamer.last_seen.replace(tzinfo=pytz.utc)
            delta = date_now - _last_seen
            return relativedelta(date_now, _last_seen), delta.total_seconds()
        finally:
            session.close()
    else:
        return relativedelta(), None


def last_seen(channel_name, user_lang):
    delta, total_seconds = get_delta_last_seen(channel_name)
    if total_seconds is not None:
        return f" — {format_time(delta, round(total_seconds), user_lang)} {user_lang['ago']}"
    else:
        return ""


def filter_channels(channels_list):
    channels_list_filtered = []
    for chan in channels_list:
        filter_re = re.fullmatch(config.twitch_user_pattern, chan)
        if filter_re is not None:
            channels_list_filtered.append(filter_re.string)
    return channels_list_filtered


def create_channels_list():
    session = db.get_session()
    try:
        channels_list = set()
        users = session.query(User).all()
        for user in users:
            channels_list.update([f.channel_name for f in user.following])
        return filter_channels(channels_list)
    finally:
        session.close()


def create_user_info(user_id, admin_id):
    session = db.get_session()
    try:
        admin_tz = session.query(User).filter(User.id == admin_id).first().timezone

        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            return "User not found"

        reg_date = timestamp_to_date(user.reg_date.replace(tzinfo=pytz.utc).timestamp(),
                                     admin_tz) if user.reg_date else "-"

        following_info = []
        for follow in user.following:
            following_info.append(f"{follow.channel_name}: {bin_to_list(follow.alert_settings)}")

        user_info = config.user_info.format(
            user.id,
            get_user_name(user.id),
            user.nickname or "-",
            reg_date,
            user.lang or "-",
            get_user_events(user.id),
            user.mute_alerts,
            user.alerts_count or 0,
            "\n".join(following_info)
        )
        user_info += f"\n\n{''.join(create_user_list(user.id))}"
        return user_info
    finally:
        session.close()


def add_to_changes(changes, channel_name, change_name):
    if channel_name in changes:
        changes[channel_name].append(change_name)
    else:
        changes.update({channel_name: [change_name]})


def check_changes(streams_past):
    changes = {}
    for channel_name, stream in streams.items():
        if channel_name in streams_past and stream.online:
            if stream.timestamp_start != streams_past[channel_name].timestamp_start:
                add_to_changes(changes, channel_name, "go_online")
            if stream.category != streams_past[channel_name].category and streams_past[channel_name].category:
                add_to_changes(changes, channel_name, "change_category")
            if stream.title != streams_past[channel_name].title and streams_past[channel_name].title:
                add_to_changes(changes, channel_name, "change_stream_name")
    return changes


def reset_user_events(user_id, message_id):
    session = db.get_session()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if user:
            main_message = is_main_message(user_id, message_id)
            for event in user.events:
                if event.event_type not in config.main_events or main_message:
                    session.delete(event)
            session.commit()
    finally:
        session.close()


def add_event_to_user(user_id, event, arg=1, message_id=None):
    if event in config.main_events and not is_main_message(user_id, message_id):
        return
    reset_user_events(user_id, message_id)

    session = db.get_session()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if user:
            new_event = UserEvent(user_id=user_id, event_type=event, event_data={"arg": arg})
            session.add(new_event)
            session.commit()
    finally:
        session.close()


def get_user_events(user_id):
    session = db.get_session()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if user:
            return {e.event_type: e.event_data.get("arg", 1) for e in user.events}
        return {}
    finally:
        session.close()


def is_main_message(user_id, message_id):
    if message_id is None:
        return True
    session = db.get_session()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        return user and str(user.menu_id) == str(message_id)
    finally:
        session.close()


def update_username(from_user):
    session = db.get_session()
    try:
        user = session.query(User).filter(User.id == str(from_user.id)).first()
        if user:
            first_name = "" if from_user.first_name is None else from_user.first_name
            last_name = "" if from_user.last_name is None else f" {from_user.last_name}"
            user.username = from_user.username
            user.nickname = f"{first_name}{last_name}"
            session.commit()
    finally:
        session.close()


def add_channels_to_user(user_id, user_channels):
    user_channels_filtered = filter_channels(user_channels)
    added_channels = []
    is_limit = False

    session = db.get_session()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            return [], False

        current_count = len(user.following)
        is_user_admin = is_admin(user_id)

        for user_channel in user_channels_filtered:
            if current_count < config.streamers_limit_by_user or is_user_admin:
                existing = session.query(UserFollowing).filter(
                    UserFollowing.user_id == user_id,
                    UserFollowing.channel_name == user_channel
                ).first()

                if not existing:
                    new_following = UserFollowing(
                        user_id=user_id,
                        channel_name=user_channel
                    )
                    session.add(new_following)
                    added_channels.append(user_channel)
                    current_count += 1
            else:
                is_limit = True
                break

        session.commit()
        return added_channels, is_limit
    finally:
        session.close()


def limit_page(page, len_result_list):
    if page > len_result_list:
        page = len_result_list
    if page < 1:
        page = 1
    return page


def create_channel_url(channel_name):
    return "https://twitch.tv/" + channel_name


def create_channel_link(channel_name, is_online=None):
    return (f"<a href='{create_channel_url(channel_name)}'><b>{get_online(is_online)}"
            f"{prettier_nicknames(channel_name)}</b></a>")


def create_vod_link(vod_id, user_lang):
    if vod_id is None or str(vod_id) == "-1":
        return user_lang["vod_not_found"]
    return f"<a href='https://twitch.tv/videos/{vod_id}'><b>🔗 {user_lang['link_to_vod']}</b></a>"


def update_past_broadcasts(channel_name, stream):
    session = db.get_session()
    try:
        temp_info = session.query(TempStreamInfo).filter(TempStreamInfo.channel_name == channel_name).first()
        if not temp_info:
            return

        viewers_data = temp_info.viewers_data or {"avg": 0, "max": 0}

        past_broadcast = PastBroadcast(
            channel_name=channel_name,
            start_time=datetime.fromtimestamp(stream.timestamp_start, tz=pytz.utc),
            end_time=datetime.fromtimestamp(get_timestamp_utc(), tz=pytz.utc),
            is_full=temp_info.is_full,
            stream_id=stream.stream_id,
            user_id=stream.user_id,
            avg_viewers=round(viewers_data.get("avg", 0)),
            max_viewers=viewers_data.get("max", 0),
            title_history=temp_info.title_history or [],
            category_history=temp_info.category_history or []
        )
        session.add(past_broadcast)
        session.commit()
    finally:
        session.close()


def get_number_of_past_broadcasts(channel_name):
    session = db.get_session()
    try:
        return session.query(PastBroadcast).filter(PastBroadcast.channel_name == channel_name).count()
    finally:
        session.close()


def past_broadcasts_condition(channel_name):
    return get_number_of_past_broadcasts(channel_name) > 0


def get_past_broadcasts(channel_name, index=None):
    session = db.get_session()
    try:
        broadcasts = session.query(PastBroadcast).filter(
            PastBroadcast.channel_name == channel_name
        ).order_by(PastBroadcast.start_time.asc()).all()

        if index is None:
            return broadcasts
        elif index < len(broadcasts):
            return broadcasts[index]
        return None
    finally:
        session.close()


def get_stream_titles_list(channel_name, stream_page, titles_page=None):
    stream_info = get_past_broadcasts(channel_name, stream_page - 1)
    if stream_info is not None and stream_info.title_history:
        titles_list = stream_info.title_history
        if titles_page is not None:
            titles_list = get_page(titles_list, titles_page, config.stream_titles_in_page)
        return titles_list
    return ["No data"]


def get_max_pages_of_stream_titles(channel_name, stream_page):
    return math.ceil(len(get_stream_titles_list(channel_name, stream_page)) / config.stream_titles_in_page)


def change_config(key, value):
    session = db.get_session()
    try:
        config_entry = session.query(DBConfig).filter(DBConfig.key == key).first()
        if not config_entry:
            config_entry = DBConfig(key=key, value=value)
            session.add(config_entry)
        else:
            config_entry.value = value
        session.commit()
        config.__init__()
    finally:
        session.close()


def toggle_user_setting(user_id, setting):
    session = db.get_session()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if user:
            current_value = getattr(user, setting, False)
            setattr(user, setting, not current_value)
            session.commit()
    finally:
        session.close()


def add_stream_to_streams(channel_data):
    stream_id = channel_data["id"]
    user_id = channel_data["user_id"]
    display_name = channel_data["user_name"]
    channel_name = channel_data["user_login"]
    title = html.quote(channel_data["title"])
    game = html.quote(channel_data["game_name"])
    res = iso8601.parse_date(channel_data["started_at"])
    viewers = channel_data["viewer_count"]
    thumbnail_url = channel_data["thumbnail_url"].replace("{width}", "1280").replace("{height}", "720")
    thumbnail_url += f"?a={get_timestamp_utc()}"
    game = "Uncategorized" if not game else game

    streams.update({
        channel_name: StreamObject(
            True,
            round(res.timestamp()),
            title,
            game,
            format_number(viewers),
            viewers,
            thumbnail_url,
            stream_id,
            user_id
        )
    })
    if channel_name != display_name:
        session = db.get_session()
        try:
            streamer = session.query(Streamer).filter(Streamer.channel_name == channel_name).first()
            if not streamer:
                streamer = Streamer(channel_name=channel_name, display_name=display_name)
                session.add(streamer)
            elif streamer.display_name != display_name:
                streamer.display_name = display_name
            session.commit()
        finally:
            session.close()


def add_last_update(text, user_id, user_lang):
    if text[-1] != "\n":
        text += "\n"

    session = db.get_session()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        _timezone = user.timezone if user else 0
        text += f"\n{user_lang['last_update']} {timestamp_to_date(get_timestamp_utc(), _timezone)}"
        return text
    finally:
        session.close()
