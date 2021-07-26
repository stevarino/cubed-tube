# gunicorn wrapper

import logging
from hermit_tube.lib.wsgi.server import app

if __name__ == '__main__':
    app.run()
