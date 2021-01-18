import os.path
import yaml

from flask import Flask, url_for, session
from flask import render_template, redirect
from authlib.integrations.flask_client import OAuth

os.chdir(os.path.dirname(os.path.abspath(__file__)))
with open('credentials.yaml') as fp:
    creds = yaml.safe_load(fp)


templates = os.path.abspath('./lib/wsgi/templates')
app = Flask(__name__, template_folder=templates)
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


@app.route('/')
def homepage():
    user = session.get('user')
    return render_template('home.html', user=user)


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

if __name__ == '__main__':
    app.run(debug=True)
