from flask import Blueprint, render_template, flash, redirect, url_for, make_response
from flask_login import login_required, current_user
from app.services.analysis import get_school_performance, get_student_performance, update_school_performance
from app.models import Exam, School, Payment, Subject, AcademicClass, User, ExamResult, teacher_subjects, Student
from app import db
from datetime import datetime, timedelta, date
from sqlalchemy import func, desc, case, and_
import logging
from sqlalchemy import distinct


# Initialize logger
logger = logging.getLogger(__name__)

dashboard_bp = Blueprint('dashboard', __name__)


def get_teacher_subjects(teacher):
    """Get subjects taught by a teacher with class information and recent results"""
    subjects = teacher.taught_subjects.all()

    # Add class information and recent results for each subject
    for subject in subjects:
        subject.recent_results = ExamResult.query \
            .join(Exam, ExamResult.exam_id == Exam.id) \
            .filter(ExamResult.subject_id == subject.id) \
            .order_by(desc(Exam.exam_date)) \
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


def get_recent_exams(school_id, limit=5):
    """Get recent exams with performance metrics"""
    exams = Exam.query.filter_by(school_id=school_id) \
        .order_by(Exam.exam_date.desc()) \
        .limit(limit) \
        .all()

    # Add performance metrics to each exam
    for exam in exams:
        exam.mean_score = db.session.query(func.avg(ExamResult.marks)) \
                              .filter_by(exam_id=exam.id) \
                              .scalar() or 0
        exam.pass_rate = db.session.query(
            func.avg(case((ExamResult.marks >= 50, 1), else_=0))
        ).filter_by(exam_id=exam.id) \
         .scalar() * 100 or 0
        exam.student_count = ExamResult.query.filter_by(exam_id=exam.id).count()
        exam.trend = calculate_exam_trend(exam.id)
    return exams

def calculate_exam_trend(exam_id):
    """Calculate trend for a specific exam compared to previous similar exam"""
    current_exam = Exam.query.get(exam_id)
    if not current_exam or not current_exam.subjects:
        return 0

    # Get the first subject (assuming exams typically have one primary subject)
    current_subject = current_exam.subjects[0]

    # Find previous exams for the same subject
    prev_exam = Exam.query.join(ExamResult) \
        .filter(
        Exam.school_id == current_exam.school_id,
        ExamResult.subject_id == current_subject.id,
        Exam.id != current_exam.id,
        Exam.exam_date < current_exam.exam_date
    ) \
        .order_by(desc(Exam.exam_date)) \
        .first()

    if not prev_exam:
        return 0

    current_avg = db.session.query(func.avg(ExamResult.marks)) \
                      .filter_by(exam_id=current_exam.id).scalar() or 0
    prev_avg = db.session.query(func.avg(ExamResult.marks)) \
                   .filter_by(exam_id=prev_exam.id).scalar() or 0

    return round(((current_avg - prev_avg) / prev_avg) * 100, 2) if prev_avg != 0 else 0


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


def get_class_performance(school_id):
    """Get performance data by class"""
    results = db.session.query(
        AcademicClass.name,
        func.avg(ExamResult.marks).label('mean'),
        (func.avg(case((ExamResult.marks >= 50, 1), else_=0)) * 100).label('pass_rate')
    ).join(Exam, ExamResult.exam_id == Exam.id) \
        .join(Subject) \
        .join(AcademicClass) \
        .filter(AcademicClass.school_id == school_id) \
        .group_by(AcademicClass.name) \
        .all()

    return {r.name: {'mean': r.mean, 'pass_rate': r.pass_rate} for r in results}


def get_subject_performance(school_id):
    """Get performance data by subject"""
    results = db.session.query(
        Subject.name,
        func.avg(ExamResult.marks).label('mean'),
        (func.avg(case((ExamResult.marks >= 50, 1), else_=0)) * 100).label('pass_rate')
    ).join(ExamResult) \
        .join(Exam) \
        .join(AcademicClass) \
        .filter(AcademicClass.school_id == school_id) \
        .group_by(Subject.name) \
        .all()

    return {r.name: {'mean': r.mean, 'pass_rate': r.pass_rate} for r in results}


