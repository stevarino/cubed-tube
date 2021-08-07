
from datetime import datetime, timedelta
import json
import logging
from time import sleep
from typing import Optional
from botocore.parsers import LOG

from prometheus_client import start_http_server, Counter

from cubed_tube.lib import util
from cubed_tube.backend import memcached_client, cloud_storage



CNT_ERRORS = Counter('ht_worker_errors', 'Number of errros')
CNT_UPLOADS = Counter('ht_worker_uploads', 'Number of errros')
DEFERRED_LAST_CHECK: Optional[datetime] = None
LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)

def check_writes(attempt = 0):
    global DEFERRED_LAST_CHECK
    creds = util.load_credentials(ttl=10)
    write_frequency = creds.backend.memcache.write_frequency
    if not write_frequency:
        return
    horizon = timedelta(seconds=write_frequency)
    now = datetime.now()
    if DEFERRED_LAST_CHECK and now - DEFERRED_LAST_CHECK < horizon:
        return
    DEFERRED_LAST_CHECK = now

    keys, cas = memcached_client.get_deferred()
    if not keys:
        return
    if not memcached_client.set_deferred('', cas):
        LOGGER.warning('CAS conflict on check_writes(%s)', attempt)
        return check_writes(attempt + 1)
        
    for chunked_keys in util.chunk(keys, len(keys), 50):
        contents = memcached_client.CLIENT.get_many(chunked_keys)
        missing = set(chunked_keys) - set(contents.keys())
        if missing:
            LOGGER.warning(
                'Missing keys from get_many: %s', json.dumps(list(missing)))
        for key in contents:
            if not contents[key]:
                LOGGER.warning('Missing content for key %s', key)
                continue
            cloud_storage.put_object(key, contents[key])
            CNT_UPLOADS.inc()
        


def loop():
    creds = util.load_credentials()
    start_http_server(3900)
    memcached_client.create_client(creds.backend.memcache)
    LOGGER.info("Worker started")
    while True:
        try:
            check_writes()
        except Exception as e:
            CNT_ERRORS.inc()
            LOGGER.exception('Unhandled error during check_writes')
        sleep(1)


if __name__ == '__main__':
    # Start up the server to expose the metrics.
    loop()
