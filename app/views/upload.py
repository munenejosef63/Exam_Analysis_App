from flask import Blueprint, request, flash
from app import process_exam_upload
from app import ContactValidator

upload_bp = Blueprint('upload', __name__)


@upload_bp.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        flash('No file uploaded', 'error')
        return redirect(request.url)

    file = request.files['file']
    if file.filename == '':
        flash('No selected file', 'error')
        return redirect(request.url)

    try:
        # Validate file type
        if not allowed_file(file.filename):
            flash('Only Excel files are allowed', 'error')
            return redirect(request.url)

        # Process upload
        result = process_exam_upload(file.stream)
        flash(f'Successfully uploaded {result["students"]} records', 'success')

    except Exception as e:
        current_app.logger.error(f"Upload failed: {str(e)}")
        flash(f'Upload failed: {str(e)}', 'error')

    return redirect(url_for('dashboard.school_dashboard'))


def allowed_file(filename):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in ['xlsx', 'xls']