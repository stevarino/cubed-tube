# gunicorn wrapper

import logging
from hermit_tube.lib.wsgi.server import app

if __name__ == '__main__':
    app.run()
else:
    # running in gunicorn context
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
