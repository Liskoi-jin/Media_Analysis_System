# auth/models.py - 修改后的版本
from models import db, User  # 从根目录的models.py导入

def init_db(app):
    """初始化数据库（兼容旧接口）"""
    # 已经由 app_auto.py 统一初始化，这里只保留兼容函数
    with app.app_context():
        db.create_all()
        print("✅ 用户表已创建（若不存在）")