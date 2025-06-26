from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from app.models import User, School
from app.forms import LoginForm, RegistrationForm
from app import db
import datetime
from urllib.parse import urlparse, urljoin

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


def log_activity(message, level='info'):
    """Helper function for logging authentication activities"""
    log_msg = f"[AUTH] {datetime.datetime.utcnow()} - {message}"
    if level == 'error':
        current_app.logger.error(log_msg)
    elif level == 'warning':
        current_app.logger.warning(log_msg)
    else:
        current_app.logger.info(log_msg)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user authentication and session creation"""
    if current_user.is_authenticated:
        log_activity(f"User {current_user.id} already authenticated")
        return redirect_to_role_dashboard(current_user.role)

    form = LoginForm()

    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()

        if not user:
            log_activity(f"Failed login attempt for unknown email: {form.email.data}", "warning")
            flash('Invalid email or password', 'danger')
            return render_template('login.html', form=form)

        if not check_password_hash(user.password_hash, form.password.data):
            user.failed_login_attempts += 1
            user.last_failed_login = datetime.datetime.utcnow()
            db.session.commit()

            log_activity(f"Failed login for user {user.id} (attempt {user.failed_login_attempts})", "warning")
            flash('Invalid email or password', 'danger')
            return render_template('login.html', form=form)

        # Successful authentication
        login_user(user, remember=form.remember_me.data)
        user.last_login = datetime.datetime.utcnow()
        user.failed_login_attempts = 0
        db.session.commit()

        log_activity(f"User {user.id} logged in successfully")
        next_page = request.args.get('next')

        if next_page and not is_safe_url(next_page):
            return current_app.login_manager.unauthorized()

        return redirect(next_page) if next_page else redirect_to_role_dashboard(user.role)

    return render_template('login.html', form=form)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Handle new user registration"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))

    form = RegistrationForm()

    if form.validate_on_submit():
        try:
            school = School.query.filter_by(name=form.school_name.data).first()
            if not school:
                school = School(
                    name=form.school_name.data,
                    location=form.school_location.data,
                    is_active=False
                )
                db.session.add(school)
                db.session.flush()

            user = User(
                username=form.username.data,
                email=form.email.data.lower().strip(),
                role=form.role.data,
                school_id=school.id,
                is_active=True
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()

            log_activity(f"New registration: {user.email} ({user.role})")
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('auth.login'))

        except Exception as e:
            db.session.rollback()
            log_activity(f"Registration error: {str(e)}", "error")
            flash('Registration failed. Please try again.', 'danger')

    return render_template('register.html', form=form)


@auth_bp.route('/logout')
@login_required
def logout():
    """Terminate user session"""
    user_id = current_user.id
    logout_user()
    log_activity(f"User {user_id} logged out")
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


def redirect_to_role_dashboard(role):
    """Determine the proper dashboard for each user role"""
    role_handlers = {
        'school_admin': 'dashboard.school_dashboard',
        'teacher': 'dashboard.teacher_dashboard',
        'parent': 'dashboard.parent_dashboard',
        'admin': 'dashboard.admin_dashboard'
    }

    if role not in role_handlers:
        log_activity(f"Invalid role access attempt: {role}", "warning")
        flash('Access denied. Please contact support.', 'danger')
        return redirect(url_for('auth.login'))

    return redirect(url_for(role_handlers[role]))


def is_safe_url(target):
    """Validate redirect URLs to prevent open redirects"""
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and \
        ref_url.netloc == test_url.netloc