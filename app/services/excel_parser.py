# app/services/excel_parser.py
import pandas as pd
from datetime import datetime
import phonenumbers
from email_validator import validate_email, EmailNotValidError
from app.models import (
    db,
    Exam,
    Student,
    Subject,
    ExamResult,
    AcademicClass,
    StudentContact,
    School
)
from app import logger


def process_exam_upload(file_stream):
    """
    Simplified interface for processing exam uploads
    Returns dict with processed data statistics
    """
    try:
        # Initialize parser with default values
        parser = ExamParser()

        # Parse the file (using dummy school_id and uploader_id for compatibility)
        success, message = parser.parse_excel(
            file_stream=file_stream,
            school_id=1,  # Should be replaced with actual school_id from session
            uploader_id=1  # Should be replaced with actual user_id from session
        )

        if not success:
            raise Exception(message)

        return {
            'status': 'success',
            'students': Student.query.count(),  # Count of processed students
            'results': ExamResult.query.count(),  # Count of processed results
            'message': message
        }

    except Exception as e:
        logger.error(f"Exam upload processing failed: {str(e)}")
        return {
            'status': 'error',
            'message': str(e)
        }


class ExamParser:
    def __init__(self):
        self.school_id = None
        self.uploader_id = None
        self.current_exam = None

    def parse_excel(self, file_stream, school_id, uploader_id):
        """Main method to parse the complete Excel template"""
        self.school_id = school_id
        self.uploader_id = uploader_id

        try:
            xls = pd.ExcelFile(file_stream)

            # Process each sheet
            exam_data = self._parse_metadata_sheet(xls)
            contacts_data = self._parse_contacts_sheet(xls)
            subjects_config = self._parse_subjects_sheet(xls)
            results = self._parse_results_sheet(xls, subjects_config)

            # Create exam record
            self.current_exam = self._create_exam_record(exam_data)

            # Process all student data
            for admission_no, data in results.items():
                self._process_student_record(admission_no, data, contacts_data.get(admission_no, {}))

            db.session.commit()
            return True, "Exam results uploaded successfully"

        except Exception as e:
            db.session.rollback()
            logger.error(f"Excel parsing failed: {str(e)}")
            return False, f"Error: {str(e)}"

    def _parse_metadata_sheet(self, xls):
        """Parse the Exam Metadata sheet"""
        try:
            df = pd.read_excel(xls, sheet_name='Exam Metadata')
            return df.iloc[0].to_dict()
        except Exception as e:
            raise ValueError(f"Metadata sheet error: {str(e)}")

    def _parse_contacts_sheet(self, xls):
        """Parse the Student Contacts sheet"""
        try:
            df = pd.read_excel(xls, sheet_name='Student Contacts')
            contacts = {}

            for _, row in df.iterrows():
                contacts[row['AdmissionNo']] = {
                    'parent1_email': self._validate_email(row.get('Parent1_Email')),
                    'parent2_email': self._validate_email(row.get('Parent2_Email')),
                    'school_email': self._validate_email(row.get('School_Email')),
                    'parent1_whatsapp': self._validate_phone(row.get('Parent1_WhatsApp')),
                    'parent2_whatsapp': self._validate_phone(row.get('Parent2_WhatsApp'))
                }
            return contacts
        except Exception as e:
            raise ValueError(f"Contacts sheet error: {str(e)}")

    def _parse_subjects_sheet(self, xls):
        """Parse the Subject Configuration sheet"""
        try:
            df = pd.read_excel(xls, sheet_name='Subject Configuration')
            return {row['SubjectCode']: row.to_dict() for _, row in df.iterrows()}
        except Exception as e:
            raise ValueError(f"Subjects sheet error: {str(e)}")

    def _parse_results_sheet(self, xls, subjects_config):
        """Parse the Student Results sheet"""
        try:
            df = pd.read_excel(xls, sheet_name='Student Results')
            results = {}

            for _, row in df.iterrows():
                admission_no = row['AdmissionNo']
                if admission_no not in results:
                    results[admission_no] = {
                        'student_name': row['StudentName'],
                        'class_name': row['Class'],
                        'stream': row.get('Stream'),
                        'results': []
                    }

                # Process all subject columns
                for col in row.index:
                    if col not in ['AdmissionNo', 'StudentName', 'Class', 'Stream', 'CommRefID']:
                        subject_name, paper_num = self._parse_subject_column(col, subjects_config)
                        results[admission_no]['results'].append({
                            'subject': subject_name,
                            'paper': paper_num,
                            'marks': float(row[col]),
                            'remarks': row.get('Remarks', '')
                        })

            return results
        except Exception as e:
            raise ValueError(f"Results sheet error: {str(e)}")

    def _parse_subject_column(self, column_name, subjects_config):
        """Extract subject name and paper number from column"""
        if '_Paper' in column_name:
            subject_name, paper = column_name.split('_Paper')
            return subject_name, int(paper)
        return column_name, None

    def _create_exam_record(self, exam_data):
        """Create the exam record in database"""
        exam = Exam(
            name=exam_data['ExamName'],
            exam_type=exam_data['ExamType'],
            exam_date=exam_data['StartDate'],
            school_id=self.school_id,
            uploader_id=self.uploader_id,
            semester=exam_data['Semester'],
            academic_year=str(exam_data['AcademicYear']),
            template_version='2.1',
            upload_format='excel'
        )
        db.session.add(exam)
        db.session.flush()
        return exam

    def _process_student_record(self, admission_no, student_data, contact_data):
        """Process individual student record with results and contacts"""
        # Get or create student
        student = Student.query.filter_by(
            admission_number=admission_no,
            school_id=self.school_id
        ).first()

        if not student:
            student = self._create_student(admission_no, student_data)

        # Update contact information if provided
        if contact_data:
            self._update_contact_info(student, contact_data)

        # Process exam results
        for result in student_data['results']:
            self._create_exam_result(student, result)

    def _create_student(self, admission_no, student_data):
        """Create new student record"""
        class_ = Class.query.filter_by(
            name=student_data['class_name'],
            school_id=self.school_id
        ).first()

        if not class_:
            class_ = Class(
                name=student_data['class_name'],
                stream=student_data.get('stream'),
                school_id=self.school_id
            )
            db.session.add(class_)
            db.session.flush()

        student = Student(
            admission_number=admission_no,
            name=student_data['student_name'],
            class_id=class_.id,
            school_id=self.school_id,
            comm_ref_id=f"CONTACT_{admission_no}"
        )
        db.session.add(student)
        db.session.flush()
        return student

    def _update_contact_info(self, student, contact_data):
        """Update or create student contact information"""
        if not student.contacts:
            student.contacts = StudentContact()

        for field, value in contact_data.items():
            if value is not None:
                setattr(student.contacts, field, value)

    def _create_exam_result(self, student, result_data):
        """Create exam result record"""
        subject = Subject.query.filter_by(
            name=result_data['subject'],
            class_id=student.class_id
        ).first()

        if not subject:
            subject = Subject(
                name=result_data['subject'],
                class_id=student.class_id,
                has_paper1=True if result_data['paper'] == 1 else False,
                has_paper2=True if result_data['paper'] == 2 else False
            )
            db.session.add(subject)
            db.session.flush()

        exam_result = ExamResult(
            exam_id=self.current_exam.id,
            student_id=student.id,
            subject_id=subject.id,
            marks=result_data['marks'],
            grade=self._calculate_grade(result_data['marks']),
            paper_number=result_data['paper'],
            remark=result_data['remarks'],
            position=0  # Will be calculated later
        )
        db.session.add(exam_result)

    def _validate_email(self, email):
        """Validate and normalize email address"""
        if pd.isna(email) or email in ['-', '']:
            return None
        try:
            v = validate_email(email)
            return v.email
        except EmailNotValidError as e:
            raise ValueError(f"Invalid email {email}: {str(e)}")

    def _validate_phone(self, phone):
        """Validate and normalize phone number"""
        if pd.isna(phone) or phone in ['-', '']:
            return None
        try:
            parsed = phonenumbers.parse(phone, None)
            if not phonenumbers.is_valid_number(parsed):
                raise ValueError("Invalid phone number")
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        except Exception as e:
            raise ValueError(f"Invalid phone {phone}: {str(e)}")

    def _calculate_grade(self, marks):
        """Calculate grade based on marks"""
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


def parse_excel(file_stream, exam_name, exam_date, school_id, uploader_id):
    """Legacy wrapper for backward compatibility"""
    parser = ExamParser()
    return parser.parse_excel(file_stream, school_id, uploader_id)