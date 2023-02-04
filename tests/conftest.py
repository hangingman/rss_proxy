import os
import pathlib
import pytest
from peewee import SqliteDatabase

from feed_extraction import Rss

cwd: pathlib.Path = pathlib.Path(os.path.abspath(__file__))
db_path: str = os.path.join(os.path.dirname(cwd.parent), 'rss_database.db')

@pytest.fixture(scope='session', autouse=True)
def scope_session():
    if os.path.exists(db_path):
        os.remove(db_path)

    db = SqliteDatabase(db_path)
    db.connect()
    db.create_tables([Rss], safe=True)

    # テスト実行
    yield
