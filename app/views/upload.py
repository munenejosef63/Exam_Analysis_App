from flask import Blueprint, request, flash, redirect, url_for, current_app, render_template
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import os
import logging
from datetime import datetime
from app.services.excel_parser import process_exam_upload
from app.services.analysis import update_school_performance
from app.models import db

# Initialize logger
logger = logging.getLogger(__name__)

upload_bp = Blueprint('upload', __name__, template_folder='templates')

ALLOWED_EXTENSIONS = {'xlsx', 'xls'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@upload_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    """Handle exam file uploads with validation, processing, and dashboard redirection"""
    if request.method == 'GET':
        return render_template('upload.html')

    try:
        # Validate form inputs
        exam_name = request.form.get('exam_name')
        exam_date = request.form.get('exam_date')

        if not exam_name or not exam_date:
            flash('Exam name and date are required', 'error')
            return redirect(url_for('upload.upload'))

        # Validate file
        if 'file' not in request.files:
            flash('No file uploaded', 'error')
            return redirect(url_for('upload.upload'))

        file = request.files['file']

        if file.filename == '':
            flash('No selected file', 'error')
            return redirect(url_for('upload.upload'))

        if not allowed_file(file.filename):
            flash('Only Excel files (.xlsx, .xls) are allowed', 'error')
            return redirect(url_for('upload.upload'))

        if not allowed_file_size(file):
            flash('File size exceeds maximum limit (10MB)', 'error')
            return redirect(url_for('upload.upload'))

        # Process the file using excel_parser service
        result = process_exam_upload(file.stream)

        if result['status'] == 'error':
            flash(f"Processing failed: {result['message']}", 'error')
            return redirect(url_for('upload.upload'))

        # Create exam record (simplified - adjust according to your Exam model)
        exam_date = datetime.strptime(exam_date, '%Y-%m-%d').date()

        # Update school performance metrics
        update_school_performance(current_user.school_id)

        logger.info(f"Exam results processed successfully by user {current_user.id}")
        flash('Exam results processed successfully! Dashboard updated.', 'success')
        return redirect(url_for('dashboard.school_dashboard'))

    except ValueError as e:
        flash(f'Invalid date format: {str(e)}', 'error')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Upload failed: {str(e)}", exc_info=True)
        flash(f'An error occurred: {str(e)}', 'error')

    return redirect(url_for('upload.upload'))


def allowed_file(filename):
    """Check if the file has an allowed extension"""
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def allowed_file_size(file):
    """Check if the file size is within limits"""
    start_pos = file.tell()
    file.seek(0, 2)
    size = file.tell()
    file.seek(start_pos)
    return size <= MAX_FILE_SIZE