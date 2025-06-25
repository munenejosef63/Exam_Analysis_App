# app/views/auth.py
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.views.models import User, School
from app.views.forms import LoginForm, RegistrationForm
from app import db

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember_me.data)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard.dashboard'))
        flash('Invalid email or password', 'danger')
    return render_template('login.html', form=form)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))

    form = RegistrationForm()
    if form.validate_on_submit():
        # Check if school exists or create new
        school = School.query.filter_by(name=form.school_name.data).first()
        if not school:
            school = School(name=form.school_name.data, location=form.school_location.data)
            db.session.add(school)
            db.session.commit()

        # Create user
        user = User(
            username=form.username.data,
            email=form.email.data,
            role=form.role.data,
            school_id=school.id
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()

        flash('Account created successfully!', 'success')
        return redirect(url_for('auth.login'))

    return render_template('register.html', form=form)


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))