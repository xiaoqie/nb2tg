import sqlite3
from dataclasses import dataclass


@dataclass
class Message:
    qq_unique_id: int
    qq_msg_id: int
    tg_bot_id: int
    tg_forum_topic_id: int
    tg_msg_id: int

@dataclass
class ForumTopic:
    tg_forum_topic_id: int
    qq_unique_id: int

class Database:
    def __init__(self, path) -> None:
        self.con = sqlite3.connect(path)
        # self.con.execute("DROP TABLE message")
        self.con.execute("""
CREATE TABLE IF NOT EXISTS message (
    qq_unique_id INT NOT NULL,
    qq_msg_id INT NOT NULL,
    tg_bot_id INT NOT NULL,
    tg_forum_topic_id INT NOT NULL,
    tg_msg_id INT NOT NULL
)""")
        self.con.execute("""
CREATE TABLE IF NOT EXISTS forum_topic (
    qq_unique_id INT NOT NULL,
    tg_forum_topic_id INT NOT NULL
)""")
        self.con.commit()

    def insert_message(self, obj: Message):
        self.con.execute("INSERT INTO message VALUES(?, ?, ?, ?, ?)", (
            obj.qq_unique_id,
            obj.qq_msg_id,
            obj.tg_bot_id,
            obj.tg_forum_topic_id,
            obj.tg_msg_id
        ))
        self.con.commit()

    def insert_forum_topic(self, obj: ForumTopic):
        self.con.execute("INSERT INTO forum_topic VALUES(?, ?)", (
            obj.qq_unique_id,
            obj.tg_forum_topic_id
        ))

    def select_qq_unique_id(self, tg_forum_topic_id: int) -> int:
        cur = self.con.execute("SELECT qq_unique_id FROM forum_topic WHERE tg_forum_topic_id = ?", 
                               (tg_forum_topic_id, ))
        row = cur.fetchone()
        if not row:
            return None
        return row[0]

    def select_tg_forum_topic_id(self, qq_unique_id: int) -> int:
        cur = self.con.execute("SELECT tg_forum_topic_id FROM forum_topic WHERE qq_unique_id = ?", 
                               (qq_unique_id, ))
        row = cur.fetchone()
        if not row:
            return None
        return row[0]

    def select_message_where_qq(self, qq_unique_id: int, qq_msg_id: int) -> Message:
        cur = self.con.execute("SELECT * FROM message WHERE qq_unique_id = ? AND qq_msg_id = ?", 
                               (qq_unique_id, qq_msg_id))
        row = cur.fetchone()
        if not row:
            return None
        return Message(*row)

    def select_message_where_tg(self, tg_forum_topic_id: int, tg_msg_id: int) -> Message:
        cur = self.con.execute("SELECT * FROM message WHERE tg_forum_topic_id = ? AND tg_msg_id = ?", 
                               (tg_forum_topic_id, tg_msg_id))
        row = cur.fetchone()
        if not row:
            return None
        return Message(*row)
