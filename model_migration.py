import peewee as pw
from playhouse import migrate
from playhouse import reflection

def run(db: pw.SqliteDatabase):
    while True:
        models = reflection.generate_models(db)
        if 'last_scanned' not in models['channel']._meta.fields:
            add_channel_counts_update(db)
            continue
        if 'tag' not in models['channel']._meta.fields:
            add_channel_tag_update(db)
            continue
        break

def add_channel_counts_update(db):
    print('Adding last_scanned and count fields to channel...')
    migrator = migrate.SqliteMigrator(db)
    count_field = pw.IntegerField(null=True)

    migrate.migrate(
        migrator.add_column('channel', 'last_scanned', count_field),
        migrator.add_column('channel', 'subscriber_count', count_field),
        migrator.add_column('channel', 'video_count', count_field),
        migrator.add_column('channel', 'view_count', count_field),
    )
    
def add_channel_tag_update(db):
    print('Adding tag field to channel...')
    migrator = migrate.SqliteMigrator(db)

    migrate.migrate(
        migrator.add_column('channel', 'tag', pw.CharField(null=True)),
    )
    