def get_grade_distribution(school_id):
    """Get distribution of grades across all exams"""
    grade_counts = db.session.query(
        ExamResult.grade,
        func.count(ExamResult.id)
    ).join(Exam) \
        .filter(Exam.school_id == school_id) \
        .group_by(ExamResult.grade) \
        .all()

    return {grade: count for grade, count in grade_counts}


def get_teacher_performance_metrics(school_id):
    """Get performance metrics for all teachers in school"""
    return db.session.query(
        User.username.label('name'),
        func.count(distinct(Subject.id)).label('subject_count'),
        func.avg(ExamResult.marks).label('avg_score'),
        (func.avg(case((ExamResult.marks >= 50, 1), else_=0)) * 100).label('pass_rate')
    ).join(teacher_subjects, teacher_subjects.c.teacher_id == User.id) \
        .join(Subject, teacher_subjects.c.subject_id == Subject.id) \
        .join(ExamResult, ExamResult.subject_id == Subject.id) \
        .filter(User.school_id == school_id, User.role == 'teacher') \
        .group_by(User.id, User.username) \
        .all()


def get_top_students(school_id, limit=5):
    """Get top performing students"""
    return db.session.query(
        User.username,
        func.avg(ExamResult.marks).label('avg_score')
    ).join(ExamResult, ExamResult.student_id == User.id) \
        .filter(User.school_id == school_id, User.role == 'student') \
        .group_by(User.id) \
        .order_by(func.avg(ExamResult.marks).desc()) \
        .limit(limit) \
        .all()


def get_bottom_students(school_id, limit=5):
    """Get students needing improvement"""
    return db.session.query(
        User.username,
        func.avg(ExamResult.marks).label('avg_score')
    ).join(ExamResult, ExamResult.student_id == User.id) \
        .filter(User.school_id == school_id, User.role == 'student') \
        .group_by(User.id) \
        .order_by(func.avg(ExamResult.marks).asc()) \
        .limit(limit) \
        .all()


def calculate_trend_percentage(values):
    """Calculate percentage change between last two values"""
    if len(values) < 2:
        return 0
    current = values[-1]
    previous = values[-2]
    if previous == 0:
        return 0
    return ((current - previous) / previous) * 100


