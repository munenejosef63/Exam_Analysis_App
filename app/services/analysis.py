# app/services/analysis.py
from app import db
from app.models import Exam, ExamResult, School, Subject
from collections import defaultdict
import statistics
from datetime import datetime
from sqlalchemy import func


def update_school_performance(school_id):
    """
    Recalculates and updates overall performance metrics for a school
    Returns: Dictionary with performance metrics
    """
    try:
        # Get all exam results for the school
        results = ExamResult.query.join(Exam).filter(
            Exam.school_id == school_id
        ).all()

        if not results:
            return None

        # Calculate overall statistics
        marks = [r.marks for r in results]
        mean_score = statistics.mean(marks) if marks else 0
        pass_rate = (len([m for m in marks if m >= 50]) / len(marks)) * 100 if marks else 0

        # Calculate subject-wise statistics
        subject_stats = defaultdict(lambda: {'marks': [], 'count': 0})
        class_stats = defaultdict(lambda: {'marks': [], 'count': 0})

        for result in results:
            subject_stats[result.subject.name]['marks'].append(result.marks)
            subject_stats[result.subject.name]['count'] += 1
            class_stats[result.student.academic_class.name]['marks'].append(result.marks)
            class_stats[result.student.academic_class.name]['count'] += 1

        # Update school record
        school = School.query.get(school_id)
        if school:
            school.average_score = round(mean_score, 2)
            school.pass_rate = round(pass_rate, 2)
            school.performance_last_updated = datetime.now()
            db.session.commit()

        return {
            'overall': {
                'mean_score': round(mean_score, 2),
                'pass_rate': round(pass_rate, 2),
                'total_students': len({r.student_id for r in results}),
                'total_subjects': len(subject_stats),
                'total_exams': len({r.exam_id for r in results})
            },
            'by_subject': {
                name: {
                    'mean': statistics.mean(data['marks']),
                    'pass_rate': (len([m for m in data['marks'] if m >= 50]) / len(data['marks'])) * 100,
                    'count': data['count']
                }
                for name, data in subject_stats.items()
            },
            'by_class': {
                name: {
                    'mean': statistics.mean(data['marks']),
                    'pass_rate': (len([m for m in data['marks'] if m >= 50]) / len(data['marks'])) * 100,
                    'count': data['count']
                }
                for name, data in class_stats.items()
            }
        }

    except Exception as e:
        db.session.rollback()
        raise e


def get_school_performance(school_id, exam_id=None):
    """Generate performance analytics for the entire school"""
    query = ExamResult.query.join(Exam).filter(Exam.school_id == school_id)

    if exam_id:
        query = query.filter(ExamResult.exam_id == exam_id)

    results = query.options(
        db.joinedload(ExamResult.student),
        db.joinedload(ExamResult.subject),
        db.joinedload(ExamResult.exam)
    ).all()

    if not results:
        return None

    # Calculate basic statistics with error handling
    marks = [r.marks for r in results]
    mean = statistics.mean(marks) if marks else 0
    median = statistics.median(marks) if marks else 0
    pass_rate = (len([m for m in marks if m >= 50]) / len(marks)) * 100 if marks else 0

    # Performance by academic class with caching
    academic_class_performance = defaultdict(list)
    subject_performance = defaultdict(list)

    for result in results:
        academic_class_performance[result.student.academic_class.name].append(result.marks)
        subject_performance[result.subject.name].append(result.marks)

    return {
        'overall': {
            'mean': mean,
            'median': median,
            'pass_rate': pass_rate,
            'total_students': len({r.student_id for r in results}),
            'total_subjects': len({r.subject_id for r in results}),
            'last_updated': datetime.now().isoformat()
        },
        'by_academic_class': {
            name: {
                'mean': statistics.mean(marks),
                'median': statistics.median(marks),
                'pass_rate': (len([m for m in marks if m >= 50]) / len(marks)) * 100,
                'count': len(marks)
            }
            for name, marks in academic_class_performance.items()
        },
        'by_subject': {
            name: {
                'mean': statistics.mean(marks),
                'median': statistics.median(marks),
                'pass_rate': (len([m for m in marks if m >= 50]) / len(marks)) * 100,
                'count': len(marks),
                'top_student': max(marks) if marks else 0
            }
            for name, marks in subject_performance.items()
        }
    }


def get_student_performance(student_id, limit=5):
    """Generate performance analytics for a single student"""
    results = ExamResult.query.filter_by(student_id=student_id) \
        .options(
        db.joinedload(ExamResult.subject),
        db.joinedload(ExamResult.exam)
    ) \
        .order_by(ExamResult.exam_date.desc()) \
        .limit(limit) \
        .all()

    if not results:
        return None

    # Enhanced performance calculation
    marks = [r.marks for r in results]
    mean = statistics.mean(marks) if marks else 0
    recent_exams = {r.exam.name for r in results}

    # Improved subject performance tracking
    subject_performance = {}
    exam_trend = {}

    for result in results:
        # Subject performance
        if result.subject.name not in subject_performance:
            subject_performance[result.subject.name] = {
                'latest_mark': result.marks,
                'latest_grade': result.grade,
                'exam_count': 1,
                'mark_trend': [result.marks]
            }
        else:
            subj = subject_performance[result.subject.name]
            subj['exam_count'] += 1
            subj['mark_trend'].append(result.marks)
            if result.exam_date > ExamResult.query \
                    .filter_by(student_id=student_id, subject_id=result.subject_id) \
                    .order_by(ExamResult.exam_date.desc()) \
                    .first().exam_date:
                subj['latest_mark'] = result.marks
                subj['latest_grade'] = result.grade

        # Exam trend
        if result.exam.name not in exam_trend:
            exam_trend[result.exam.name] = {
                'date': result.exam.exam_date.isoformat(),
                'subjects': {}
            }
        exam_trend[result.exam.name]['subjects'][result.subject.name] = {
            'marks': result.marks,
            'grade': result.grade,
            'class_avg': db.session.query(func.avg(ExamResult.marks))
                         .filter_by(exam_id=result.exam_id, subject_id=result.subject_id)
                         .scalar() or 0
        }

    return {
        'overall': {
            'mean_score': mean,
            'exam_count': len(recent_exams),
            'improvement': calculate_improvement(marks) if len(marks) > 1 else 0
        },
        'by_subject': subject_performance,
        'by_exam': exam_trend
    }


def calculate_improvement(marks):
    """Calculate performance improvement over time"""
    if len(marks) < 2:
        return 0
    return ((marks[0] - statistics.mean(marks[1:])) / statistics.mean(marks[1:])) * 100


def get_teacher_performance(teacher_id):
    """Generate performance analytics for a teacher's subjects"""
    results = ExamResult.query.join(ExamResult.subject) \
        .filter(Subject.teacher_id == teacher_id) \
        .options(db.joinedload(ExamResult.subject)) \
        .all()

    if not results:
        return None

    subject_stats = defaultdict(lambda: {'marks': [], 'count': 0})
    for result in results:
        subject_stats[result.subject.name]['marks'].append(result.marks)
        subject_stats[result.subject.name]['count'] += 1

    return {
        'overall': {
            'mean_score': statistics.mean([r.marks for r in results]),
            'total_students': len({r.student_id for r in results}),
            'total_exams': len({r.exam_id for r in results})
        },
        'by_subject': {
            name: {
                'mean': statistics.mean(data['marks']),
                'pass_rate': (len([m for m in data['marks'] if m >= 50]) / len(data['marks'])) * 100,
                'count': data['count']
            }
            for name, data in subject_stats.items()
        }
    }