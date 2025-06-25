# app/__init__.py
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
import os
from logging.handlers import RotatingFileHandler

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()


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

    return app


def configure_app(app, config_class):
    """Handle application configuration"""
    # Default configuration
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
        'DATABASE_URL',
        'postgresql://postgres@localhost/exam_analysis'
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Load additional configuration if provided
    if config_class:
        app.config.from_object(config_class)


def initialize_extensions(app):
    """Initialize Flask extensions"""
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'


def configure_logging(app):
    """Configure application logging"""
    if not app.debug and not app.testing:
        # Ensure logs directory exists
        if not os.path.exists('logs'):
            os.mkdir('logs')

        # Create rotating file handler
        file_handler = RotatingFileHandler(
            'logs/exam_analysis.log',
            maxBytes=10240,
            backupCount=10
        )
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s '
            '[in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)

        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info('Exam Analysis startup')


def register_blueprints(app):
    """Register Flask blueprints"""
    from app.views.auth import auth_bp
    from app.views.dashboard import dashboard_bp
    from app.views.upload import upload_bp
    from app.views.payment import payment_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(payment_bp)