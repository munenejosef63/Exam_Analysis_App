import logging
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from logging.handlers import RotatingFileHandler

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()

# Store file handlers for cleanup
file_handlers = []


def create_app(config_class=None):
    """Application factory function"""
    app = Flask(__name__)

    # Configure application
    configure_app(app, config_class)

    # Initialize extensions
    initialize_extensions(app)

    # Configure logging
    configure_logging(app)

    # Register blueprints
    register_blueprints(app)

    # Register error handlers
    register_error_handlers(app)

    # Setup cleanup when app context is torn down
    @app.teardown_appcontext
    def cleanup_logging(exception=None):
        """Clean up logging handlers when application context is torn down"""
        global file_handlers
        for handler in file_handlers:
            try:
                handler.close()
                app.logger.removeHandler(handler)
            except Exception as e:
                if app.debug:
                    print(f"Error cleaning up handler: {str(e)}")
        file_handlers = []

    return app


def configure_app(app, config_class):
    """Handle application configuration"""
    # Default configuration
    app.config.from_mapping(
        SECRET_KEY=os.getenv('SECRET_KEY', 'dev-secret-key'),
        SQLALCHEMY_DATABASE_URI=os.getenv(
            'DATABASE_URL',
            'postgresql://postgres@localhost/exam_analysis'
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={
            'pool_pre_ping': True,
            'pool_recycle': 300,
        }
    )

    # Load additional configuration if provided
    if config_class:
        app.config.from_object(config_class)


def initialize_extensions(app):
    """Initialize Flask extensions"""
    # Database
    db.init_app(app)

    # Login Manager
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'
    login_manager.session_protection = "strong"

    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        try:
            return User.query.get(int(user_id))
        except Exception as e:
            app.logger.error(f"Error loading user {user_id}: {str(e)}")
            return None

    # Migrations
    migrate.init_app(app, db)


def configure_logging(app):
    """Configure application logging"""
    global file_handlers

    if app.debug:
        # Detailed debug logging during development
        logging.basicConfig(level=logging.DEBUG)
        app.logger.setLevel(logging.DEBUG)
    else:
        # Production logging configuration
        if not os.path.exists('logs'):
            os.mkdir('logs')

        file_handler = RotatingFileHandler(
            'logs/exam_analysis.log',
            maxBytes=10240 * 10,  # 100KB
            backupCount=10,
            encoding='utf-8',
            delay=True  # Delay file opening until first log
        )
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s '
            '[in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)

        # Add to global list for cleanup
        file_handlers.append(file_handler)

        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info('Exam Analysis application startup')


def register_blueprints(app):
    """Register Flask blueprints"""
    from app.views.auth import auth_bp
    from app.views.dashboard import dashboard_bp
    from app.views.upload import upload_bp
    from app.views.payment import payment_bp

    # Main application blueprints
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(upload_bp, url_prefix='/upload')
    app.register_blueprint(payment_bp, url_prefix='/payment')


def register_error_handlers(app):
    """Register global error handlers"""
    from flask import render_template

    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/403.html'), 403

    @app.errorhandler(500)
    def internal_server_error(e):
        app.logger.error(f"500 Error: {str(e)}")
        return render_template('errors/500.html'), 500

    @app.errorhandler(Exception)
    def handle_unexpected_error(e):
        app.logger.error(f"Unexpected error: {str(e)}")
        return render_template('errors/500.html'), 500


# Import models at the end to avoid circular imports
from app import models