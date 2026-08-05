import os
from models import *


def load_json(file_path):
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return orjson.loads(f.read())
    return {}


def clean_tables(session):
    try:
        session.query(UserEvent).delete()
        session.query(TempStreamInfo).delete()
        session.query(Stat).delete()
        session.query(PastBroadcast).delete()
        session.query(UserFollowing).delete()
        session.query(Streamer).delete()
        session.query(User).delete()
        session.query(Language).delete()
        session.commit()
    except:
        session.rollback()


def migrate_data():
    # Инициализация базы данных
    db = Database(db_path="./migration_data/bot.db")
    session = db.get_session()
    # clean_tables(session)

    try:
        # Миграция users.json
        users_path = os.path.join('migration_data', 'users.json')
        users_data = load_json(users_path)
        if users_data:
            for user_id, user_data in users_data.items():
                user = User(
                    id=user_id,
                    username=user_data.get('username', None),
                    nickname=user_data.get('nickname', None),
                    lang=user_data.get('lang', 'en'),
                    timezone=user_data.get('timezone', 0),
                    time_range=user_data.get('time', '00:00-23:59'),
                    mute_alerts=bool(user_data.get('mute_alerts', False)),
                    is_show_category=bool(user_data.get('is_show_category', True)),
                    reg_date=datetime.fromtimestamp(user_data.get('reg_date', 0), tz=pytz.utc),
                    menu_id=user_data.get('menu_id', 0),
                    alerts_count=0
                )
                session.merge(user)

                # Миграция подписок пользователя
                if 'following' in user_data:
                    for channel_name, alert_settings in user_data['following'].items():
                        following = UserFollowing(
                            user_id=user_id,
                            channel_name=channel_name,
                            alert_settings=alert_settings
                        )
                        session.merge(following)

                # Миграция событий пользователя
                if 'events' in user_data:
                    for event_type, event_arg in user_data['events'].items():
                        event = UserEvent(
                            user_id=user_id,
                            event_type=event_type,
                            event_data={'arg': event_arg}
                        )
                        session.merge(event)

            print(f"Migrated users.json: {len(users_data)} users")

        # Миграция streamers_info.json
        streamers_info_path = os.path.join('migration_data', 'streamers_info.json')
        streamers_info_data = load_json(streamers_info_path)
        if streamers_info_data:
            for channel_name, streamer_data in streamers_info_data.items():
                streamer = Streamer(
                    channel_name=channel_name,
                    display_name=streamer_data.get('display_name', None),
                    last_seen=datetime.fromtimestamp(
                        streamer_data['timestamp'], tz=pytz.utc) if 'timestamp' in streamer_data else None
                )
                session.merge(streamer)

                # Миграция прошлых трансляций
                if 'past_broadcasts' in streamer_data:
                    for broadcast_data in streamer_data['past_broadcasts']:
                        vod_id = None
                        if "vod_id" in broadcast_data:
                            vod_id = broadcast_data["vod_id"] if broadcast_data["vod_id"] is not None else "-1"

                        broadcast = PastBroadcast(
                            channel_name=channel_name,
                            start_time=datetime.fromtimestamp(broadcast_data['start'], tz=pytz.utc),
                            end_time=datetime.fromtimestamp(broadcast_data['end'], tz=pytz.utc),
                            is_full=bool(broadcast_data.get("full")),
                            stream_id=broadcast_data.get('stream_id'),
                            user_id=broadcast_data.get('user_id'),
                            avg_viewers=broadcast_data.get('viewers', 0),
                            max_viewers=broadcast_data.get('max_viewers', 0),
                            vod_id=vod_id,
                            title_history=broadcast_data.get('title_history', []),
                            category_history=broadcast_data.get('history', [])
                        )
                        session.merge(broadcast)

            print(f"Migrated streamers_info.json: {len(streamers_info_data)} streamers")

        # Миграция temp_stream_info.json
        temp_stream_info_path = os.path.join('migration_data', 'temp_stream_info.json')
        temp_stream_info_data = load_json(temp_stream_info_path)
        if temp_stream_info_data:
            for channel_name, temp_data in temp_stream_info_data.items():
                temp_info = TempStreamInfo(
                    channel_name=channel_name,
                    is_full=bool(temp_data.get("full")),
                    viewers_data={
                        'avg': temp_data.get('viewers', 0),
                        'count': temp_data.get('n_viewers', 0),
                        'max': temp_data.get('max_viewers', 0)
                    } if 'viewers' in temp_data else None,
                    title_history=temp_data.get('title_history', []),
                    category_history=temp_data.get('history', [])
                )
                session.merge(temp_info)

            print(f"Migrated temp_stream_info.json: {len(temp_stream_info_data)} temp infos")

        language_path = os.path.join('migration_data', 'language.json')
        languages_data = load_json(language_path)
        if languages_data:
            # Переносим данные
            for code, content in languages_data.items():
                lang = Language(
                    code=code,
                    flag=content.get("flag", ""),
                    name=content.get("name", ""),
                    data={k: v for k, v in content.items() if k not in ("flag", "name")}
                )
                session.merge(lang)  # merge чтобы перезаписывать при повторном запуске

        session.commit()
        print("Migration completed successfully!")

    except Exception as e:
        session.rollback()
        print(f"Migration failed: {str(e)}")
    finally:
        session.close()


if __name__ == "__main__":
    print("Starting migration from JSON to SQLite...")
    migrate_data()
    input()
