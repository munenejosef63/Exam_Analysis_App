from flask import Blueprint, render_template, flash, redirect, url_for, current_app, make_response
from flask_login import login_required, current_user
from app.services.analysis import get_school_performance, get_student_performance, update_school_performance
from app.models import Exam, School, Payment, Subject, AcademicClass, User, ExamResult
from app import db
from datetime import datetime, timedelta
from sqlalchemy import func, desc, extract
import logging

# Initialize logger
logger = logging.getLogger(__name__)

dashboard_bp = Blueprint('dashboard', __name__)


def get_teacher_subjects(teacher):
    """Get subjects taught by a teacher with class information and recent results"""
    subjects = Subject.query.join(AcademicClass) \
        .filter(AcademicClass.school_id == teacher.school_id) \
        .options(db.joinedload(Subject.academic_class)) \
        .all()

    # Add recent results for each subject
    for subject in subjects:
        subject.recent_results = ExamResult.query \
            .filter_by(subject_id=subject.id) \
            .order_by(desc(ExamResult.exam_date)) \
            .limit(5) \
            .all()
    return subjects


def get_upcoming_exams(school_id, days=30):
    """Get upcoming exams with additional details"""
    return Exam.query.filter(
        Exam.school_id == school_id,
        Exam.exam_date >= datetime.now().date(),
        Exam.exam_date <= datetime.now().date() + timedelta(days=days)
    ).order_by(Exam.exam_date.asc()).all()


def get_recent_activity(school_id, limit=5):
    """Get recent system activity with performance impact"""
    recent_exams = Exam.query.filter_by(school_id=school_id) \
        .order_by(Exam.exam_date.desc()) \
        .limit(limit).all()

    # Calculate performance changes for recent exams
    for exam in recent_exams:
        exam.performance_change = calculate_performance_change(exam.id)

    recent_payments = Payment.query.filter_by(school_id=school_id) \
        .order_by(Payment.payment_date.desc()) \
        .limit(limit).all()

    return {
        'exams': recent_exams,
        'payments': recent_payments
    }


def calculate_performance_change(exam_id):
    """Calculate performance change compared to previous exam"""
    current_exam = Exam.query.get(exam_id)
    if not current_exam:
        return 0

    # Get previous exam of same type
    prev_exam = Exam.query.filter(
        Exam.school_id == current_exam.school_id,
        Exam.name == current_exam.name,
        Exam.exam_date < current_exam.exam_date
    ).order_by(desc(Exam.exam_date)).first()

    if not prev_exam:
        return 0

    current_avg = db.session.query(func.avg(ExamResult.marks)) \
                      .filter_by(exam_id=current_exam.id).scalar() or 0
    prev_avg = db.session.query(func.avg(ExamResult.marks)) \
                   .filter_by(exam_id=prev_exam.id).scalar() or 0

    return round(((current_avg - prev_avg) / prev_avg) * 100, 2) if prev_avg != 0 else 0


@dashboard_bp.route('/')
@login_required
def dashboard():
    """Main dashboard route with cache control"""
    response = make_response(redirect_to_role_dashboard())
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    return response


def redirect_to_role_dashboard():
    """Handle role-based dashboard routing"""
    role_handlers = {
        'admin': admin_dashboard,
        'school_admin': school_dashboard,
        'teacher': teacher_dashboard,
        'parent': parent_dashboard
    }

    handler = role_handlers.get(current_user.role)
    if not handler:
        logger.warning(f'Unknown role accessed: {current_user.role}')
        flash('Unknown user role', 'warning')
        return redirect(url_for('auth.login'))

    return handler()


@dashboard_bp.route('/admin')
@login_required
def admin_dashboard():
    """Admin dashboard with fresh data and performance metrics"""
    if current_user.role != 'admin':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('dashboard.dashboard'))

    try:
        # Force fresh data query
        stats = {
            'total_schools': School.query.count(),
            'active_schools': School.query.filter_by(is_active=True).count(),
            'total_users': User.query.count(),
            'recent_payments': Payment.query.order_by(Payment.payment_date.desc()).limit(10).all(),
            'revenue_data': get_revenue_trends(),
            'performance_metrics': get_system_performance_metrics()
        }

        response = make_response(render_template('dashboard_admin.html', **stats))
        response.headers['Cache-Control'] = 'no-cache'
        return response

    except Exception as e:
        logger.error(f"Admin dashboard error: {str(e)}", exc_info=True)
        flash('Error loading admin dashboard', 'danger')
        return redirect(url_for('dashboard.dashboard'))


def get_revenue_trends():
    """Get revenue trends with monthly breakdown using PostgreSQL to_char"""
    return db.session.query(
        func.to_char(Payment.payment_date, 'YYYY-MM').label('month'),
        func.sum(Payment.amount).label('amount')
    ).group_by(func.to_char(Payment.payment_date, 'YYYY-MM')).all()


def get_system_performance_metrics():
    """Get system-wide performance metrics"""
    return {
        'avg_school_performance': db.session.query(
            func.avg(School.performance_score)
        ).scalar(),
        'top_performing_schools': School.query.order_by(
            desc(School.performance_score)
        ).limit(5).all()
    }


