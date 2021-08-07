
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

from cubed_tube.lib.util import sha1, load_credentials
from cubed_tube.backend import user_state

flask_config = {
    'SEND_FILE_MAX_AGE_DEFAULT': 0
}
creds = load_credentials()
flask_config.update(creds.backend.as_dict())


CTR_REQUESTS = Counter(
    'ht_requests', 'Number of requests to site',
    labelnames=['path', 'method', 'status'])
HIST_REQUESTS = Histogram(
    'ht_latency', 'Latency of requests',
    labelnames=['path', 'method'])
CTR_VIDEO_PLAY = Counter(
    'ht_video_play', 'Videos played by channel/series',
    labelnames=['channel', 'series'])
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
        ['Memcache', creds.backend.memcache],
        ['Deffered writes', creds.backend.memcache and 
                            creds.backend.memcache.write_frequency],
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
    try:
        parts = urlparse(referrer)
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
    user_hash = sha1(creds.backend.user_salt + user['email'])
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
