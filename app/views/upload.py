# app/views/upload.py
from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from datetime import datetime
import os
from app.services.excel_parser import parse_excel
from app.views.models import Exam
from app import app

upload_bp = Blueprint('upload', __name__)


@upload_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_exam():
    if current_user.role not in ['school_admin', 'teacher']:
        flash('You are not authorized to upload exams', 'danger')
        return redirect(url_for('dashboard.dashboard'))

    if request.method == 'POST':
        # Check if the post request has the file part
        if 'file' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)

        file = request.files['file']
        exam_name = request.form.get('exam_name')
        exam_date_str = request.form.get('exam_date')

        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(request.url)

        if not exam_name or not exam_date_str:
            flash('Exam name and date are required', 'danger')
            return redirect(request.url)

        try:
            exam_date = datetime.strptime(exam_date_str, '%Y-%m-%d')
        except ValueError:
            flash('Invalid date format', 'danger')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # In a production app, you'd save to cloud storage (S3, etc.)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)

            # Parse the Excel file
            success, message = parse_excel(
                file_path,
                exam_name,
                exam_date,
                current_user.school_id,
                current_user.id
            )

            if success:
                flash('Exam results uploaded successfully!', 'success')
                return redirect(url_for('dashboard.school_dashboard'))
            else:
                flash(f'Error: {message}', 'danger')

    exams = Exam.query.filter_by(school_id=current_user.school_id).all()
    return render_template('upload.html', exams=exams)


def allowed_file(filename):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in ['xlsx', 'xls']