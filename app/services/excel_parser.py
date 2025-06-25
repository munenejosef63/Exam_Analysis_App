# app/services/excel_parser.py
import pandas as pd
from app.views.models import db, Exam, Student, Subject, ExamResult, Class


def parse_excel(file_stream, exam_name, exam_date, school_id, uploader_id):
    try:
        # Read Excel file
        df = pd.read_excel(file_stream)

        # Create new exam record
        new_exam = Exam(
            name=exam_name,
            exam_date=exam_date,
            school_id=school_id,
            uploader_id=uploader_id
        )
        db.session.add(new_exam)
        db.session.commit()

        # Process each row in the Excel file
        for _, row in df.iterrows():
            # Get or create student
            student = Student.query.filter_by(
                admission_number=row['AdmissionNumber'],
                school_id=school_id
            ).first()

            if not student:
                # Find class
                class_ = Class.query.filter_by(
                    name=row['Class'],
                    school_id=school_id
                ).first()

                if not class_:
                    class_ = Class(name=row['Class'], school_id=school_id)
                    db.session.add(class_)
                    db.session.commit()

                student = Student(
                    admission_number=row['AdmissionNumber'],
                    name=row['StudentName'],
                    class_id=class_.id,
                    school_id=school_id
                )
                db.session.add(student)
                db.session.commit()

            # Process each subject
            for subject_name, marks in row.items():
                if subject_name in ['AdmissionNumber', 'StudentName', 'Class']:
                    continue

                # Get or create subject
                subject = Subject.query.filter_by(
                    name=subject_name,
                    class_id=student.class_id
                ).first()

                if not subject:
                    subject = Subject(
                        name=subject_name,
                        class_id=student.class_id
                    )
                    db.session.add(subject)
                    db.session.commit()

                # Create exam result
                exam_result = ExamResult(
                    exam_id=new_exam.id,
                    student_id=student.id,
                    subject_id=subject.id,
                    marks=float(marks),
                    grade=calculate_grade(float(marks))
                )
                db.session.add(exam_result)

        db.session.commit()
        return True, "Exam results uploaded successfully"
    except Exception as e:
        db.session.rollback()
        return False, str(e)


def calculate_grade(marks):
    if marks >= 80:
        return 'A'
    elif marks >= 70:
        return 'B'
    elif marks >= 60:
        return 'C'
    elif marks >= 50:
        return 'D'
    else:
        return 'E'