def get_performance_trend_data(school_id, months=6):
    """Get comprehensive performance trend data for charts and indicators"""
    # Get mean scores trend
    mean_trend = db.session.query(
        func.to_char(Exam.exam_date, 'YYYY-MM').label('month'),
        func.avg(ExamResult.marks).label('avg_marks')
    ).join(ExamResult) \
        .filter(Exam.school_id == school_id) \
        .group_by(func.to_char(Exam.exam_date, 'YYYY-MM')) \
        .order_by(func.to_char(Exam.exam_date, 'YYYY-MM').desc()) \
        .limit(months).all()

    # Get pass rates trend
    pass_rate_trend = db.session.query(
        func.to_char(Exam.exam_date, 'YYYY-MM').label('month'),
        (func.avg(case((ExamResult.marks >= 50, 1), else_=0)) * 100).label('pass_rate')
    ).join(ExamResult) \
        .filter(Exam.school_id == school_id) \
        .group_by(func.to_char(Exam.exam_date, 'YYYY-MM')) \
        .order_by(func.to_char(Exam.exam_date, 'YYYY-MM').desc()) \
        .limit(months).all()

    # Prepare data
    exam_periods = [t.month for t in mean_trend]
    mean_scores = [float(t.avg_marks) for t in mean_trend]
    pass_rates = [float(t.pass_rate) for t in pass_rate_trend]

    # Calculate trend percentages
    mean_trend_pct = calculate_trend_percentage(mean_scores) if mean_scores else 0
    pass_rate_trend_pct = calculate_trend_percentage(pass_rates) if pass_rates else 0

    return {
        'exam_periods': exam_periods,
        'mean_scores': mean_scores,
        'pass_rates': pass_rates,
        'mean_trend_pct': mean_trend_pct,
        'pass_rate_trend_pct': pass_rate_trend_pct
    }


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
    """Get revenue trends with monthly breakdown"""
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

        # Handle subscription expiry with proper datetime/date conversion
        if school.subscription_expiry is None:
            school.subscription_expiry = datetime(1900, 1, 1)  # Using datetime for consistency
            db.session.commit()
            logger.warning(f"School {school.id} had null subscription_expiry - set to default")
        elif isinstance(school.subscription_expiry, date):
            school.subscription_expiry = datetime.combine(school.subscription_expiry, datetime.min.time())
            db.session.commit()

        update_school_performance(school.id)

        # Get comprehensive performance trend data with None check
        trend_data = get_performance_trend_data(school.id) or {
            'mean_trend_pct': 0,
            'pass_rate_trend_pct': 0,
            'exam_periods': [],
            'mean_scores': [],
            'pass_rates': []
        }

        # Get school performance with proper None handling
        school_performance = get_school_performance(school.id) or {}

        # Prepare the complete performance dictionary
        performance = get_school_performance(school.id) or {
            'overall': {
                'mean': 0,
                'pass_rate': 0,
                'total_students': User.query.filter_by(
                    school_id=school.id,
                    role='student'
                ).count(),
                'active_students': User.query.filter_by(
                    school_id=school.id,
                    role='student',
                    is_active=True
                ).count(),
                'total_subjects': Subject.query.join(AcademicClass) \
                    .filter(AcademicClass.school_id == school.id) \
                    .count(),
                'core_subjects': Subject.query.join(AcademicClass) \
                    .filter(
                    AcademicClass.school_id == school.id,
                    Subject.is_core == True
                ).count(),
                'total_results': ExamResult.query.join(Exam) \
                    .filter(Exam.school_id == school.id).count()
            },
            'by_class': get_class_performance(school.id) or {},
            'by_subject': get_subject_performance(school.id) or {},
            'trends': {
                'mean_trend': trend_data.get('mean_trend_pct', 0),
                'pass_rate_trend': trend_data.get('pass_rate_trend_pct', 0),
                'exam_periods': trend_data.get('exam_periods', []),
                'mean_scores': trend_data.get('mean_scores', []),
                'pass_rates': trend_data.get('pass_rates', [])
            },
            'grade_distribution': get_grade_distribution(school.id) or {},
            'teacher_performance': get_teacher_performance_metrics(school.id) or [],
            'top_students': get_top_students(school.id) or [],
            'bottom_students': get_bottom_students(school.id) or []
        }

        # Get additional data with error handling
        try:
            exams = get_recent_exams(school.id)
            stats = get_school_stats(school.id)
        except Exception as e:
            logger.warning(f"Error fetching additional dashboard data: {str(e)}")
            exams = []
            stats = {}

        # Prepare data for template with consistent datetime types
        current_date = datetime.now()  # Using datetime consistently
        students = User.query.filter_by(school_id=school.id, role='student').all()

        data = {
            'students': students if students else [],
            'school': school,
            'performance': performance,
            'exams': exams,
            'current_date': current_date,  # Now always datetime
            'current_date_date': current_date.date(),  # Also provide date version if needed
            'stats': stats or {}
        }

        logger.debug(f"Dashboard data prepared for school {school.id}")
        response = make_response(render_template('dashboard_school.html', **data))
        response.headers['Cache-Control'] = 'no-cache'
        return response

    except Exception as e:
        logger.error(f"School dashboard error for user {current_user.id}: {str(e)}", exc_info=True)
        flash('Error loading school dashboard. Please try again later.', 'danger')
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
    ).join(teacher_subjects, teacher_subjects.c.subject_id == Subject.id) \
        .join(ExamResult, ExamResult.subject_id == Subject.id) \
        .filter(teacher_subjects.c.teacher_id == teacher_id) \
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