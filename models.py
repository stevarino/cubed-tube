import model_migration

import datetime
import os
import os.path
from typing import Dict

import peewee as pw

FILENAME = 'db.sqlite3'

os.chdir(os.path.dirname(os.path.abspath(__file__)))
new_db = not os.path.exists(FILENAME)
db = pw.SqliteDatabase(FILENAME)
if not new_db:
    model_migration.run(db)

class BaseModel(pw.Model):
    class Meta:
        database = db

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
    # Minecraft gamer tag from wiki, because vintagebeef is an unrecognizable
    # Sian Dent and tfc is "TinfoilChef's Gaming Channel". creatives... ;-)
    tag = pw.IntegerField(null=True)

class Series(BaseModel):
    slug = pw.CharField(primary_key=True, unique=True)
    title = pw.CharField()

class Playlist(BaseModel):
    playlist_id = pw.CharField(primary_key=True, unique=True)
    playlist_type = pw.CharField(default='youtube_pl')
    key = pw.CharField(null=True)
    channel = pw.ForeignKeyField(Channel, backref='playlists')

class Video(BaseModel):
    video_type = pw.CharField(default='youtube')
    video_id = pw.CharField()
    playlist = pw.ForeignKeyField(Playlist, backref='videos')
    series = pw.ForeignKeyField(Series, backref='videos')

    title = pw.CharField(null=True)
    published_at = pw.IntegerField(null=True)
    playlist_at = pw.IntegerField(null=True)
    position = pw.IntegerField(null=True)
    description = pw.CharField(null=True)
    thumbnails = pw.CharField(null=True)

    class Meta:
        indexes = (
            (('video_type', 'video_id'), True),
        )

db.create_tables([Channel, Series, Playlist, Video])
