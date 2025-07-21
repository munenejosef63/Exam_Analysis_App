import pandas as pd
from datetime import datetime
import phonenumbers
from email_validator import validate_email, EmailNotValidError
from flask import current_app
from flask_login import current_user
import logging
from app.models import (
    db,
    Exam,
    Student,
    Subject,
    ExamResult,
    AcademicClass,
    StudentContact,
    School,
    User
)
from app.services.grading import calculate_grade
from sqlalchemy.exc import IntegrityError

# Configure logger
logger = logging.getLogger(__name__)

REQUIRED_SHEETS = {
    'Exam Metadata': ['ExamName', 'ExamType', 'StartDate', 'Semester', 'AcademicYear'],
    'Student Contacts': ['AdmissionNo'],
    'Subject Configuration': ['SubjectCode'],
    'Student Results': ['AdmissionNo', 'StudentName', 'Class']
}


def process_exam_upload(file_stream):
    """
    Process exam uploads with improved error handling and dynamic school assignment
    Returns dict with processed data statistics
    """
    try:
        if not current_user.is_authenticated:
            raise ValueError("User must be logged in to upload exams")

        if not current_user.school_id:
            raise ValueError("User is not associated with any school")

        parser = ExamParser()
        success, message = parser.parse_excel(
            file_stream=file_stream,
            school_id=current_user.school_id,
            uploader_id=current_user.id
        )

        if not success:
            raise ValueError(message)

        return {
            'status': 'success',
            'students': Student.query.filter_by(school_id=current_user.school_id).count(),
            'results': ExamResult.query.join(Exam).filter(
                Exam.school_id == current_user.school_id
            ).count(),
            'message': message,
            'exam_id': parser.current_exam.id if parser.current_exam else None
        }

    except Exception as e:
        logger.error(f"Exam upload processing failed: {str(e)}", exc_info=True)
        return {
            'status': 'error',
            'message': f"Upload failed: {str(e)}"
        }


