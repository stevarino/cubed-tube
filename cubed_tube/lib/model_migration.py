import peewee as pw
from playhouse import migrate
from playhouse import reflection

def run(db: pw.SqliteDatabase):
    int_field = pw.IntegerField(null=True)
    char_field = pw.CharField(null=True)

    new_fields = [
        [
            ('channel', 'last_scanned', int_field),
            ('channel', 'subscriber_count', int_field),
            ('channel', 'video_count', int_field),
            ('channel', 'view_count', int_field),
        ],
        [('channel', 'tag', char_field)],
        [('video', 'length', int_field)],
        [('video', 'last_scanned', int_field)],
        [('video', 'captions', char_field)],
        [('video', 'tombstone', int_field)],
        [('playlist', 'etag', char_field)],
        [('video', 'channel', char_field)],
    ]
    for field_set in new_fields:
        table, field, _ = field_set[0]
        models = reflection.generate_models(db)
        if field not in models[table]._meta.fields:
            print(f'Adding {table}.{field}...')
            migrator = migrate.SqliteMigrator(db)
            migrate.migrate(*[migrator.add_column(table, field, field_type)
                              for table, field, field_type in field_set])

    
    # models = reflection.generate_models(db)
    # if 'id' not in models['channel']._meta.fields:
    #     migrator = migrate.SqliteMigrator(db)
    #     migrate.migrate(migrator.add_column('channel', 'id', int_field))
    # db.execute_sql('''
    #     UPDATE channel SET id = (
    #         SELECT rowid FROM channel c2 WHERE c2.name = channel.name
    #     ) WHERE channel.id IS null;
    # ''')
    # db.execute_sql('''
    #     UPDATE video SET channel = (
    #         SELECT p.channel_id from playlist p
    #         WHERE p.playlist_id = video.playlist_id
    #     ) WHERE video.channel is null;
    # ''')

    # migrator = migrate.SqliteMigrator(db)
    # migrate.migrate(migrator.drop_not_null('video', 'playlist_id'))

