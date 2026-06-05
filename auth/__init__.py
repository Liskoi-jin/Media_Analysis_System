# auth/__init__.py
from auth.views import auth_bp
from models import User  # 从根目录models导入

# 对外暴露蓝图和初始化函数
__all__ = ['auth_bp', 'User', 'init_db']

# 兼容旧代码的init_db函数
def init_db(app):
    """初始化用户表"""
    with app.app_context():
        from models import db
        db.create_all()
        pass