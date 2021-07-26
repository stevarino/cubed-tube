
import logging
import os
import os.path
from re import MULTILINE
import time
from urllib.parse import urlparse
import yaml

from flask import (
    Flask, url_for, session, redirect, render_template, request,
    send_from_directory, jsonify, g, Response)
from flask.logging import default_handler

from authlib.integrations.flask_client import OAuth

from prometheus_client import (
    Histogram, multiprocess, generate_latest, CollectorRegistry, CONTENT_TYPE_LATEST,
    Gauge, Counter, Histogram)

from hermit_tube.lib.common import generate_template_context
from hermit_tube.lib.util import root, sha1
from hermit_tube.lib.wsgi import user_state

path = os.path.abspath(__file__)
while 'lib' in path:
    path = os.path.dirname(path)

with open(root('credentials.yaml'), 'r') as fp:
    creds = yaml.safe_load(fp)
with open(root('playlists.yaml'), 'r') as fp:
    config = yaml.safe_load(fp)

flask_config = {
    'SEND_FILE_MAX_AGE_DEFAULT': 0
}
flask_config.update(creds['wsgi'])


CTR_REQUESTS = Counter('ht_requests', 'Number of requests to site',
                       labelnames=['path', 'method', 'status'])
HIST_REQUESTS = Histogram('ht_latency', 'Latency of requests',
                          labelnames=['path', 'method'])
CTR_VIDEO_PLAY = Counter('ht_video_play', 'Videos played by channel/series',
                         labelnames=['channel', 'series'])

app = Flask(
    __name__, 
    template_folder='../../templates',
    static_url_path='')
app.config.update(flask_config)


loggers = [
    app.logger,
    logging.getLogger(user_state.__name__),
]
for logger in loggers:
    logger.addHandler(default_handler)
    logger.setLevel(logging.INFO)

CONF_URL = 'https://accounts.google.com/.well-known/openid-configuration'
oauth = OAuth(app)
oauth.register(
    name='google',
    server_metadata_url=CONF_URL,
    client_kwargs={
        'scope': 'openid email'
    }
)

STATIC_DIR = os.path.join(path, 'templates/static').replace('\\', '/')
MULTIPROCESS = bool(os.getenv('PROMETHEUS_MULTIPROC_DIR'))

@app.before_first_request
def before_first_request():
    options = [
        ['Multiprocess', MULTIPROCESS],
        ['Memcache', os.getenv('memcache')],
        ['Deffered writes', os.getenv('deferred_writes')],
    ]
    for mode, status in options:
        app.logger.info('%s mode %sabled', mode, ('en' if status else 'dis'))



@app.before_request
def before_request():
    g.start = time.time()


@app.after_request
def after_request(response: Response):
    diff = time.time() - g.start
    if response.response and 200 <= response.status_code < 300:
        response.headers["X-ServerTiming"] = str(diff)
    HIST_REQUESTS.labels(
        path=request.path,
        method=request.method,
    ).observe(diff)
    CTR_REQUESTS.labels(
        path=request.path,
        method=request.method,
        status=response.status_code,
    ).inc()
    return response


def _allow_cors(func):
    def _wrapper(*args, **kwargs):
        res, code = func(*args, **kwargs)
        domain = _get_domain(request.referrer)
        if not domain:
            domain = flask_config['CORS_ORIGINS'][0]
        if domain not in flask_config['CORS_ORIGINS']:
            app.logger.error(f'Unrecognized referrer: "{domain}"')
            domain = flask_config['CORS_ORIGINS'][0]
        res.headers['Access-Control-Allow-Origin'] = domain
        res.headers['Vary'] = 'Origin'
        res.headers['Access-Control-Allow-Credentials'] = 'true'
        return res, code
    return _wrapper


def _json(data):
    """
    Returns a json response object with 200 status code, useful as browsers consider 4xx
    codes failurs and log them to the console. :-(
    """
    return jsonify(data), 200

def _get_domain(referrer):
    try:
        parts = urlparse(referrer)
        return f'{parts.scheme}://{parts.netloc}'
    except:
        return ''


@app.route('/')
def homepage():
    user = session.get('user_hash')
    context = generate_template_context(config)
    return render_template('wsgi/wsgi.html', user=user, **context)

@app.route("/metrics")
def metrics():
    if MULTIPROCESS:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        data = generate_latest(registry)
    else:
        data = generate_latest()
    return Response(data, mimetype=CONTENT_TYPE_LATEST)


@app.route('/login')
def login():
    session.pop('redirect', None)
    if request.args.get('r'):
        session['redirect'] = request.args.get('r')
    return oauth.google.authorize_redirect(url_for('auth', _external=True))


@app.route('/auth')
def auth():
    token = oauth.google.authorize_access_token()
    user = oauth.google.parse_id_token(token)
    user_hash = sha1(creds['salt'] + user['email'])
    session['user_hash'] = user_hash
    app.logger.info(f"User {user_hash} logged in")
    return redirect(session.pop('redirect', None) or '/')


@app.route('/logout')
def logout():
    user_hash = session.pop('user_hash', None)
    if user_hash is not None:
        app.logger.info(f"User {user_hash} logged out")
    return redirect(request.args.get('r') or '/')


@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory(STATIC_DIR, path)


@app.route('/play_count')
def play_count():
    CTR_VIDEO_PLAY.labels(
        channel=request.args.get('channel'),
        series=request.args.get('series'),
    )


@app.route('/_status')
def status():
    # NOTE: This is being left unauthenticated (for now) as this project is
    # just as much about being a learning resource as anything else.
    cache = user_state.get_user_cache()
    cache_data = {
        'size': len(cache.cache),
        'hits': cache.hits,
        'misses': cache.misses,
    }
    return _json({
        'cache': cache_data
    })

@app.route('/app/user_state', methods = ['POST', 'GET'])
@_allow_cors
def handle_user_state():
    return_value = {}
    user_hash = session.get('user_hash')
        
    if not user_hash:
        return _json({'error': 'unauthenticated'})

    # POST - Uploading state
    if request.method == 'POST':
        upload_data = request.get_json(force=True)
        merged_data = user_state.write_user(user_hash, upload_data)
        return_value['state'] = merged_data
    else:  # GET - Retrieving state
        try:
            return_value['state'] = user_state.lookup_user(user_hash)
        except user_state.UserNotFound:
            return _json({'error': 'unknown'})
    return _json(return_value)

if __name__ == '__main__':
    app.run(debug=True)
