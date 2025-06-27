# app/services/grading.py
def calculate_grade(marks):
    """Standard grade calculation used across the application"""
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