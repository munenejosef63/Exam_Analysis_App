import re
from flask import current_app

class ContactValidator:
    @staticmethod
    def normalize_phone(phone):
        """Standardize phone number format"""
        if not phone:
            return None
        digits = re.sub(r'[^\d+]', '', phone)
        if digits.startswith('0'):
            return '+254' + digits[1:]
        elif digits.startswith('7'):
            return '+254' + digits
        return digits

    @staticmethod
    def is_valid_kenyan_phone(phone):
        pattern = r'^\+2547\d{8}$'
        return bool(re.match(pattern, phone))

    @staticmethod
    def is_valid_email(email):
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))