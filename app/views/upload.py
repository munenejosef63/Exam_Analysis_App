from flask import Blueprint, request, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from app.services.excel_parser import process_exam_upload
from app.models import School  # Assuming you have a School model


upload_bp = Blueprint('upload', __name__)

ALLOWED_EXTENSIONS = {'xlsx', 'xls'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@upload_bp.route('/upload', methods=['POST'])
@login_required
def upload():
    """Handle exam file uploads with validation and processing"""
    # Check if file was uploaded
    if 'file' not in request.files:
        flash('No file uploaded', 'error')
        return redirect(request.url)

    file = request.files['file']

    # Check if file is empty
    if file.filename == '':
        flash('No selected file', 'error')
        return redirect(request.url)

    try:
        # Validate file type
        if not allowed_file(file.filename):
            flash('Only Excel files (.xlsx, .xls) are allowed', 'error')
            return redirect(request.url)

        # Validate file size
        if not allowed_file_size(file):
            flash('File size exceeds maximum limit (10MB)', 'error')
            return redirect(request.url)

        # Get the user's school (assuming teachers are associated with a school)
        school = School.query.get(current_user.school_id)
        if not school:
            flash('School not found', 'error')
            return redirect(request.url)

        # Process the file
        result = process_exam_upload(
            file_stream=file.stream,
            school_id=school.id,
            uploader_id=current_user.id
        )

        if result['status'] == 'error':
            logger.error(f"Upload failed for user {current_user.id}: {result['message']}")
            flash(f'Processing error: {result["message"]}', 'error')
        else:
            logger.info(f"Successfully processed {result['students']} records for school {school.id}")
            flash(f'Successfully processed {result["students"]} student records', 'success')

    except Exception as e:
        db.session.rollback()
        logger.error(f"Upload failed: {str(e)}", exc_info=True)
        flash(f'Upload failed: {str(e)}', 'error')

    return redirect(url_for('dashboard.school_dashboard'))


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