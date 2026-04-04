"""Flask application entry point."""
import os
from flask import Flask, send_from_directory
from flask_cors import CORS
from .models import init_db
from .routes import api


def create_app():
    app = Flask(__name__, static_folder=None)
    app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100 MB
    CORS(app, origins=['http://localhost:5000', 'http://127.0.0.1:5000', 'http://localhost:5050', 'http://127.0.0.1:5050'])

    # Register API blueprint
    app.register_blueprint(api)

    # Initialize database
    with app.app_context():
        init_db()

    # Serve React frontend
    frontend_dir = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'build')

    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def serve_frontend(path):
        if path and os.path.exists(os.path.join(frontend_dir, path)):
            return send_from_directory(frontend_dir, path)
        return send_from_directory(frontend_dir, 'index.html')

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=False, port=5000, host='127.0.0.1')
