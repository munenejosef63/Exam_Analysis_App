from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, current_app
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from app.models import School, Payment, db
import stripe

payment_bp = Blueprint('payment', __name__)


@payment_bp.route('/payment', methods=['GET', 'POST'])
@login_required
def payment():
    if current_user.role != 'school_admin':
        flash('Only school administrators can make payments', 'danger')
        return redirect(url_for('dashboard.dashboard'))

    # Set Stripe API key from Flask config
    stripe.api_key = current_app.config['STRIPE_SECRET_KEY']

    school = current_user.school

    if request.method == 'POST':
        payment_method = request.form.get('payment_method')
        subscription_type = request.form.get('subscription_type')

        if payment_method == 'stripe':
            token = request.form.get('stripeToken')
            amount = 10000 if subscription_type == 'annual' else 1000  # in cents

            try:
                charge = stripe.Charge.create(
                    amount=amount,
                    currency='usd',
                    description=f'{subscription_type} subscription for {school.name}',
                    source=token
                )

                expiry_date = datetime.utcnow() + timedelta(days=365 if subscription_type == 'annual' else 30)
                school.subscription_type = subscription_type
                school.subscription_expiry = expiry_date
                school.is_active = True

                payment = Payment(
                    school_id=school.id,
                    amount=amount / 100,
                    payment_method='stripe',
                    transaction_id=charge.id,
                    status='completed',
                    subscription_period=subscription_type
                )
                db.session.add(payment)
                db.session.commit()

                flash('Payment successful! Your subscription is now active.', 'success')
                return redirect(url_for('dashboard.school_dashboard'))

            except stripe.error.StripeError as e:
                flash(f'Payment failed: {str(e)}', 'danger')

        elif payment_method == 'mpesa':
            flash('Mpesa payment initiated. Complete payment on your phone.', 'info')
            return redirect(url_for('payment.mpesa_callback'))

    return render_template('payment.html', school=school, stripe_key=current_app.config['STRIPE_PUBLISHABLE_KEY'])


@payment_bp.route('/mpesa-callback', methods=['POST'])
def mpesa_callback():
    school_id = request.json.get('school_id')
    amount = request.json.get('amount')
    subscription_type = 'annual' if amount == 10000 else 'monthly'

    school = School.query.get(school_id)
    if school:
        expiry_date = datetime.utcnow() + timedelta(days=365 if subscription_type == 'annual' else 30)
        school.subscription_type = subscription_type
        school.subscription_expiry = expiry_date
        school.is_active = True

        payment = Payment(
            school_id=school.id,
            amount=amount / 100,
            payment_method='mpesa',
            transaction_id=request.json.get('mpesa_code'),
            status='completed',
            subscription_period=subscription_type
        )
        db.session.add(payment)
        db.session.commit()

        return jsonify({'status': 'success'})

    return jsonify({'status': 'error', 'message': 'School not found'}), 404