@dashboard_bp.route('/school')
@login_required
def school_dashboard():
    """School dashboard with real-time performance data"""
    if current_user.role != 'school_admin':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('dashboard.dashboard'))

    if not current_user.school:
        flash('No school assigned', 'danger')
        return redirect(url_for('dashboard.dashboard'))

    try:
        school = current_user.school
        update_school_performance(school.id)  # Ensure fresh performance data

        data = {
            'school': school,
            'performance': get_school_performance(school.id),
            'upcoming_exams': get_upcoming_exams(school.id),
            'recent_activity': get_recent_activity(school.id),
            'stats': get_school_stats(school.id),
            'performance_trend': get_performance_trend(school.id)
        }

        response = make_response(render_template('dashboard_school.html', **data))
        response.headers['Cache-Control'] = 'no-cache'
        return response

    except Exception as e:
        logger.error(f"School dashboard error: {str(e)}", exc_info=True)
        flash('Error loading school dashboard', 'danger')
        return redirect(url_for('dashboard.dashboard'))


def get_school_stats(school_id):
    """Get school statistics with fresh queries"""
    return {
        'teacher_count': User.query.filter_by(school_id=school_id, role='teacher').count(),
        'student_count': User.query.filter_by(school_id=school_id, role='student').count(),
        'active_exams': Exam.query.filter_by(school_id=school_id).count(),
        'pending_payments': Payment.query.filter_by(
            school_id=school_id,
            status='pending'
        ).count()
    }


def get_performance_trend(school_id, months=6):
    """Get performance trend data for charts using PostgreSQL date functions"""
    return db.session.query(
        func.to_char(Exam.exam_date, 'YYYY-MM').label('month'),
        func.avg(ExamResult.marks).label('avg_marks')
    ).join(ExamResult) \
     .filter(Exam.school_id == school_id) \
     .group_by(func.to_char(Exam.exam_date, 'YYYY-MM')) \
     .order_by(func.to_char(Exam.exam_date, 'YYYY-MM').desc()) \
     .limit(months).all()


@dashboard_bp.route('/teacher')
@login_required
def teacher_dashboard():
    """Teacher dashboard with subject performance data"""
    if current_user.role != 'teacher':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('dashboard.dashboard'))

    if not current_user.school:
        flash('No school assigned', 'danger')
        return redirect(url_for('dashboard.dashboard'))

    try:
        data = {
            'subjects': get_teacher_subjects(current_user),
            'school': current_user.school,
            'upcoming_exams': get_upcoming_exams(current_user.school.id),
            'performance_overview': get_teacher_performance(current_user.id)
        }

        response = make_response(render_template('dashboard_teacher.html', **data))
        response.headers['Cache-Control'] = 'no-cache'
        return response

    except Exception as e:
        logger.error(f"Teacher dashboard error: {str(e)}", exc_info=True)
        flash('Error loading teacher dashboard', 'danger')
        return redirect(url_for('dashboard.dashboard'))


def get_teacher_performance(teacher_id):
    """Get performance metrics for teacher's subjects"""
    return db.session.query(
        Subject.name,
        func.avg(ExamResult.marks).label('average_score'),
        func.count(ExamResult.id).label('results_count')
    ).join(ExamResult) \
     .filter(Subject.teacher_id == teacher_id) \
     .group_by(Subject.name).all()


@dashboard_bp.route('/parent')
@login_required
def parent_dashboard():
    """Parent dashboard with student progress tracking"""
    if current_user.role != 'parent':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('dashboard.dashboard'))

    try:
        if not current_user.students:
            return render_template('dashboard_parent.html',
                                 students=[],
                                 performances={},
                                 upcoming_exams=[])

        performances = {
            student.id: get_student_performance(student.id, force_refresh=True)
            for student in current_user.students
        }

        data = {
            'students': current_user.students,
            'performances': performances,
            'upcoming_exams': get_upcoming_exams_for_students(current_user.students),
            'performance_trends': get_student_trends(current_user.students)
        }

        response = make_response(render_template('dashboard_parent.html', **data))
        response.headers['Cache-Control'] = 'no-cache'
        return response

    except Exception as e:
        logger.error(f"Parent dashboard error: {str(e)}", exc_info=True)
        flash('Error loading parent dashboard', 'danger')
        return redirect(url_for('dashboard.dashboard'))


def get_upcoming_exams_for_students(students):
    """Get upcoming exams for multiple students"""
    school_ids = {student.school_id for student in students}
    exams = []
    for school_id in school_ids:
        exams.extend(get_upcoming_exams(school_id))
    return exams


def get_student_trends(students):
    """Get performance trends for multiple students"""
    return {
        student.id: db.session.query(
            Exam.name,
            ExamResult.marks
        ).join(Exam) \
         .filter(ExamResult.student_id == student.id) \
         .order_by(Exam.exam_date.desc()) \
         .limit(5).all()
        for student in students
    }