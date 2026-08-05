from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, JSON, ForeignKey
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
import pytz
from datetime import datetime
import orjson

Base = declarative_base()


def get_timestamp_utc():
    return round(datetime.now(pytz.utc).timestamp())


class User(Base):
    __tablename__ = 'users'

    id = Column(String, primary_key=True)
    username = Column(String)
    nickname = Column(String)
    lang = Column(String, default='en')
    timezone = Column(Integer, default=0)
    time_range = Column(String, default='00:00-23:59')
    mute_alerts = Column(Boolean, default=False)
    is_show_category = Column(Boolean, default=True)
    reg_date = Column(DateTime, default=get_timestamp_utc)
    menu_id = Column(Integer)
    alerts_count = Column(Integer, default=0)

    following = relationship("UserFollowing", back_populates="user")
    events = relationship("UserEvent", back_populates="user")


class UserFollowing(Base):
    __tablename__ = 'user_following'

    id = Column(Integer, primary_key=True)
    user_id = Column(String, ForeignKey('users.id'))
    channel_name = Column(String)
    alert_settings = Column(Integer, default=2)  # Binary flags for alert types

    user = relationship("User", back_populates="following")


class UserEvent(Base):
    __tablename__ = 'user_events'

    id = Column(Integer, primary_key=True)
    user_id = Column(String, ForeignKey('users.id'))
    event_type = Column(String)
    event_data = Column(JSON)

    user = relationship("User", back_populates="events")


class Streamer(Base):
    __tablename__ = 'streamers'

    channel_name = Column(String, primary_key=True)
    display_name = Column(String)
    last_seen = Column(DateTime)

    past_broadcasts = relationship("PastBroadcast", back_populates="streamer")
    temp_info = relationship("TempStreamInfo", back_populates="streamer")


class PastBroadcast(Base):
    __tablename__ = 'past_broadcasts'

    id = Column(Integer, primary_key=True)
    channel_name = Column(String, ForeignKey('streamers.channel_name'))
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    is_full = Column(Boolean)
    stream_id = Column(String)
    user_id = Column(String)
    avg_viewers = Column(Integer)
    max_viewers = Column(Integer)
    vod_id = Column(String)
    title_history = Column(JSON)  # List of titles
    category_history = Column(JSON)  # List of {"category": timestamp}

    streamer = relationship("Streamer", back_populates="past_broadcasts")


class TempStreamInfo(Base):
    __tablename__ = 'temp_stream_info'

    id = Column(Integer, primary_key=True)
    channel_name = Column(String, ForeignKey('streamers.channel_name'))
    is_full = Column(Boolean)
    viewers_data = Column(JSON)  # {avg: float, count: int, max: int}
    title_history = Column(JSON)  # List of titles
    category_history = Column(JSON)  # List of {"category": timestamp}

    streamer = relationship("Streamer", back_populates="temp_info")


class Admin(Base):
    __tablename__ = 'admins'

    id = Column(String, primary_key=True)


class Stat(Base):
    __tablename__ = 'stats'

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    value = Column(Integer)


class DBConfig(Base):
    __tablename__ = 'config'

    key = Column(String, primary_key=True)
    value = Column(String)


class Language(Base):
    __tablename__ = "languages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String, unique=True, nullable=False)
    flag = Column(String, nullable=False)
    name = Column(String, nullable=False)
    data = Column(JSON, nullable=False)


class Database:
    def __init__(self, db_path='./data/bot.db'):
        self.engine = create_engine(f'sqlite:///{db_path}',
                                    pool_size=600,
                                    max_overflow=500,
                                    pool_timeout=30,
                                    pool_recycle=18000,
                                    pool_pre_ping=True,
                                    connect_args={'timeout': 30},
                                    json_serializer=lambda obj: orjson.dumps(obj).decode("utf-8",
                                                                                         errors="ignore"))
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def get_session(self):
        return self.Session()
