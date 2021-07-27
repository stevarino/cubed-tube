# gunicorn wrapper

import logging
from hermit_tube.backend.server import app

if __name__ == '__main__':
    app.run()