class ExamParser:
    def __init__(self):
        self.school_id = None
        self.uploader_id = None
        self.current_exam = None
        self.current_school = None

    def parse_excel(self, file_stream, school_id, uploader_id):
        """Main method to parse the complete Excel template"""
        self.school_id = school_id
        self.uploader_id = uploader_id

        try:
            # Validate school exists
            self.current_school = School.query.get(self.school_id)
            if not self.current_school:
                raise ValueError(f"School with ID {self.school_id} does not exist")

            xls = pd.ExcelFile(file_stream)
            self._validate_sheet_structure(xls)

            exam_data = self._parse_metadata_sheet(xls)
            contacts_data = self._parse_contacts_sheet(xls)
            subjects_config = self._parse_subjects_sheet(xls)
            results = self._parse_results_sheet(xls, subjects_config)

            self.current_exam = self._create_exam_record(exam_data)

            processed_students = 0
            for admission_no, data in results.items():
                try:
                    self._process_student_record(
                        admission_no,
                        data,
                        contacts_data.get(admission_no, {})
                    )
                    processed_students += 1
                except Exception as e:
                    logger.warning(f"Skipped student {admission_no}: {str(e)}")
                    continue

            db.session.commit()
            logger.info(
                f"Successfully uploaded exam results for {processed_students} students "
                f"to exam ID: {self.current_exam.id} in school ID: {self.school_id}"
            )
            return True, f"Processed {processed_students} student records successfully"

        except Exception as e:
            db.session.rollback()
            logger.error(f"Excel parsing failed: {str(e)}", exc_info=True)
            return False, f"Error processing file: {str(e)}"

    def _validate_sheet_structure(self, xls):
        """Validate the Excel file structure before processing"""
        missing_sheets = [sheet for sheet in REQUIRED_SHEETS if sheet not in xls.sheet_names]
        if missing_sheets:
            raise ValueError(f"Missing required sheets: {', '.join(missing_sheets)}")

    def _parse_metadata_sheet(self, xls):
        """Parse the Exam Metadata sheet with validation"""
        try:
            df = pd.read_excel(xls, sheet_name='Exam Metadata')
            missing_cols = [col for col in REQUIRED_SHEETS['Exam Metadata'] if col not in df.columns]
            if missing_cols:
                raise ValueError(f"Metadata sheet missing columns: {', '.join(missing_cols)}")

            return df.iloc[0].to_dict()
        except Exception as e:
            logger.error(f"Error parsing metadata sheet: {str(e)}")
            raise ValueError(f"Invalid metadata sheet: {str(e)}")

    def _parse_contacts_sheet(self, xls):
        """Parse the Student Contacts sheet with flexible column handling"""
        try:
            df = pd.read_excel(xls, sheet_name='Student Contacts')

            # Handle case-insensitive column names
            column_map = {
                'admissionno': 'AdmissionNo',
                'parent1_email': 'Parent1_Email',
                'parent2_email': 'Parent2_Email',
                'school_email': 'School_Email',
                'parent1_whatsapp': 'Parent1_WhatsApp',
                'parent2_whatsapp': 'Parent2_WhatsApp'
            }

            # Normalize column names
            df.columns = df.columns.str.strip().str.lower()

            # Check for required columns
            if 'admissionno' not in df.columns:
                raise ValueError("Contacts sheet must contain 'AdmissionNo' column")

            contacts = {}
            for _, row in df.iterrows():
                admission_no = str(row['admissionno']).strip()
                if not admission_no:
                    continue

                contacts[admission_no] = {
                    'parent1_email': self._validate_email(row.get('parent1_email')),
                    'parent2_email': self._validate_email(row.get('parent2_email')),
                    'school_email': self._validate_email(row.get('school_email')),
                    'parent1_whatsapp': self._validate_phone(row.get('parent1_whatsapp')),
                    'parent2_whatsapp': self._validate_phone(row.get('parent2_whatsapp'))
                }
            return contacts

        except Exception as e:
            logger.error(f"Error parsing contacts sheet: {str(e)}")
            raise ValueError(f"Invalid contacts sheet: {str(e)}")

    def _parse_subjects_sheet(self, xls):
        """Parse the Subject Configuration sheet"""
        try:
            df = pd.read_excel(xls, sheet_name='Subject Configuration')
            if 'SubjectCode' not in df.columns:
                raise ValueError("Subjects sheet must contain 'SubjectCode' column")

            return {row['SubjectCode']: row.to_dict() for _, row in df.iterrows()}
        except Exception as e:
            logger.error(f"Error parsing subjects sheet: {str(e)}")
            raise ValueError(f"Invalid subjects sheet: {str(e)}")

    def _parse_results_sheet(self, xls, subjects_config):
        """Parse the Student Results sheet with validation"""
        try:
            df = pd.read_excel(xls, sheet_name='Student Results')

            # Check for required columns
            missing_cols = [col for col in REQUIRED_SHEETS['Student Results'] if col not in df.columns]
            if missing_cols:
                raise ValueError(f"Results sheet missing columns: {', '.join(missing_cols)}")

            results = {}
            for _, row in df.iterrows():
                try:
                    admission_no = str(row['AdmissionNo']).strip()
                    if not admission_no:
                        continue

                    if admission_no not in results:
                        results[admission_no] = {
                            'student_name': str(row['StudentName']).strip(),
                            'class_name': str(row['Class']).strip(),
                            'stream': str(row.get('Stream', '')).strip(),
                            'results': []
                        }

                    for col in row.index:
                        if col not in ['AdmissionNo', 'StudentName', 'Class', 'Stream', 'CommRefID', 'Remarks']:
                            if pd.notna(row[col]):
                                subject_name, paper_num = self._parse_subject_column(col, subjects_config)
                                results[admission_no]['results'].append({
                                    'subject': subject_name,
                                    'paper': paper_num,
                                    'marks': float(row[col]),
                                    'remarks': str(row.get('Remarks', '')).strip()
                                })
                except Exception as e:
                    logger.warning(f"Error processing row for admission {row.get('AdmissionNo')}: {str(e)}")
                    continue

            if not results:
                raise ValueError("No valid student results found in the sheet")

            logger.info(f"Parsed results for {len(results)} students")
            return results

        except Exception as e:
            logger.error(f"Error parsing results sheet: {str(e)}")
            raise ValueError(f"Invalid results sheet: {str(e)}")

    def _create_exam_record(self, exam_data):
        """Create the exam record in database with validation"""
        try:
            required_fields = ['ExamName', 'ExamType', 'StartDate', 'Semester', 'AcademicYear']
            missing_fields = [field for field in required_fields if field not in exam_data or not exam_data[field]]
            if missing_fields:
                raise ValueError(f"Missing required exam fields: {', '.join(missing_fields)}")

            exam = Exam(
                name=str(exam_data['ExamName']),
                exam_type=str(exam_data['ExamType']),
                exam_date=exam_data['StartDate'],
                school_id=self.school_id,
                uploader_id=self.uploader_id,
                semester=str(exam_data['Semester']),
                academic_year=str(exam_data['AcademicYear']),
                template_version='2.1',
                upload_format='excel'
            )
            db.session.add(exam)
            db.session.flush()
            logger.info(f"Created exam record: {exam.name} (ID: {exam.id}) for school ID: {self.school_id}")
            return exam
        except IntegrityError as e:
            raise ValueError(f"Database integrity error creating exam: {str(e)}")
        except Exception as e:
            logger.error(f"Error creating exam record: {str(e)}")
            raise ValueError(f"Failed to create exam record: {str(e)}")

    def _process_student_record(self, admission_no, student_data, contact_data):
        """Process individual student record with error handling"""
        # First try to find existing student in the same school
        student = Student.query.filter_by(
            admission_number=admission_no
        ).join(AcademicClass).filter(
            AcademicClass.school_id == self.school_id
        ).first()

        if not student:
            student = self._create_student(admission_no, student_data)

        if contact_data:
            self._update_contact_info(student, contact_data)

        for result in student_data['results']:
            self._create_exam_result(student, result)

    def _create_student(self, admission_no, student_data):
        """Create new student record with validation"""
        if not student_data.get('class_name'):
            raise ValueError("Class name is required")

        # Find or create academic class within the same school
        class_ = AcademicClass.query.filter_by(
            name=student_data['class_name'],
            school_id=self.school_id
        ).first()

        if not class_:
            class_ = AcademicClass(
                name=student_data['class_name'],
                stream=student_data.get('stream', ''),
                school_id=self.school_id
            )
            db.session.add(class_)
            db.session.flush()

        student = Student(
            admission_number=admission_no,
            name=student_data['student_name'],
            academic_class_id=class_.id,
            comm_ref_id=f"{self.school_id}_{admission_no}"
        )
        db.session.add(student)
        db.session.flush()
        logger.info(f"Created new student: {student.name} ({admission_no}) in school ID: {self.school_id}")
        return student

    def _update_contact_info(self, student, contact_data):
        """Update or create student contact information"""
        if not student.contacts:
            student.contacts = StudentContact()

        for field, value in contact_data.items():
            if value is not None:
                setattr(student.contacts, field, value)

    def _create_exam_result(self, student, result_data):
        """Create exam result record with validation"""
        if not result_data.get('subject'):
            raise ValueError("Subject name is required")

        subject = Subject.query.filter_by(
            name=result_data['subject'],
            academic_class_id=student.academic_class_id
        ).first()

        if not subject:
            subject = Subject(
                name=result_data['subject'],
                academic_class_id=student.academic_class_id,
                has_paper1=True if result_data.get('paper') == 1 else False,
                has_paper2=True if result_data.get('paper') == 2 else False
            )
            db.session.add(subject)
            db.session.flush()

        exam_result = ExamResult(
            exam_id=self.current_exam.id,
            student_id=student.id,
            subject_id=subject.id,
            marks=float(result_data['marks']),
            grade=calculate_grade(float(result_data['marks'])),
            paper_number=result_data.get('paper'),
            remark=result_data.get('remarks', ''),
            position=0
        )
        db.session.add(exam_result)

    # Helper methods remain the same...
    def _parse_subject_column(self, column_name, subjects_config):
        """Extract subject name and paper number from column with validation"""
        try:
            if '_Paper' in column_name:
                subject_name, paper = column_name.split('_Paper')
                return subject_name.strip(), int(paper.strip())
            return column_name.strip(), None
        except Exception as e:
            logger.warning(f"Invalid subject column format: {column_name}")
            raise ValueError(f"Invalid subject column: {column_name}")

    def _validate_email(self, email):
        """Validate and normalize email address"""
        if pd.isna(email) or not str(email).strip() or str(email).strip().lower() in ['-', 'n/a', 'null']:
            return None
        try:
            v = validate_email(str(email).strip())
            return v.email
        except EmailNotValidError as e:
            logger.warning(f"Invalid email format: {email}")
            return None

    def _validate_phone(self, phone):
        """Validate and normalize phone number"""
        if pd.isna(phone) or not str(phone).strip() or str(phone).strip().lower() in ['-', 'n/a', 'null']:
            return None
        try:
            parsed = phonenumbers.parse(str(phone).strip(), None)
            if not phonenumbers.is_valid_number(parsed):
                raise ValueError("Invalid phone number")
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        except Exception as e:
            logger.warning(f"Invalid phone format: {phone}")
            return None


def parse_excel(file_stream, exam_name=None, exam_date=None, school_id=None, uploader_id=None):
    """Legacy wrapper for backward compatibility"""
    parser = ExamParser()
    return parser.parse_excel(
        file_stream,
        school_id or current_user.school_id,
        uploader_id or current_user.id
    )