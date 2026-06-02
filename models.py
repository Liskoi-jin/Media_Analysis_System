# models.py - 完全复制原文件
"""
统一的数据库模型文件
包含所有模块的数据库模型
"""
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class User(db.Model):
    """用户表 - 对应 sys_user"""
    __tablename__ = 'sys_user'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment='用户ID')
    username = db.Column(db.String(50), unique=True, nullable=False, comment='登录账号')
    _password_hash = db.Column('password', db.String(100), nullable=False, comment='加密密码')
    full_name = db.Column(db.String(50), default='', comment='用户姓名')
    email = db.Column(db.String(100), default='', comment='邮箱')
    phone = db.Column(db.String(20), default='', comment='手机号')
    role = db.Column(db.String(20), default='user', comment='角色')
    status = db.Column(db.SmallInteger, default=1, comment='状态：1启用/0禁用')
    create_time = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    def __init__(self, username, password, full_name='', email='', phone='', role='user', status=1):
        self.username = username
        self.password = password
        self.full_name = full_name
        self.email = email
        self.phone = phone
        self.role = role
        self.status = status

    @property
    def password(self):
        raise AttributeError('密码不可读')

    @password.setter
    def password(self, plain_password):
        from flask_bcrypt import generate_password_hash
        self._password_hash = generate_password_hash(plain_password).decode('utf-8')

    def check_password(self, plain_password):
        from flask_bcrypt import check_password_hash
        try:
            return check_password_hash(self._password_hash, plain_password)
        except Exception as e:
            print(f"密码验证错误: {e}")
            return False

    def is_admin(self):
        return self.role == 'admin'

    def is_active(self):
        return self.status == 1

    def __repr__(self):
        return f'<User {self.username}>'


class MediaPersonnel(db.Model):
    """媒介人员表 - 对应 lgc_media_personnel"""
    __tablename__ = 'lgc_media_personnel'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment='主键ID')
    user_id = db.Column(db.BigInteger, nullable=False, comment='用户ID')
    user_name = db.Column(db.String(50), nullable=False, comment='用户名')
    wechat_user_id = db.Column(db.String(64), comment='企业微信userid')
    nike_name = db.Column(db.String(50), comment='昵称')
    flower_name = db.Column(db.String(64), comment='花名')
    media_tag = db.Column(db.String(64), comment='媒介标签')
    dept_id = db.Column(db.BigInteger, comment='部门ID')
    parent_dept_id = db.Column(db.BigInteger, comment='上级部门ID')
    dept_name = db.Column(db.String(100), comment='部门名称')
    parent_dept_name = db.Column(db.String(100), comment='上级部门名称')
    post_id = db.Column(db.BigInteger, comment='岗位ID')
    post_name = db.Column(db.String(100), comment='岗位名称')
    state = db.Column(db.SmallInteger, nullable=False, default=1, comment='状态（1-启用，0-禁用）')
    creator = db.Column(db.String(64), comment='创建者')
    create_time = db.Column(db.DateTime, nullable=False, default=datetime.now, comment='创建时间')
    updater = db.Column(db.String(64), default='', comment='更新者')
    update_time = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now,
                            comment='更新时间')
    deleted = db.Column(db.Boolean, nullable=False, default=False, comment='是否删除')
    tenant_id = db.Column(db.BigInteger, nullable=False, default=0, comment='租户编号')
    linked_influencer_count = db.Column(db.Integer, default=0, comment='关联达人数量')
    total_bd = db.Column(db.Integer, default=0, comment='累计BD')
    total_submissions = db.Column(db.Integer, default=0, comment='累计提报')
    total_scheduled = db.Column(db.Integer, default=0, comment='累计定档')
    avg_cpm = db.Column(db.Numeric(10, 2), default=0.00, comment='平均CPM')
    avg_cpe = db.Column(db.Numeric(10, 2), default=0.00, comment='平均CPE')
    avg_cost = db.Column(db.Numeric(10, 2), default=0.00, comment='平均成本')
    valid_submission_rate = db.Column(db.Numeric(5, 2), default=0.00, comment='有效提报率')
    valid_scheduled_rate = db.Column(db.Numeric(5, 2), default=0.00, comment='有效定档率')
    timely_fill_rate = db.Column(db.Numeric(5, 2), default=0.00, comment='及时回填率')
    ad_selection_rate = db.Column(db.Numeric(5, 2), default=0.00, comment='投流选中率')
    interaction_rate_per_hundred = db.Column(db.Numeric(5, 2), default=0.00, comment='百互动率')
    interaction_rate_per_thousand = db.Column(db.Numeric(5, 2), default=0.00, comment='千互动率')

    def get_real_name(self):
        """获取真实姓名（优先使用nike_name，其次是user_name）"""
        if self.nike_name and self.nike_name.strip():
            return self.nike_name.strip()
        if self.user_name and self.user_name.strip():
            return self.user_name.strip()
        return '未知'

    def get_flower_name(self):
        """获取花名"""
        return self.flower_name.strip() if self.flower_name else ''

    def get_group_name(self):
        """获取小组名称（根据dept_name映射）"""
        if not self.dept_name or not self.dept_name.strip():
            return '其他组'

        dept = self.dept_name.strip()
        if '家居' in dept:
            return '家居媒介组'
        elif '快消' in dept:
            return '快消媒介组'
        elif '数码' in dept or '3C' in dept:
            return '数码媒介组'
        elif '素材' in dept:
            return '素材组'
        else:
            return '其他组'

    def __repr__(self):
        return f'<MediaPersonnel {self.user_name}>'