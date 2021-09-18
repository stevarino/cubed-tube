
import json
import logging
import os
import os.path
from re import MULTILINE
import time
from urllib.parse import urlparse
import yaml

from flask import (
    Flask, url_for, session, redirect, request, jsonify, g, Response)
from flask.logging import default_handler

from authlib.integrations.flask_client import OAuth

from prometheus_client import (
    Histogram, multiprocess, generate_latest, CollectorRegistry, CONTENT_TYPE_LATEST,
    Gauge, Counter, Histogram)

from cubed_tube.actions import actions
from cubed_tube.backend import user_state
from cubed_tube.lib import util
from cubed_tube.backend import user_state

flask_config = {
    'SEND_FILE_MAX_AGE_DEFAULT': 0
}
config = util.load_config()
creds = util.load_credentials()
flask_config.update(creds.backend.as_dict())

# init CTR_VIDEO_PLAY at 0
channels_by_season = []
for series in config.series:
    for channel in series.get_channels():
        channels_by_season.append((channel, series.slug))


CTR_REQUESTS = Counter(
    'ht_requests', 'Number of requests to site',
    labelnames=['path', 'method', 'status'])
HIST_REQUESTS = Histogram(
    'ht_latency', 'Latency of requests',
    labelnames=['path', 'method'])
CTR_VIDEO_PLAY = util.make_counter(
    'ht_video_play', 'Videos played by channel/series',
    labelnames=['channel', 'series'],
    labelshape=channels_by_season)
CTR_USER_STATUS = Counter(
    'ht_user_status', 'Count of users by status',
    labelnames=['status', 'is_mobile', 'is_logged_in'])


app = Flask(__name__)
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

MULTIPROCESS = bool(os.getenv('PROMETHEUS_MULTIPROC_DIR'))


