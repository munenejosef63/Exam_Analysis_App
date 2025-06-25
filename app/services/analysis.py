# app/services/analysis.py
from app.models import db, Exam, Student, Class, Subject, ExamResult
from collections import defaultdict
import statistics


def get_school_performance(school_id, exam_id=None):
    """Generate performance analytics for the entire school"""
    query = ExamResult.query.join(Exam).filter(Exam.school_id == school_id)

    if exam_id:
        query = query.filter(ExamResult.exam_id == exam_id)

    results = query.all()

    if not results:
        return None

    # Calculate basic statistics
    marks = [r.marks for r in results]
    mean = statistics.mean(marks)
    median = statistics.median(marks)
    pass_rate = len([m for m in marks if m >= 50]) / len(marks) * 100

    # Performance by class
    class_performance = defaultdict(list)
    for result in results:
        class_performance[result.student.

        class .name].append(result.marks)

        class_stats = {}
        for class_name, marks in class_performance.items():
            class_stats[class_name] = {

        'mean': statistics.mean(marks),
        'median': statistics.median(marks),
        'pass_rate': len([m for m in marks if m >= 50]) / len(marks) * 100,
        'count': len(marks)
    }

    # Performance by subject
    subject_performance = defaultdict(list)
    for result in results:
        subject_performance[result.subject.name].append(result.marks)

    subject_stats = {}
    for subject_name, marks in subject_performance.items():
        subject_stats[subject_name] = {
    'mean': statistics.mean(marks),
    'median': statistics.median(marks),
    'pass_rate': len([m for m in marks if m >= 50]) / len(marks) * 100,
    'count': len(marks)

}

return {
    'overall': {
        'mean': mean,
        'median': median,
        'pass_rate': pass_rate,
        'total_students': len({r.student_id for r in results}),
        'total_subjects': len({r.subject_id for r in results})
    },
    'by_class': class_stats,
    'by_subject': subject_stats
}


def get_teacher_performance(teacher_id, exam_id=None):
    """Generate performance analytics for a teacher's subjects"""
    # Implementation would depend on how teachers are associated with subjects
    pass


def get_student_performance(student_id):
    """Generate performance analytics for a single student"""
    results = ExamResult.query.filter_by(student_id=student_id).all()

    if not results:
        return None

    # Overall performance
    marks = [r.marks for r in results]
    mean = statistics.mean(marks)
    grades = [r.grade for r in results]

    # Performance by subject
    subject_performance = {}
    for result in results:
        subject_performance[result.subject.name] = {
            'marks': result.marks,
            'grade': result.grade,
            'position': result.position,
            'exam': result.exam.name
        }

    # Performance trend over time
    exam_performance = {}
    for result in results:
        if result.exam.name not in exam_performance:
            exam_performance[result.exam.name] = {
                'date': result.exam.exam_date,
                'subjects': {}
            }
        exam_performance[result.exam.name]['subjects'][result.subject.name] = {
            'marks': result.marks,
            'grade': result.grade
        }

    return {
        'overall': {
            'mean': mean,
            'grades': grades
        },
        'by_subject': subject_performance,
        'by_exam': exam_performance
    }