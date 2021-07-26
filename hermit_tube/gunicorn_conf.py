import os
import shutil

workers = 5

raw_env = [
    'PROMETHEUS_MULTIPROC_DIR=./prometheus_multiproc',
    'memcache=localhost:11211',
]

bind = 'unix:hermit-tube.socket'

accesslog = '/var/www/hermit.tube/logs/access.log'
errorlog = '/var/www/hermit.tube/logs/error.log'
loglevel = 'info'
enable_stdio_inheritance = True

def post_fork(server, worker):
    server.log.info("Worker spawned (pid: %s)", worker.pid)
    
def on_starting(server):
    server.log.info("on_starting")
    shutil.rmtree('./prometheus_multiproc')
    os.mkdir('./prometheus_multiproc')

def when_ready(server):
    server.log.info("server ready")

def pre_fork(server, worker):
    worker.log.info("pre_fork")

def pre_exec(server):
    server.log.info("Forked child, re-executing.")

def when_ready(server):
    server.log.info("Server is ready. Spawning workers")

def worker_int(worker):
    worker.log.info("worker received INT or QUIT signal")

def worker_exit(server, worker):
    from prometheus_client import multiprocess
    multiprocess.mark_process_dead(worker.pid)
