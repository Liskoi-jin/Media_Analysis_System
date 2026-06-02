# web/__init__.py
from web.routes.upload import upload_bp
from web.routes.database import database_bp
from web.routes.reports import reports_bp
from web.routes.note_analysis import note_bp  # 确保这一行存在

__all__ = ['upload_bp', 'database_bp', 'reports_bp', 'note_bp']