@app.before_first_request
def before_first_request():
    options = [
        ['Multiprocess', MULTIPROCESS],
        ['Memcache', creds.backend.memcache.host],
        ['Deffered writes', creds.backend.memcache.writes_enabled()],
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
    if  request.path != '/metrics':
        HIST_REQUESTS.labels(
            path=request.path,
            method=request.method,
        ).observe(diff)
        CTR_REQUESTS.labels(
            path=request.path,
            method=request.method,
            status=response.status_code,
        ).inc()

    # CORS code
    domain = _get_domain(request.referrer)
    if not domain:
        domain = flask_config['cors_origins'][0]
    if domain not in flask_config['cors_origins']:
        app.logger.error(f'Unrecognized referrer: "{domain}"')
        domain = flask_config['cors_origins'][0]
    response.headers['Access-Control-Allow-Origin'] = domain
    response.headers['Vary'] = 'Origin'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    return response


def _json(data):
    """
    Returns a json response object with 200 status code, useful as browsers consider 4xx
    codes failurs and log them to the console. :-(
    """
    return jsonify(data), 200

def _get_domain(referrer):
    if not referrer:
        return ''
    try:
        parts = urlparse(util.ensure_str(referrer))
        return f'{parts.scheme}://{parts.netloc}'
    except:
        return ''


@app.route('/')
def homepage():
    """
    Unsure what to do here, bounce them to the frontend?
    """
    return redirect(flask_config['cors_origins'][0], code=302)


@app.route("/metrics")
def metrics():
    """
    Metric collection. Used by Prometheus to gether metrics for all replicas.
    """
    if MULTIPROCESS:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        data = generate_latest(registry)
    else:
        data = generate_latest()
    return Response(data, mimetype=CONTENT_TYPE_LATEST)


@app.route('/login')
def login():
    """
    Send user to Google with OAuth request. Initiates user login flow.
    """
    session.pop('redirect', None)
    if request.args.get('r'):
        session['redirect'] = request.args.get('r')
    return oauth.google.authorize_redirect(url_for('auth', _external=True))


@app.route('/auth')
def auth():
    """
    Handle user returning from Google with OAuth token. Finalizes login flow.
    """
    token = oauth.google.authorize_access_token()
    user = oauth.google.parse_id_token(token)
    user_hash = util.sha1(creds.backend.user_salt + user['email'])
    session['user_hash'] = user_hash
    app.logger.info(f"User {user_hash} logged in")
    return redirect(session.pop('redirect', None) or '/')


@app.route('/logout')
def logout():
    """
    Delete the user token from sessions.
    """
    user_hash = session.pop('user_hash', None)
    if user_hash is not None:
        app.logger.info(f"User {user_hash} logged out")
    return redirect(request.args.get('r') or '/')


@app.route('/app//play_count')
def play_count():
    """
    Gather play data on channel/series (not per video).

    Useful for creator feedback and justification of site value.
    """
    CTR_VIDEO_PLAY.labels(
        channel=request.args.get('channel'),
        series=request.args.get('series'),
    ).inc()
    return _json({'ok': True})


@app.route('/app/user_poll')
def user_status():
    """
    Gather user load info (on site, watching video, on mobile or not).

    Useful for estimating site load, forcasting resource needs, and
    justifying my own time on this project. :-)
    """
    CTR_USER_STATUS.labels(
        status=request.args.get('status'),
        is_mobile=request.args.get('is_mobile'),
        is_logged_in=request.args.get('is_mobile'),
    ).inc()
    return _json({'ok': True})


@app.route('/app/user_state', methods = ['POST', 'GET'])
def handle_user_state():
    """
    Get/Set user state.
    
    The main funciton of the backend which ties into the user_state module.
    """
    return_value = {}
    user_hash = session.get('user_hash')
        
    if not user_hash:
        return _json({'error': 'unauthenticated'})

    creds = util.load_credentials(ttl=30)
    # POST - Uploading state
    if request.method == 'POST':
        upload_data = request.get_json(force=True)
        merged_data = user_state.write_user(user_hash, upload_data)
        return_value['state'] = merged_data
    else:  # GET - Retrieving state
        try:
            return_value['state'] = user_state.lookup_user(user_hash)
        except user_state.UserNotFound:
            return_value['error'] = 'unknown'
    if creds.roles.is_known(user_hash):
        return_value['has_roles'] = 1
    return _json(return_value)


@app.route('/app/actions', methods=['GET'])
def get_user_actions():
    user_hash = session.get('user_hash')
    if not user_hash:
        return _json({'error': 'unauthenticated'})
    
    return _json({'actions': [
        a.as_dict() for a in actions.get_user_actions(user_hash) if a.listed
    ]})


@app.route('/app/request_action', methods=['POST'])
def request_action():
    user_hash = session.get('user_hash')
    if not user_hash:
        return _json({'error': 'unauthenticated'})

    action = request.args.get('action')
    if not action:
        return _json({'error': 'unknown format'})
    params = request.get_json(force=True)
    try:
        record = actions.enqueue_action_request(user_hash, action, params)
    except ValueError as e:
        return _json({'error': str(e)})
    return _json({'record': record.as_dict()})


@app.route('/app/action_status', methods=['GET'])
def action_status():
    user_hash = session.get('user_hash')
    if not user_hash:
        return _json({'error': 'unauthenticated'})

    action_id = request.args.get('id')
    since_time = float(request.args.get('t', '0'))
    if not action_id:
        return _json({'error': 'unknown format'})
    
    if not actions.find_action_record(user_hash, action_id):
        return _json({'error': 'action not found'})

    log = actions.cache.ActionLogger(action_id).queue.get()

    records = []
    if since_time == 0:
        records = [json.loads(l) for l in log]
    else:
        for record in reversed(log):
            record = json.loads(record)
            if record['time'] <= since_time:
                break
            records.append(record)
        records.reverse()
    return _json({'records': records})


if __name__ == '__main__':
    app.run(debug=True)
