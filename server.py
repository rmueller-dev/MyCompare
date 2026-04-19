"""Entry point for PyInstaller-bundled Flask backend."""
import argparse
import os
import sys


def main():
    parser = argparse.ArgumentParser(description='MyCompare Backend Server')
    parser.add_argument('--port', type=int, default=5000)
    args = parser.parse_args()

    data_dir = os.environ.get('MYCOMPARE_DATA_DIR', '.')
    os.makedirs(os.path.join(data_dir, 'storage'), exist_ok=True)

    from app.main import create_app
    flask_app = create_app()
    flask_app.run(
        host='127.0.0.1',
        port=args.port,
        threaded=True,
        debug=False,
        use_reloader=False,
    )


if __name__ == '__main__':
    main()
