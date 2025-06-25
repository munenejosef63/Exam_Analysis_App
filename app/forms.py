# app/forms.py
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms import StringField, PasswordField, SubmitField, SelectField, DateField, FloatField, IntegerField, BooleanField, TextAreaField
from wtforms.validators import DataRequired, Email, ValidationError, Length, Optional, NumberRange
from app.models import User, School, Student
from flask_login import current_user
from email_validator import validate_email, EmailNotValidError
import phonenumbers

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=64)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), Length(min=8)])
    role = SelectField('Role', choices=[
        ('school_admin', 'School Administrator'),
        ('teacher', 'Teacher'),
        ('parent', 'Parent')
    ], validators=[DataRequired()])
    school_name = StringField('School Name', validators=[DataRequired()])
    school_location = StringField('School Location', validators=[DataRequired()])
    phone_number = StringField('Phone Number', validators=[Optional()])
    submit = SubmitField('Register')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Email already in use. Please choose a different one.')

    def validate_phone_number(self, phone_number):
        if phone_number.data:
            try:
                parsed = phonenumbers.parse(phone_number.data, None)
                if not phonenumbers.is_valid_number(parsed):
                    raise ValidationError('Invalid phone number')
            except:
                raise ValidationError('Invalid phone number format')

class SchoolForm(FlaskForm):
    name = StringField('School Name', validators=[DataRequired(), Length(max=120)])
    location = StringField('Location', validators=[DataRequired(), Length(max=120)])
    contact_email = StringField('Contact Email', validators=[DataRequired(), Email()])
    contact_phone = StringField('Contact Phone', validators=[DataRequired()])
    submit = SubmitField('Save School')

    def validate_contact_phone(self, contact_phone):
        try:
            parsed = phonenumbers.parse(contact_phone.data, None)
            if not phonenumbers.is_valid_number(parsed):
                raise ValidationError('Invalid phone number')
        except:
            raise ValidationError('Invalid phone number format')

class StudentForm(FlaskForm):
    admission_number = StringField('Admission Number', validators=[DataRequired(), Length(max=50)])
    name = StringField('Full Name', validators=[DataRequired(), Length(max=120)])
    class_id = SelectField('Class', coerce=int, validators=[DataRequired()])
    parent_id = SelectField('Parent/Guardian', coerce=int, validators=[Optional()])
    submit = SubmitField('Save Student')

class StudentContactForm(FlaskForm):
    parent1_email = StringField('Primary Email', validators=[DataRequired(), Email()])
    parent2_email = StringField('Secondary Email', validators=[Optional(), Email()])
    school_email = StringField('School Email', validators=[Optional(), Email()])
    parent1_whatsapp = StringField('Primary WhatsApp', validators=[DataRequired()])
    parent2_whatsapp = StringField('Secondary WhatsApp', validators=[Optional()])
    emergency_contact = StringField('Emergency Contact', validators=[Optional()])
    primary_contact_method = SelectField('Preferred Contact Method', choices=[
        ('email', 'Email'),
        ('whatsapp', 'WhatsApp'),
        ('sms', 'SMS')
    ], validators=[DataRequired()])
    receive_progress_reports = BooleanField('Receive Progress Reports', default=True)
    receive_announcements = BooleanField('Receive Announcements', default=True)
    submit = SubmitField('Save Contact Info')

    def validate_parent1_whatsapp(self, field):
        try:
            parsed = phonenumbers.parse(field.data, None)
            if not phonenumbers.is_valid_number(parsed):
                raise ValidationError('Invalid WhatsApp number')
        except:
            raise ValidationError('Invalid WhatsApp number format')

    def validate_parent2_whatsapp(self, field):
        if field.data:
            try:
                parsed = phonenumbers.parse(field.data, None)
                if not phonenumbers.is_valid_number(parsed):
                    raise ValidationError('Invalid WhatsApp number')
            except:
                raise ValidationError('Invalid WhatsApp number format')

class ExamUploadForm(FlaskForm):
    exam_name = StringField('Exam Name', validators=[DataRequired(), Length(max=120)])
    exam_type = SelectField('Exam Type', choices=[
        ('national', 'National Exam'),
        ('internal', 'Internal Exam')
    ], validators=[DataRequired()])
    exam_date = DateField('Exam Date', validators=[DataRequired()])
    semester = SelectField('Semester', choices=[
        (1, 'Semester 1'),
        (2, 'Semester 2')
    ], validators=[DataRequired()])
    academic_year = StringField('Academic Year', validators=[DataRequired()])
    template_version = StringField('Template Version', default='2.1', validators=[DataRequired()])
    file = FileField('Excel File', validators=[
        DataRequired(),
        FileAllowed(['xlsx', 'xls'], 'Excel files only!')
    ])
    submit = SubmitField('Upload Results')

class SubjectForm(FlaskForm):
    name = StringField('Subject Name', validators=[DataRequired(), Length(max=80)])
    code = StringField('Subject Code', validators=[DataRequired(), Length(max=10)])
    class_id = SelectField('Class', coerce=int, validators=[DataRequired()])
    has_paper1 = BooleanField('Has Paper 1', default=False)
    has_paper2 = BooleanField('Has Paper 2', default=False)
    max_score_paper1 = IntegerField('Max Score Paper 1', validators=[Optional(), NumberRange(min=0, max=100)])
    max_score_paper2 = IntegerField('Max Score Paper 2', validators=[Optional(), NumberRange(min=0, max=100)])
    is_core = BooleanField('Core Subject', default=True)
    submit = SubmitField('Save Subject')

class PaymentForm(FlaskForm):
    amount = FloatField('Amount', validators=[DataRequired(), NumberRange(min=0)])
    payment_method = SelectField('Payment Method', choices=[
        ('mpesa', 'M-Pesa'),
        ('stripe', 'Credit Card'),
        ('bank', 'Bank Transfer')
    ], validators=[DataRequired()])
    subscription_period = SelectField('Subscription Period', choices=[
        ('monthly', 'Monthly'),
        ('annual', 'Annual')
    ], validators=[DataRequired()])
    payer_email = StringField('Payer Email', validators=[DataRequired(), Email()])
    payer_phone = StringField('Payer Phone', validators=[DataRequired()])
    submit = SubmitField('Process Payment')

    def validate_payer_phone(self, payer_phone):
        try:
            parsed = phonenumbers.parse(payer_phone.data, None)
            if not phonenumbers.is_valid_number(parsed):
                raise ValidationError('Invalid phone number')
        except:
            raise ValidationError('Invalid phone number format')

class ExamResultForm(FlaskForm):
    marks = FloatField('Marks', validators=[DataRequired(), NumberRange(min=0, max=100)])
    grade = StringField('Grade', validators=[DataRequired(), Length(max=2)])
    comments = TextAreaField('Comments', validators=[Optional(), Length(max=500)])
    position = IntegerField('Position', validators=[Optional(), NumberRange(min=1)])
    paper_number = SelectField('Paper Number', choices=[
        (None, 'Single Paper'),
        (1, 'Paper 1'),
        (2, 'Paper 2')
    ], validators=[Optional()])
    remark = StringField('Remark', validators=[Optional(), Length(max=50)])
    submit = SubmitField('Save Result')