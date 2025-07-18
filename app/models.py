from datetime import datetime
from app import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import phonenumbers
from email_validator import validate_email, EmailNotValidError
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy import func, and_


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# Association table for teacher-subject many-to-many relationship
teacher_subjects = db.Table('teacher_subjects',
    db.Column('teacher_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('subject_id', db.Integer, db.ForeignKey('subjects.id'), primary_key=True),
    db.Column('date_assigned', db.DateTime, default=datetime.utcnow)
)


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
    notification_preference = db.Column(db.String(20), default='email')
    email_verified = db.Column(db.Boolean, default=False)
    phone_verified = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    # Relationships
    school = db.relationship('School', back_populates='users')
    students = db.relationship('Student', back_populates='parent')
    uploaded_exams = db.relationship('Exam', back_populates='uploader')
    taught_subjects = db.relationship('Subject',
                                    secondary=teacher_subjects,
                                    back_populates='teachers',
                                    lazy='dynamic')

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

    def get_taught_exams(self):
        """Returns exams for subjects this teacher teaches"""
        from sqlalchemy import and_
        return Exam.query.join(ExamResult).join(Subject).filter(
            and_(
                Subject.id.in_([s.id for s in self.taught_subjects]),
                Exam.school_id == self.school_id
            )
        ).distinct()


class School(db.Model):
    __tablename__ = 'schools'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120))
    location = db.Column(db.String(120))
    subscription_type = db.Column(db.String(50))
    subscription_expiry = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=False)
    contact_email = db.Column(db.String(120))
    contact_phone = db.Column(db.String(20))

    # Relationships
    users = db.relationship('User', back_populates='school')
    academic_classes = db.relationship('AcademicClass', back_populates='school')
    exams = db.relationship('Exam', back_populates='school')
    payments = db.relationship('Payment', back_populates='school')

    def active_teachers(self):
        return User.query.filter_by(school_id=self.id, role='teacher', is_active=True).all()


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

    def get_exams(self):
        """Returns all exams taken by this class"""
        return Exam.query.join(ExamResult).join(Student).filter(
            Student.academic_class_id == self.id
        ).distinct()


class Student(db.Model):
    __tablename__ = 'students'
    id = db.Column(db.Integer, primary_key=True)
    admission_number = db.Column(db.String(50), unique=True)
    name = db.Column(db.String(120))
    academic_class_id = db.Column(db.Integer, db.ForeignKey('academic_classes.id'))
    parent_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    comm_ref_id = db.Column(db.String(50), unique=True)

    # Relationships
    academic_class = db.relationship('AcademicClass', back_populates='students')
    parent = db.relationship('User', back_populates='students')
    exam_results = db.relationship('ExamResult', back_populates='student')
    contacts = db.relationship('StudentContact', back_populates='student',
                             uselist=False, cascade="all, delete-orphan")

    @hybrid_property
    def school_id(self):
        """Provides access to school_id through academic_class relationship"""
        return self.academic_class.school_id if self.academic_class else None

    @school_id.expression
    def school_id(cls):
        """Enables querying by school_id directly on Student"""
        return AcademicClass.school_id

    def get_exams(self):
        """Returns all exams taken by this student"""
        return Exam.query.join(ExamResult).filter(
            ExamResult.student_id == self.id
        ).distinct()


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
    primary_contact_method = db.Column(db.String(20), default='email')
    receive_progress_reports = db.Column(db.Boolean, default=True)
    receive_announcements = db.Column(db.Boolean, default=True)

    # Relationships
    student = db.relationship('Student', back_populates='contacts')


class Subject(db.Model):
    __tablename__ = 'subjects'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80))
    code = db.Column(db.String(10))
    academic_class_id = db.Column(db.Integer, db.ForeignKey('academic_classes.id'))
    has_paper1 = db.Column(db.Boolean, default=False)
    has_paper2 = db.Column(db.Boolean, default=False)
    max_score_paper1 = db.Column(db.Integer, default=100)
    max_score_paper2 = db.Column(db.Integer, default=100)
    is_core = db.Column(db.Boolean, default=True)

    # Relationships
    academic_class = db.relationship('AcademicClass', back_populates='subjects')
    exam_results = db.relationship('ExamResult', back_populates='subject')
    exams = db.relationship('Exam',
                          secondary='exam_results',
                          back_populates='subjects',
                          viewonly=True)
    teachers = db.relationship('User',
                             secondary=teacher_subjects,
                             back_populates='taught_subjects',
                             lazy='dynamic')

    def get_exams(self):
        """Returns all exams for this subject"""
        return Exam.query.join(ExamResult).filter(
            ExamResult.subject_id == self.id
        ).distinct()


class Exam(db.Model):
    __tablename__ = 'exams'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120))
    exam_type = db.Column(db.String(50))
    exam_date = db.Column(db.DateTime)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'))
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    uploader_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    semester = db.Column(db.Integer)
    academic_year = db.Column(db.String(10))
    template_version = db.Column(db.String(20))
    upload_format = db.Column(db.String(50))

    # Relationships
    school = db.relationship('School', back_populates='exams')
    results = db.relationship('ExamResult', back_populates='exam',
                            cascade='all, delete-orphan')
    uploader = db.relationship('User', back_populates='uploaded_exams')
    subjects = db.relationship('Subject',
                             secondary='exam_results',
                             back_populates='exams',
                             viewonly=True)

    def get_subject_ids(self):
        """Returns list of subject IDs for this exam"""
        return [subject.id for subject in self.subjects]

    def get_student_count(self):
        """Returns number of students who took this exam"""
        return db.session.query(func.count(ExamResult.student_id)).filter(
            ExamResult.exam_id == self.id
        ).scalar()

    @classmethod
    def get_by_subject(cls, subject_id):
        """Returns exams for a specific subject"""
        return cls.query.join(ExamResult).filter(
            ExamResult.subject_id == subject_id
        ).distinct()


class ExamResult(db.Model):
    __tablename__ = 'exam_results'
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exams.id'), index=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), index=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), index=True)
    marks = db.Column(db.Float)
    grade = db.Column(db.String(2))
    comments = db.Column(db.Text)
    position = db.Column(db.Integer)
    paper_number = db.Column(db.Integer)
    remark = db.Column(db.String(50))

    # Relationships
    exam = db.relationship('Exam', back_populates='results')
    student = db.relationship('Student', back_populates='exam_results')
    subject = db.relationship('Subject', back_populates='exam_results')

    def get_percentage(self):
        """Calculates percentage score based on subject max score"""
        max_score = self.subject.max_score_paper1 if self.paper_number == 1 else self.subject.max_score_paper2
        return (self.marks / max_score) * 100 if max_score else 0


class Payment(db.Model):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'))
    amount = db.Column(db.Float)
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    payment_method = db.Column(db.String(50))
    transaction_id = db.Column(db.String(100))
    status = db.Column(db.String(20))
    subscription_period = db.Column(db.String(50))
    receipt_number = db.Column(db.String(50))
    payer_email = db.Column(db.String(120))
    payer_phone = db.Column(db.String(20))

    # Relationships
    school = db.relationship('School', back_populates='payments')