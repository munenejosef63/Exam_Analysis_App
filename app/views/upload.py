from flask import Blueprint, request, flash, redirect, url_for, current_app, render_template
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import os
import logging

# Initialize logger
logger = logging.getLogger(__name__)

upload_bp = Blueprint('upload', __name__, template_folder='templates')

ALLOWED_EXTENSIONS = {'xlsx', 'xls'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@upload_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    """Handle exam file uploads with validation and processing"""
    if request.method == 'GET':
        # Show the upload form for GET requests
        return render_template('upload.html')

    # POST request handling
    try:
        # Check if file was uploaded
        if 'file' not in request.files:
            flash('No file uploaded', 'error')
            return redirect(url_for('upload.upload'))

        file = request.files['file']

        # Check if file is empty
        if file.filename == '':
            flash('No selected file', 'error')
            return redirect(url_for('upload.upload'))

        # Validate file type
        if not allowed_file(file.filename):
            flash('Only Excel files (.xlsx, .xls) are allowed', 'error')
            return redirect(url_for('upload.upload'))

        # Validate file size
        if not allowed_file_size(file):
            flash('File size exceeds maximum limit (10MB)', 'error')
            return redirect(url_for('upload.upload'))

        # Secure the filename
        filename = secure_filename(file.filename)

        # Here you would typically process the file
        # For now, we'll just log success
        logger.info(f"File {filename} uploaded successfully by user {current_user.id}")
        flash('File uploaded successfully! Processing would happen here.', 'success')

    except Exception as e:
        current_app.logger.error(f"Upload failed: {str(e)}", exc_info=True)
        flash('An unexpected error occurred during upload', 'error')
        return redirect(url_for('upload.upload'))

    return redirect(url_for('upload.upload'))


def allowed_file(filename):
    """Check if the file has an allowed extension"""
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def allowed_file_size(file):
    """Check if the file size is within limits"""
    # Save current position
    start_pos = file.tell()
    # Move to end of file
    file.seek(0, 2)
    size = file.tell()
    # Reset pointer to start
    file.seek(start_pos)
    return size <= MAX_FILE_SIZE