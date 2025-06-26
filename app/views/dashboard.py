from flask import Blueprint, render_template, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from app.services.analysis import get_school_performance, get_student_performance
from app.models import Exam, School, Payment, Subject, AcademicClass, User
from app import db
from datetime import datetime, timedelta
from sqlalchemy import func

dashboard_bp = Blueprint('dashboard', __name__)

def get_teacher_subjects(teacher):
    """Helper function to get subjects taught by a teacher with class information"""
    if hasattr(teacher, 'taught_subjects'):
        return teacher.taught_subjects

    return Subject.query.join(AcademicClass) \
        .filter(AcademicClass.school_id == teacher.school_id) \
        .options(db.joinedload(Subject.academic_class)) \
        .all()

def get_upcoming_exams(school_id, days=30):
    """Get upcoming exams within the next specified days"""
    return Exam.query.filter(
        Exam.school_id == school_id,
        Exam.exam_date >= datetime.now(),
        Exam.exam_date <= datetime.now() + timedelta(days=days)
    ).order_by(Exam.exam_date.asc()).all()

def get_recent_activity(school_id):
    """Get recent system activity for a school"""
    recent_exams = Exam.query.filter_by(school_id=school_id) \
        .order_by(Exam.exam_date.desc()) \
        .limit(5).all()

    recent_payments = Payment.query.filter_by(school_id=school_id) \
        .order_by(Payment.payment_date.desc()) \
        .limit(5).all()

    return {
        'exams': recent_exams,
        'payments': recent_payments
    }

@dashboard_bp.route('/')
@login_required
def dashboard():
    """Main dashboard route that redirects to role-specific dashboards"""
    try:
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))

        role_handlers = {
            'school_admin': school_dashboard,
            'teacher': teacher_dashboard,
            'parent': parent_dashboard,
            'admin': admin_dashboard
        }

        handler = role_handlers.get(current_user.role)
        if not handler:
            current_app.logger.warning(f'Unknown role accessed: {current_user.role}')
            flash('Unknown user role', 'warning')
            return redirect(url_for('auth.login'))

        return handler()

    except Exception as e:
        current_app.logger.error(f"Dashboard routing error: {str(e)}", exc_info=True)
        flash('Error loading dashboard', 'danger')
        return redirect(url_for('auth.login'))

@dashboard_bp.route('/admin')
@login_required
def admin_dashboard():
    """Admin dashboard showing system overview"""
    if current_user.role != 'admin':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('dashboard.dashboard'))

    try:
        stats = {
            'total_schools': School.query.count(),
            'active_schools': School.query.filter_by(is_active=True).count(),
            'total_users': User.query.count(),
            'recent_payments': Payment.query \
                .order_by(Payment.payment_date.desc()) \
                .limit(10).all(),
            'revenue_data': db.session.query(
                func.strftime('%Y-%m', Payment.payment_date),
                func.sum(Payment.amount)
            ).group_by(func.strftime('%Y-%m', Payment.payment_date)).all()
        }

        return render_template('dashboard_admin.html', **stats)

    except Exception as e:
        current_app.logger.error(f"Admin dashboard error: {str(e)}", exc_info=True)
        flash('Error loading admin dashboard', 'danger')
        return redirect(url_for('dashboard.dashboard'))

@dashboard_bp.route('/school')
@login_required
def school_dashboard():
    """School administrator dashboard"""
    if current_user.role != 'school_admin':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('dashboard.dashboard'))

    if not current_user.school:
        flash('No school assigned', 'danger')
        return redirect(url_for('dashboard.dashboard'))

    try:
        school = current_user.school
        recent_activity = get_recent_activity(school.id)

        data = {
            'school': school,
            'performance': get_school_performance(school.id),
            'upcoming_exams': get_upcoming_exams(school.id),
            'recent_exams': recent_activity['exams'],
            'recent_payments': recent_activity['payments'],
            'teacher_count': User.query.filter_by(
                school_id=school.id,
                role='teacher'
            ).count(),
            'student_count': User.query.filter_by(
                school_id=school.id,
                role='student'
            ).count()
        }

        return render_template('dashboard_school.html', **data)

    except Exception as e:
        current_app.logger.error(
            f"School dashboard error for school {current_user.school_id}: {str(e)}",
            exc_info=True
        )
        flash('Error loading school dashboard', 'danger')
        return redirect(url_for('dashboard.dashboard'))

@dashboard_bp.route('/teacher')
@login_required
def teacher_dashboard():
    """Teacher dashboard showing classes and subjects"""
    if current_user.role != 'teacher':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('dashboard.dashboard'))

    if not current_user.school:
        flash('No school assigned', 'danger')
        return redirect(url_for('dashboard.dashboard'))

    try:
        subjects = get_teacher_subjects(current_user)
        school = current_user.school

        classes = list({subject.academic_class for subject in subjects})

        data = {
            'subjects': subjects,
            'classes': classes,
            'school': school,
            'upcoming_exams': get_upcoming_exams(school.id),
            'recent_exams': Exam.query.filter_by(school_id=school.id)
            .order_by(Exam.exam_date.desc())
            .limit(5).all()
        }

        return render_template('dashboard_teacher.html', **data)

    except Exception as e:
        current_app.logger.error(
            f"Teacher dashboard error for teacher {current_user.id}: {str(e)}",
            exc_info=True
        )
        flash('Error loading teacher dashboard', 'danger')
        return redirect(url_for('dashboard.dashboard'))

@dashboard_bp.route('/parent')
@login_required
def parent_dashboard():
    """Parent dashboard showing student progress"""
    if current_user.role != 'parent':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('dashboard.dashboard'))

    try:
        if not current_user.students:
            return render_template('dashboard_parent.html',
                               students=[],
                               performances={},
                               upcoming_exams=[])

        school_ids = {student.school_id for student in current_user.students}
        performances = {
            student.id: get_student_performance(student.id)
            for student in current_user.students
        }

        upcoming_exams = []
        for school_id in school_ids:
            upcoming_exams.extend(get_upcoming_exams(school_id))

        return render_template('dashboard_parent.html',
                           students=current_user.students,
                           performances=performances,
                           upcoming_exams=upcoming_exams)

    except Exception as e:
        current_app.logger.error(
            f"Parent dashboard error for parent {current_user.id}: {str(e)}",
            exc_info=True
        )
        flash('Error loading parent dashboard', 'danger')
        return redirect(url_for('dashboard.dashboard'))