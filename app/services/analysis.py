# app/services/analysis.py
from app import db
from app.models import Exam, ExamResult, School, Subject, Student, User, AcademicClass
from collections import defaultdict
from datetime import datetime
from sqlalchemy import func, case, and_, distinct, or_
import statistics
import json


def update_school_performance(school_id):
    """
    Recalculates and updates overall performance metrics for a school using SQL queries
    Returns: Dictionary with performance metrics
    """
    try:
        # Get overall statistics using SQL with explicit joins
        stats = (db.session.query(
            func.avg(ExamResult.marks).label('mean_score'),
            (func.avg(case((ExamResult.marks >= 50, 1), else_=0)) * 100).label('pass_rate'),
            func.count(distinct(ExamResult.student_id)).label('total_students'),
            func.count(distinct(ExamResult.subject_id)).label('total_subjects'),
            func.count(distinct(ExamResult.exam_id)).label('total_exams')
        )
                 .select_from(ExamResult)
                 .join(Exam, ExamResult.exam_id == Exam.id)
                 .filter(Exam.school_id == school_id)
                 .first())

        if not stats or stats.mean_score is None:
            return None

        # Update school record
        school = School.query.get(school_id)
        if school:
            school.average_score = round(stats.mean_score, 2)
            school.pass_rate = round(stats.pass_rate, 2)
            school.performance_last_updated = datetime.now()
            db.session.commit()

        # Get subject-wise statistics with explicit joins
        subject_stats = (db.session.query(
            Subject.name,
            func.avg(ExamResult.marks).label('mean'),
            (func.avg(case((ExamResult.marks >= 50, 1), else_=0)) * 100).label('pass_rate'),
            func.count(ExamResult.id).label('count')
        )
                         .select_from(ExamResult)
                         .join(Subject, ExamResult.subject_id == Subject.id)
                         .join(Exam, ExamResult.exam_id == Exam.id)
                         .filter(Exam.school_id == school_id)
                         .group_by(Subject.name)
                         .all())

        # Get class-wise statistics with explicit joins
        class_stats = (db.session.query(
            AcademicClass.name,
            func.avg(ExamResult.marks).label('mean'),
            (func.avg(case((ExamResult.marks >= 50, 1), else_=0)) * 100).label('pass_rate'),
            func.count(distinct(ExamResult.student_id)).label('count')
        )
                       .select_from(ExamResult)
                       .join(Student, ExamResult.student_id == Student.id)
                       .join(AcademicClass, Student.academic_class_id == AcademicClass.id)
                       .join(Exam, ExamResult.exam_id == Exam.id)
                       .filter(Exam.school_id == school_id)
                       .group_by(AcademicClass.name)
                       .all())

        return {
            'overall': {
                'mean': round(stats.mean_score, 2),
                'pass_rate': round(stats.pass_rate, 2),
                'total_students': stats.total_students,
                'total_subjects': stats.total_subjects,
                'total_exams': stats.total_exams
            },
            'by_subject': {
                s.name: {
                    'mean': round(s.mean, 2),
                    'pass_rate': round(s.pass_rate, 2),
                    'count': s.count
                } for s in subject_stats
            },
            'by_class': {
                c.name: {
                    'mean': round(c.mean, 2),
                    'pass_rate': round(c.pass_rate, 2),
                    'count': c.count
                } for c in class_stats
            }
        }

    except Exception as e:
        db.session.rollback()
        raise e


