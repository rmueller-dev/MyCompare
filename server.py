#!/usr/bin/env python3
"""PyInstaller entry point for MyCompare backend."""
import sys
import os
import argparse


def main():
    parser = argparse.ArgumentParser(description='MyCompare Backend')
    parser.add_argument('--port', type=int, default=5000)
    parser.add_argument('--host', default='127.0.0.1')
    args = parser.parse_args()

    # User data directory — writable even inside a .app bundle
    data_dir = os.path.expanduser('~/Library/Application Support/mycompare')
    os.makedirs(data_dir, exist_ok=True)
    os.environ['MYCOMPARE_DATA_DIR'] = data_dir

    # When frozen by PyInstaller, _MEIPASS contains extracted modules
    if getattr(sys, 'frozen', False):
        sys.path.insert(0, sys._MEIPASS)

    from app.main import create_app
    flask_app = create_app()
    flask_app.run(
        host=args.host,
        port=args.port,
        debug=False,
        threaded=True,
        use_reloader=False,
    )


if __name__ == '__main__':
    main()
