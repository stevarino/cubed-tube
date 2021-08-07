from cubed_tube.lib import model_migration, util

import datetime
import os
import os.path
from typing import Dict

import peewee as pw

FILENAME = 'db.sqlite3'

db = pw.SqliteDatabase(None)

class BaseModel(pw.Model):
    class Meta:
        database = db

class Misc(BaseModel):
    key = pw.CharField(primary_key=True, unique=True)
    value = pw.CharField(null=True)

class Channel(BaseModel):
    name = pw.CharField(primary_key=True, unique=True)
    title = pw.CharField(null=True)
    channel_type = pw.CharField(default='youtube')
    channel_id = pw.CharField(null=True)
    description = pw.CharField(null=True)
    custom_url = pw.CharField(null=True)
    thumbnails = pw.CharField(null=True)
    last_scanned = pw.IntegerField(null=True)
    subscriber_count = pw.IntegerField(null=True)
    video_count = pw.IntegerField(null=True)
    view_count = pw.IntegerField(null=True)
    # Canonical name for use on site (from playlists.yaml)
    tag = pw.IntegerField(null=True)
    id = pw.IntegerField(null=True)

class Series(BaseModel):
    slug = pw.CharField(primary_key=True, unique=True)
    title = pw.CharField()

class Playlist(BaseModel):
    playlist_id = pw.CharField(primary_key=True, unique=True)
    playlist_type = pw.CharField(default='youtube_pl')
    key = pw.CharField(null=True)
    channel = pw.ForeignKeyField(Channel, backref='playlists')
    etag = pw.CharField(null=True)

class Video(BaseModel):
    video_type = pw.CharField(default='youtube')
    video_id = pw.CharField()
    series = pw.ForeignKeyField(Series, backref='videos')

    title = pw.CharField(null=True)
    published_at = pw.IntegerField(null=True)
    playlist_at = pw.IntegerField(null=True)
    position = pw.IntegerField(null=True)
    description = pw.CharField(null=True)
    thumbnails = pw.CharField(null=True)
    length = pw.IntegerField(null=True)
    last_scanned = pw.IntegerField(null=True)
    captions = pw.CharField(null=True)
    tombstone = pw.IntegerField(null=True)
    channel = pw.CharField(null=True)

    class Meta:
        indexes = (
            (('video_type', 'video_id'), True),
        )

# class Statistic(BaseModel):
#     statistic_id = pw.AutoField()
#     video = pw.ForeignKeyField(Video, backref='statistics')
#     timestamp = pw.IntegerField(null=True)
#     views = pw.IntegerField(null=True)
#     likes = pw.IntegerField(null=True)
#     dislikes = pw.IntegerField(null=True)
#     favorites = pw.IntegerField(null=True)
#     comments = pw.IntegerField(null=True)

class TrendPoint(BaseModel):
    point_id = pw.AutoField()
    timestamp = pw.IntegerField()
    value = pw.IntegerField()
    series_id = pw.IntegerField(index=True)

    def __str__(self):
        return (f'{self.point_id}@{self.series_id} '
                f'({self.timestamp}, {self.value})')

class TrendSeries(BaseModel):
    series_id = pw.AutoField()
    pivot = pw.ForeignKeyField(TrendPoint, null=True)
    current = pw.ForeignKeyField(TrendPoint, null=True)
    delta = pw.FloatField(default=1)
    upper = pw.FloatField(null=True)
    lower = pw.FloatField(null=True)
    # uncompressed sample size
    raw_count = pw.IntegerField(default=0)
    # stored sample size after compression
    point_count = pw.IntegerField(default=0)

    def __str__(self):
        return f'{self.series_id} {self.upper} / {self.lower}'

class VideoTrends(BaseModel):
    video_trend_id = pw.AutoField()
    video_id = pw.ForeignKeyField(Video, unique=True, backref='trends')
    views = pw.ForeignKeyField(TrendSeries, null=True)
    likes = pw.ForeignKeyField(TrendSeries, null=True)
    dislikes = pw.ForeignKeyField(TrendSeries, null=True)
    favorites = pw.ForeignKeyField(TrendSeries, null=True)
    comments = pw.ForeignKeyField(TrendSeries, null=True)


@db.func('power')
def power(base, exponent):
    """As far as I know, this does not exist"""
    if base is None or exponent is None:
        return None
    return base ** exponent

MODELS = BaseModel.__subclasses__()

def init_database():
    new_db = not os.path.exists(FILENAME)
    print(os.getcwd(), new_db)
    # import sys
    # sys.exit()
    db.init(os.path.join(os.getcwd(), FILENAME),
            pragmas={'journal_mode': 'wal'})
    if not new_db:
        model_migration.run(db)

    db.create_tables(MODELS)
