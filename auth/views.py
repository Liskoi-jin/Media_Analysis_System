# auth/views.py - 修复模板路径

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from flask_login import login_user, logout_user, login_required as flask_login_required
from auth.models import db, User
from auth.utils import login_required, admin_required, get_current_user
from config import SECRET_KEY
import os

# 修改蓝图模板路径 - 使用绝对路径或正确的相对路径
template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'web', 'templates')
auth_bp = Blueprint('auth', __name__, url_prefix='/auth', template_folder=template_dir)

# 或者更简单的方式：不使用 template_folder，让 Flask 自动查找
# auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """登录视图"""
    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password').strip()

        if not username or not password:
            flash('账号和密码不能为空', 'danger')
            return render_template('auth/login.html', username=username)

        user = User.query.filter_by(username=username).first()

        if not user:
            flash('账号不存在', 'danger')
            return render_template('auth/login.html', username=username)
        if not user.is_active():
            flash('账号已被禁用，请联系管理员', 'danger')
            return render_template('auth/login.html', username=username)
        if not user.check_password(password):
            flash('密码错误', 'danger')
            return render_template('auth/login.html', username=username)

        session['user_id'] = user.id
        session['username'] = user.username
        session['role'] = user.role

        # 修改跳转路径为 reports.data_source_selector
        next_page = request.args.get('next', url_for('reports.data_source_selector'))
        flash(f'登录成功，欢迎回来，{user.full_name or user.username}', 'success')
        return redirect(next_page)

    return render_template('auth/login.html')


@auth_bp.route('/logout')
def logout():
    """退出登录"""
    session.clear()
    flash('已成功退出登录', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/user-manage')
@admin_required
def user_manage():
    """账号列表管理"""
    users = User.query.order_by(User.create_time.desc()).all()
    return render_template('auth/user_manage.html', users=users)


@auth_bp.route('/add-user', methods=['GET', 'POST'])
@admin_required
def add_user():
    """新增用户账号"""
    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password').strip()
        full_name = request.form.get('full_name').strip()
        email = request.form.get('email').strip()
        phone = request.form.get('phone').strip()
        role = request.form.get('role', 'user')
        status = 1 if request.form.get('status') == 'on' else 0

        if not username or not password:
            flash('账号和密码不能为空', 'danger')
            return render_template('auth/add_user.html',
                                   username=username, full_name=full_name,
                                   email=email, phone=phone, role=role)

        if User.query.filter_by(username=username).first():
            flash('该账号已存在，请更换账号名', 'danger')
            return render_template('auth/add_user.html',
                                   username=username, full_name=full_name,
                                   email=email, phone=phone, role=role)

        try:
            new_user = User(
                username=username,
                password=password,
                full_name=full_name,
                email=email,
                phone=phone,
                role=role,
                status=status
            )
            db.session.add(new_user)
            db.session.commit()
            flash('账号开通成功', 'success')
            return redirect(url_for('auth.user_manage'))
        except Exception as e:
            db.session.rollback()
            flash(f'账号开通失败：{str(e)}', 'danger')
            return render_template('auth/add_user.html',
                                   username=username, full_name=full_name,
                                   email=email, phone=phone, role=role)

    return render_template('auth/add_user.html')


@auth_bp.route('/edit-user/<int:user_id>', methods=['GET', 'POST'])
@admin_required
def edit_user(user_id):
    """编辑已有用户"""
    user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        full_name = request.form.get('full_name').strip()
        email = request.form.get('email').strip()
        phone = request.form.get('phone').strip()
        role = request.form.get('role', 'user')
        status = 1 if request.form.get('status') == 'on' else 0
        new_password = request.form.get('new_password').strip()

        try:
            user.full_name = full_name
            user.email = email
            user.phone = phone
            user.role = role
            user.status = status

            if new_password:
                user.password = new_password  # User模型的password setter会自动处理加密

            db.session.commit()
            flash('用户信息更新成功', 'success')
            return redirect(url_for('auth.user_manage'))
        except Exception as e:
            db.session.rollback()
            flash(f'用户信息更新失败：{str(e)}', 'danger')
            return render_template('auth/edit_user.html', user=user)

    return render_template('auth/edit_user.html', user=user)


@auth_bp.route('/delete-user/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    """删除用户"""
    user = User.query.get_or_404(user_id)

    if user.is_admin():
        flash('管理员账号不能删除', 'danger')
        return redirect(url_for('auth.user_manage'))

    try:
        db.session.delete(user)
        db.session.commit()
        flash('用户删除成功', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'用户删除失败：{str(e)}', 'danger')

    return redirect(url_for('auth.user_manage'))