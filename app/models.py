# app/models.py
from datetime import datetime
from app import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import phonenumbers
from email_validator import validate_email, EmailNotValidError


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, index=True)
    email = db.Column(db.String(120), unique=True, index=True)
    password_hash = db.Column(db.String(512))
    role = db.Column(db.String(20))  # 'admin', 'school_admin', 'teacher', 'parent'
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'))
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    phone_number = db.Column(db.String(20))
    notification_preference = db.Column(db.String(20), default='email')  # 'email', 'whatsapp', 'sms'
    email_verified = db.Column(db.Boolean, default=False)
    phone_verified = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)  # Correct definition

    # Relationships
    school = db.relationship('School', back_populates='users')
    students = db.relationship('Student', back_populates='parent')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def validate_phone(self, phone_number):
        try:
            parsed = phonenumbers.parse(phone_number, None)
            return phonenumbers.is_valid_number(parsed)
        except:
            return False

    def validate_email(self, email):
        try:
            validate_email(email)
            return True
        except EmailNotValidError:
            return False


class School(db.Model):
    __tablename__ = 'schools'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120))
    location = db.Column(db.String(120))
    subscription_type = db.Column(db.String(50))  # 'basic', 'premium', etc.
    subscription_expiry = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=False)
    contact_email = db.Column(db.String(120))
    contact_phone = db.Column(db.String(20))

    # Relationships
    users = db.relationship('User', back_populates='school')
    academic_classes = db.relationship('AcademicClass', back_populates='school')
    exams = db.relationship('Exam', back_populates='school')
    payments = db.relationship('Payment', back_populates='school')


class AcademicClass(db.Model):
    __tablename__ = 'academic_classes'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50))  # e.g., "Form 1", "Grade 5"
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'))
    stream = db.Column(db.String(50))  # e.g., "North", "South"

    # Relationships
    school = db.relationship('School', back_populates='academic_classes')
    students = db.relationship('Student', back_populates='academic_class')
    subjects = db.relationship('Subject', back_populates='academic_class')


class Student(db.Model):
    __tablename__ = 'students'
    id = db.Column(db.Integer, primary_key=True)
    admission_number = db.Column(db.String(50), unique=True)
    name = db.Column(db.String(120))
    academic_class_id = db.Column(db.Integer, db.ForeignKey('academic_classes.id'))
    parent_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    comm_ref_id = db.Column(db.String(50), unique=True)  # e.g., "CONTACT_STD1001"

    # Relationships
    academic_class = db.relationship('AcademicClass', back_populates='students')
    parent = db.relationship('User', back_populates='students')
    exam_results = db.relationship('ExamResult', back_populates='student')
    contacts = db.relationship('StudentContact', back_populates='student', uselist=False, cascade="all, delete-orphan")


class StudentContact(db.Model):
    __tablename__ = 'student_contacts'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'))

    # Contact information
    parent1_email = db.Column(db.String(120), index=True)
    parent2_email = db.Column(db.String(120), index=True)
    school_email = db.Column(db.String(120), index=True)
    parent1_whatsapp = db.Column(db.String(20), index=True)
    parent2_whatsapp = db.Column(db.String(20), index=True)
    emergency_contact = db.Column(db.String(20))

    # Verification status
    parent1_email_verified = db.Column(db.Boolean, default=False)
    parent2_email_verified = db.Column(db.Boolean, default=False)
    parent1_whatsapp_verified = db.Column(db.Boolean, default=False)
    parent2_whatsapp_verified = db.Column(db.Boolean, default=False)

    # Communication preferences
    primary_contact_method = db.Column(db.String(20), default='email')  # 'email', 'whatsapp'
    receive_progress_reports = db.Column(db.Boolean, default=True)
    receive_announcements = db.Column(db.Boolean, default=True)

    # Relationships
    student = db.relationship('Student', back_populates='contacts')


class Subject(db.Model):
    __tablename__ = 'subjects'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80))
    code = db.Column(db.String(10))  # e.g., "MATH", "ENG"
    academic_class_id = db.Column(db.Integer, db.ForeignKey('academic_classes.id'))
    has_paper1 = db.Column(db.Boolean, default=False)
    has_paper2 = db.Column(db.Boolean, default=False)
    max_score_paper1 = db.Column(db.Integer, default=100)
    max_score_paper2 = db.Column(db.Integer, default=100)
    is_core = db.Column(db.Boolean, default=True)

    # Relationships
    academic_class = db.relationship('AcademicClass', back_populates='subjects')
    exam_results = db.relationship('ExamResult', back_populates='subject')


class Exam(db.Model):
    __tablename__ = 'exams'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120))  # e.g., "End Term 1 2024"
    exam_type = db.Column(db.String(50))  # 'National', 'Internal'
    exam_date = db.Column(db.DateTime)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'))
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    uploader_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    semester = db.Column(db.Integer)  # 1 or 2
    academic_year = db.Column(db.String(10))  # e.g., "2023-2024"
    template_version = db.Column(db.String(20))
    upload_format = db.Column(db.String(50))  # 'excel', 'csv', 'json'

    # Relationships
    school = db.relationship('School', back_populates='exams')
    results = db.relationship('ExamResult', back_populates='exam')
    uploader = db.relationship('User')


class ExamResult(db.Model):
    __tablename__ = 'exam_results'
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exams.id'))
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'))
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'))
    marks = db.Column(db.Float)
    grade = db.Column(db.String(2))
    comments = db.Column(db.Text)
    position = db.Column(db.Integer)
    paper_number = db.Column(db.Integer)  # 1 or 2 for subjects with multiple papers
    remark = db.Column(db.String(50))  # e.g., "Improved", "Consistent"

    # Relationships
    exam = db.relationship('Exam', back_populates='results')
    student = db.relationship('Student', back_populates='exam_results')
    subject = db.relationship('Subject', back_populates='exam_results')


class Payment(db.Model):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'))
    amount = db.Column(db.Float)
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    payment_method = db.Column(db.String(50))  # 'mpesa', 'stripe', 'bank'
    transaction_id = db.Column(db.String(100))
    status = db.Column(db.String(20))  # 'pending', 'completed', 'failed'
    subscription_period = db.Column(db.String(50))  # 'monthly', 'annual'
    receipt_number = db.Column(db.String(50))
    payer_email = db.Column(db.String(120))
    payer_phone = db.Column(db.String(20))

    # Relationships
    school = db.relationship('School', back_populates='payments')