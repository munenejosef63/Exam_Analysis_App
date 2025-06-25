# app/views/dashboard.py
from flask import Blueprint, render_template, flash, redirect, url_for
from flask_login import login_required, current_user
from app.services.analysis import get_school_performance, get_student_performance
from app.views.models import Exam, School, Payment

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@login_required
def dashboard():
    if current_user.role == 'school_admin':
        return redirect(url_for('dashboard.school_dashboard'))
    elif current_user.role == 'teacher':
        return redirect(url_for('dashboard.teacher_dashboard'))
    elif current_user.role == 'parent':
        return redirect(url_for('dashboard.parent_dashboard'))
    else:
        return redirect(url_for('dashboard.admin_dashboard'))


@dashboard_bp.route('/admin')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('dashboard.dashboard'))

    schools = School.query.all()
    payments = Payment.query.order_by(Payment.payment_date.desc()).limit(10).all()

    return render_template('dashboard_admin.html', schools=schools, payments=payments)


@dashboard_bp.route('/school')
@login_required
def school_dashboard():
    if current_user.role != 'school_admin':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('dashboard.dashboard'))

    school = current_user.school
    exams = Exam.query.filter_by(school_id=school.id).order_by(Exam.exam_date.desc()).limit(5).all()
    performance = get_school_performance(school.id)

    return render_template('dashboard_school.html',
                           school=school,
                           exams=exams,
                           performance=performance)


@dashboard_bp.route('/teacher')
@login_required
def teacher_dashboard():
    if current_user.role != 'teacher':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('dashboard.dashboard'))

    # Get subjects taught by this teacher (implementation depends on your model)
    # For now, we'll show all subjects in the teacher's school
    school = current_user.school
    subjects = Subject.query.join(Class).filter(Class.school_id == school.id).all()

    return render_template('dashboard_teacher.html',
                           school=school,
                           subjects=subjects)


@dashboard_bp.route('/parent')
@login_required
def parent_dashboard():
    if current_user.role != 'parent':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('dashboard.dashboard'))

    students = current_user.students
    student_performances = {}

    for student in students:
        student_performances[student.id] = get_student_performance(student.id)

    return render_template('dashboard_parent.html',
                           students=students,
                           performances=student_performances)