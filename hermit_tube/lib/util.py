import os.path

def root(*paths):
    path = os.path.abspath(__file__).replace('\\', '/')
    while 'hermit_tube/lib' in path:
        path = os.path.dirname(path).replace('\\', '/')
    return os.path.join(path, *paths)