def get_school_performance(school_id, exam_id=None):
    """Generate performance analytics using optimized SQL queries with explicit joins"""
    try:
        # Base query with explicit join conditions
        query = (db.session.query(
            ExamResult,
            Student,
            Subject,
            Exam,
            AcademicClass
        )
                 .select_from(ExamResult)
                 .join(Exam, ExamResult.exam_id == Exam.id)
                 .join(Student, ExamResult.student_id == Student.id)
                 .join(Subject, ExamResult.subject_id == Subject.id)
                 .join(AcademicClass, Student.academic_class_id == AcademicClass.id)
                 .filter(Exam.school_id == school_id))

        if exam_id:
            query = query.filter(ExamResult.exam_id == exam_id)

        # Get overall metrics with single query
        overall = query.with_entities(
            func.avg(ExamResult.marks).label('mean'),
            (func.avg(case((ExamResult.marks >= 50, 1), else_=0)) * 100).label('pass_rate'),
            func.count(distinct(ExamResult.student_id)).label('total_students'),
            func.count(ExamResult.id).label('total_results')
        ).first()

        if not overall or overall.mean is None:
            return None

        # Get grade distribution
        grade_dist = query.with_entities(
            ExamResult.grade,
            func.count(ExamResult.id)
        ).group_by(ExamResult.grade).all()

        # Get all students with their scores
        all_students = []
        students = db.session.query(Student).join(AcademicClass).filter(Student.school_id == school_id).all()

        for student in students:
            # Get all exam results for this student
            results = ExamResult.query.filter_by(student_id=student.id)
            if exam_id:
                results = results.filter_by(exam_id=exam_id)
            results = results.join(Subject).all()

            if not results:
                continue

            scores = {r.subject.name: r.marks for r in results}
            total = sum(scores.values())
            avg = total / len(scores) if scores else 0

            all_students.append({
                'id': student.id,
                'name': student.name,
                'class_name': student.academic_class.name,
                'total_score': total,
                'avg_score': avg,
                'scores': scores
            })

        # Sort students by total score descending
        all_students.sort(key=lambda x: x['total_score'], reverse=True)

        # Get top/bottom students from the all_students list
        top_students = [{
            'name': s['name'],
            'avg_score': round(s['avg_score'], 1),
            'total_score': round(s['total_score'], 1),
            'grade': get_grade_from_score(s['avg_score'])
        } for s in all_students[:5]]

        bottom_students = [{
            'name': s['name'],
            'avg_score': round(s['avg_score'], 1),
            'total_score': round(s['total_score'], 1),
            'grade': get_grade_from_score(s['avg_score'])
        } for s in all_students[-5:]]

        # Get teacher performance with explicit joins
        teacher_perf = (db.session.query(
            User.username,
            func.count(distinct(Subject.id)).label('subject_count'),
            func.avg(ExamResult.marks).label('avg_score'),
            (func.avg(case((ExamResult.marks >= 50, 1), else_=0)) * 100).label('pass_rate')
        )
                        .select_from(ExamResult)
                        .join(Subject, ExamResult.subject_id == Subject.id)
                        .join(Exam, ExamResult.exam_id == Exam.id)
                        .join(Subject.teachers)  # This uses the many-to-many relationship directly
                        .filter(Exam.school_id == school_id)
                        .group_by(User.id, User.username)
                        .all())

        # Get performance by subject and class
        by_subject = query.with_entities(
            Subject.name,
            func.avg(ExamResult.marks).label('mean'),
            (func.avg(case((ExamResult.marks >= 50, 1), else_=0)) * 100).label('pass_rate'),
            func.count(distinct(ExamResult.student_id)).label('total_students'),
            func.max(ExamResult.marks).label('top_student')
        ).group_by(Subject.name).all()

        by_class = query.with_entities(
            AcademicClass.name,
            func.avg(ExamResult.marks).label('mean'),
            (func.avg(case((ExamResult.marks >= 50, 1), else_=0)) * 100).label('pass_rate'),
            func.count(distinct(ExamResult.student_id)).label('total_students')
        ).group_by(AcademicClass.name).all()

        return {
            'overall': {
                'mean': round(overall.mean, 1),
                'pass_rate': round(overall.pass_rate, 1),
                'total_students': overall.total_students,
                'active_students': overall.total_students,
                'total_subjects': len(by_subject),
                'core_subjects': len(by_subject),
                'total_results': overall.total_results
            },
            'by_subject': {
                s.name: {
                    'mean': round(s.mean, 1),
                    'pass_rate': round(s.pass_rate, 1),
                    'total_students': s.total_students,
                    'top_student': round(s.top_student, 1)
                } for s in by_subject
            },
            'by_class': {
                c.name: {
                    'mean': round(c.mean, 1),
                    'pass_rate': round(c.pass_rate, 1),
                    'total_students': c.total_students
                } for c in by_class
            },
            'grade_distribution': dict(grade_dist),
            'teacher_performance': [{
                'name': t.username,
                'subject_count': t.subject_count,
                'avg_score': round(t.avg_score, 1),
                'pass_rate': round(t.pass_rate, 1)
            } for t in teacher_perf],
            'all_students': all_students,
            'top_students': top_students,
            'bottom_students': bottom_students,
            'trends': get_performance_trends(school_id)
        }

    except Exception as e:
        db.session.rollback()
        raise e


def get_grade_from_score(score):
    """Helper function to convert score to letter grade"""
    if score >= 80:
        return 'A'
    elif score >= 70:
        return 'B'
    elif score >= 60:
        return 'C'
    elif score >= 50:
        return 'D'
    else:
        return 'E'


def get_performance_trends(school_id, months=6):
    """Get historical performance trends with explicit joins"""
    trend_data = (db.session.query(
        func.to_char(Exam.exam_date, 'YYYY-MM').label('month'),
        func.avg(ExamResult.marks).label('mean_score'),
        (func.avg(case((ExamResult.marks >= 50, 1), else_=0)) * 100).label('pass_rate')
    )
                  .select_from(ExamResult)
                  .join(Exam, ExamResult.exam_id == Exam.id)
                  .filter(Exam.school_id == school_id)
                  .group_by(func.to_char(Exam.exam_date, 'YYYY-MM'))
                  .order_by(func.to_char(Exam.exam_date, 'YYYY-MM').desc())
                  .limit(months)
                  .all())

    if not trend_data:
        return {
            'mean_trend': 0,
            'pass_rate_trend': 0,
            'exam_periods': [],
            'mean_scores': [],
            'pass_rates': []
        }

    # Calculate trends
    mean_trend = calculate_trend([t.mean_score for t in trend_data])
    pass_rate_trend = calculate_trend([t.pass_rate for t in trend_data])

    return {
        'mean_trend': mean_trend,
        'pass_rate_trend': pass_rate_trend,
        'exam_periods': [t.month for t in reversed(trend_data)],
        'mean_scores': [round(t.mean_score, 1) for t in reversed(trend_data)],
        'pass_rates': [round(t.pass_rate, 1) for t in reversed(trend_data)]
    }


def calculate_trend(values):
    """Calculate percentage change between last two values"""
    if len(values) < 2:
        return 0
    current = values[0]
    previous = values[1]
    if previous == 0:
        return 0
    return round(((current - previous) / previous) * 100, 1)


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