# app/models.py
from datetime import datetime
from app import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, index=True)
    email = db.Column(db.String(120), unique=True, index=True)
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(20))  # 'admin', 'school_admin', 'teacher', 'parent'
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'))
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    school = db.relationship('School', back_populates='users')
    students = db.relationship('Student', back_populates='parent')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class School(db.Model):
    __tablename__ = 'schools'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120))
    location = db.Column(db.String(120))
    subscription_type = db.Column(db.String(50))  # 'basic', 'premium', etc.
    subscription_expiry = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=False)

    # Relationships
    users = db.relationship('User', back_populates='school')
    classes = db.relationship('Class', back_populates='school')
    exams = db.relationship('Exam', back_populates='school')
    payments = db.relationship('Payment', back_populates='school')


class Class(db.Model):
    __tablename__ = 'classes'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50))  # e.g., "Form 1", "Grade 5"
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'))

    # Relationships
    school = db.relationship('School', back_populates='classes')
    students = db.relationship('Student', back_populates='class')
    subjects = db.relationship('Subject', back_populates='class')


class Student(db.Model):
    __tablename__ = 'students'
    id = db.Column(db.Integer, primary_key=True)
    admission_number = db.Column(db.String(50), unique=True)
    name = db.Column(db.String(120))
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'))
    parent_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Relationships
    class = db.relationship('Class', back_populates='students')

    parent = db.relationship('User', back_populates='students')
    exam_results = db.relationship('ExamResult', back_populates='student')


class Subject(db.Model):
    __tablename__ = 'subjects'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80))
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'))

    # Relationships
    class = db.relationship('Class', back_populates='subjects')

    exam_results = db.relationship('ExamResult', back_populates='subject')


class Exam(db.Model):
    __tablename__ = 'exams'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120))  # e.g., "End Term 1 2024"
    exam_date = db.Column(db.DateTime)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'))
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    uploader_id = db.Column(db.Integer, db.ForeignKey('users.id'))

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

    # Relationships
    school = db.relationship('School', back_populates='payments')