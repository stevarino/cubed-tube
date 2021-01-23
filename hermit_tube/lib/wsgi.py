
import os.path
import sys
import yaml

from flask import (
    Flask, url_for, session, render_template, redirect, send_from_directory)
from authlib.integrations.flask_client import OAuth

from hermit_tube.lib.common import generate_template_context
from hermit_tube.lib.util import root

path = os.path.abspath(__file__)
while 'lib' in path:
    path = os.path.dirname(path)

with open(root('credentials.yaml'), 'r') as fp:
    creds = yaml.safe_load(fp)
with open(root('playlists.yaml'), 'r') as fp:
    config = yaml.safe_load(fp)

app = Flask(
    __name__, 
    template_folder='../templates',
    static_url_path='')
app.config.update(creds['wsgi'])

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

@app.after_request
def add_header(req):
    """
    Add headers to both force latest IE rendering engine or Chrome Frame,
    and also to cache the rendered page for 10 minutes.
    """
    req.headers["Pragma"] = "no-cache"
    req.headers["Expires"] = "0"
    req.headers['Cache-Control'] = 'public, max-age=0'
    return r

@app.route('/')
def homepage():
    user = session.get('user')
    context = generate_template_context(config)
    return render_template('wsgi/wsgi.html', user=user, **context)


@app.route('/login')
def login():
    redirect_uri = url_for('auth', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@app.route('/auth')
def auth():
    token = oauth.google.authorize_access_token()
    user = oauth.google.parse_id_token(token)
    session['user'] = user
    return redirect('/')


@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')

@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory(STATIC_DIR, path)


if __name__ == '__main__':
    app.run(debug=True)
