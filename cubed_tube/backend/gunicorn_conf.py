import os
import shutil

from cubed_tube.lib import util

creds = util.load_credentials()

if not creds.site_name:
    raise ValueError('site_name missing from credentials.yaml')

workers = 5

raw_env = [
    'PROMETHEUS_MULTIPROC_DIR=./prometheus_multiproc',
]

bind = f'unix:{creds.site_name}.socket'

accesslog = f'/var/www/{creds.site_name}/logs/access.log'
errorlog = f'/var/www/{creds.site_name}/logs/error.log'
loglevel = 'info'
enable_stdio_inheritance = True

def post_fork(server, worker):
    server.log.info("Worker spawned (pid: %s)", worker.pid)
    
def on_starting(server):
    server.log.info("on_starting")
    shutil.rmtree('./prometheus_multiproc')
    os.mkdir('./prometheus_multiproc')

def worker_exit(server, worker):
    from prometheus_client import multiprocess
    multiprocess.mark_process_dead(worker.pid)
