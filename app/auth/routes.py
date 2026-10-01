from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.models import db, User, Parent, Student, AuditLog, Institution
from app.security import is_safe_url, generate_password_reset_token, verify_password_reset_token
from app.limiter import limiter

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        if current_user.role == 'ADMIN':
            return redirect(url_for('admin.dashboard'))
        elif current_user.role == 'DRIVER':
            return redirect(url_for('driver.dashboard'))
        elif current_user.role == 'PARENT':
            return redirect(url_for('parent.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        remember = True if request.form.get('remember') else False

        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash('Invalid email address or password. Please try again.', 'danger')
            return render_template('auth/login.html')

        if not user.is_active:
            flash('Your account has been deactivated. Please contact school admin.', 'warning')
            return render_template('auth/login.html')

        if user.role != 'SUPER_ADMIN' and user.institution and not user.institution.is_active:
            flash('Your institution has been deactivated. Access denied.', 'danger')
            return render_template('auth/login.html')

        login_user(user, remember=remember)
        
        # Log Audit event
        log = AuditLog(
            institution_id=user.institution_id,
            user_id=user.id,
            action=f"LOGIN_{user.role}",
            ip_address=request.remote_addr,
            details=f"User {user.email} logged in successfully."
        )
        db.session.add(log)
        db.session.commit()

        flash(f'Welcome back, {user.full_name}!', 'success')
        
        next_page = request.args.get('next')
        # Open Redirect Security Sanitizer
        if next_page and is_safe_url(next_page):
            return redirect(next_page)

        if user.role == 'SUPER_ADMIN':
            return redirect(url_for('superadmin.institutions_list'))
        elif user.role == 'ADMIN':
            return redirect(url_for('admin.dashboard'))
        elif user.role == 'DRIVER':
            return redirect(url_for('driver.dashboard'))
        elif user.role == 'PARENT':
            return redirect(url_for('parent.dashboard'))

    return render_template('auth/login.html')


@auth_bp.route('/register-parent', methods=['GET', 'POST'])
def register_parent():
    if current_user.is_authenticated:
        return redirect(url_for('parent.dashboard'))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        address = request.form.get('address', '').strip()
        emergency_contact = request.form.get('emergency_contact', '').strip()
        relationship = request.form.get('relationship', 'Parent')
        student_invite_code = request.form.get('student_invite_code', '').strip() or request.form.get('invite_code', '').strip()

        if not student_invite_code:
            flash('Student Invite Code is required for guardian registration. Please enter the code provided by your school.', 'danger')
            return render_template('auth/register_parent.html')

        student = Student.query.filter_by(invite_code=student_invite_code).first()
        if not student:
            flash('Invalid Student Invite Code. Please check the code issued by your school administrator.', 'danger')
            return render_template('auth/register_parent.html')

        if student.invite_used:
            flash('This Student Invite Code has already been used. Contact school administration if you need assistance.', 'danger')
            return render_template('auth/register_parent.html')

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('An account with this email address already exists.', 'danger')
            return render_template('auth/register_parent.html')

        try:
            inst_id = student.institution_id if student.institution_id else 1
            new_user = User(
                institution_id=inst_id,
                email=email,
                role='PARENT',
                full_name=full_name,
                phone=phone
            )
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.flush()

            new_parent = Parent(
                institution_id=inst_id,
                user_id=new_user.id,
                address=address,
                emergency_contact=emergency_contact,
                relationship=relationship
            )
            db.session.add(new_parent)
            db.session.flush()

            # Link student to new verified parent profile and mark invite code used
            student.parent_id = new_parent.id
            student.invite_used = True

            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash('Database registration error: Email address or user details already registered.', 'danger')
            return render_template('auth/register_parent.html')

        flash(f'Guardian registration successful! Linked to {student.full_name}. You can now log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register_parent.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out securely.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit("10 per minute", methods=["POST"])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        user = User.query.filter_by(email=email).first()
        if user:
            token = generate_password_reset_token(user.id)
            reset_url = url_for('auth.reset_password', token=token, _external=True)
            flash(f'Password reset link generated for {user.email}: {reset_url}', 'success')
        else:
            flash('If an account exists with that email, a reset link was sent.', 'info')
        return redirect(url_for('auth.login'))
    return render_template('auth/forgot_password.html')


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=["POST"])
def reset_password(token):
    user_id = verify_password_reset_token(token)
    if not user_id:
        flash('The password reset link is invalid or has expired. Please request a new link.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if password != confirm_password:
            flash('Passwords do not match. Please try again.', 'danger')
            return render_template('auth/reset_password.html')

        user.set_password(password)
        db.session.commit()

        flash('Your password has been reset successfully! Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html')
