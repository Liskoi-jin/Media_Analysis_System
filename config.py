# config.py - 完整文件
import os
from datetime import timedelta
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


class Config:
    """应用配置类（所有配置从环境变量读取）"""
    SECRET_KEY = os.environ.get('SECRET_KEY', '')
    PERMANENT_SESSION_LIFETIME = timedelta(seconds=int(os.environ.get('PERMANENT_SESSION_LIFETIME', 86400)))

    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 52428800))
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'uploads')
    ALLOWED_EXTENSIONS = set(os.environ.get('ALLOWED_EXTENSIONS', 'csv,xlsx,xls').split(','))

    OUTPUT_DIR = os.environ.get('OUTPUT_DIR', 'outputs')
    EXCEL_OUTPUT_DIR = os.environ.get('EXCEL_OUTPUT_DIR', 'outputs/excel')
    HTML_OUTPUT_DIR = os.environ.get('HTML_OUTPUT_DIR', 'outputs/html')
    TEMP_DIR = os.environ.get('TEMP_DIR', 'outputs/temp')

    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FILE = os.environ.get('LOG_FILE', 'logs/app.log')

    MEDIA_GROUPS = os.environ.get('MEDIA_GROUPS', '家居媒介组,快消媒介组,数码媒介组,素材组,其他组').split(',')

    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER')
    MAIL_RECIPIENTS = os.environ.get('MAIL_RECIPIENTS', '').split(',')

    SCHEDULE_DAILY_TIME = os.environ.get('SCHEDULE_DAILY_TIME', '08:00')
    SCHEDULE_WEEKLY_DAY = os.environ.get('SCHEDULE_WEEKLY_DAY', 'Monday')
    SCHEDULE_WEEKLY_TIME = os.environ.get('SCHEDULE_WEEKLY_TIME', '09:00')

    REPORT_OUTPUT_DIR = os.environ.get('REPORT_OUTPUT_DIR', 'outputs/reports')
    REPORT_TEMPLATE_DIR = os.environ.get('REPORT_TEMPLATE_DIR', 'web/templates/reports')

    REPORT_DAILY_HOUR = int(os.environ.get('REPORT_DAILY_HOUR', 9))
    REPORT_WEEKLY_DAY = os.environ.get('REPORT_WEEKLY_DAY', 'Monday')
    REPORT_WEEKLY_HOUR = int(os.environ.get('REPORT_WEEKLY_HOUR', 9))

    ABNORMAL_TASK_AUTO_CREATE = os.environ.get('ABNORMAL_TASK_AUTO_CREATE', 'true').lower() == 'true'
    ABNORMAL_TASK_EXPIRY_DAYS = int(os.environ.get('ABNORMAL_TASK_EXPIRY_DAYS', 30))

    NOTE_CPM_GOOD = float(os.environ.get('NOTE_CPM_GOOD', 30))
    NOTE_CPM_MEDIUM = float(os.environ.get('NOTE_CPM_MEDIUM', 50))
    NOTE_CPE_GOOD = float(os.environ.get('NOTE_CPE_GOOD', 5))
    NOTE_CPE_MEDIUM = float(os.environ.get('NOTE_CPE_MEDIUM', 10))
    NOTE_CTR_GOOD = float(os.environ.get('NOTE_CTR_GOOD', 5))
    NOTE_CTR_MEDIUM = float(os.environ.get('NOTE_CTR_MEDIUM', 3))


def create_directories():
    """创建必要的目录"""
    dirs = [
        Config.UPLOAD_FOLDER,
        Config.OUTPUT_DIR,
        Config.EXCEL_OUTPUT_DIR,
        Config.HTML_OUTPUT_DIR,
        Config.TEMP_DIR,
        Config.REPORT_OUTPUT_DIR,
        os.path.dirname(Config.LOG_FILE)
    ]
    for dir_path in dirs:
        os.makedirs(dir_path, exist_ok=True)


create_directories()

# ========== 数据库配置（从环境变量读取，不设默认密码）==========
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', 'ai_media_db'),
    'charset': os.getenv('DB_CHARSET', 'utf8mb4')
}

SECRET_KEY = os.getenv('AUTH_SECRET_KEY', os.getenv('SECRET_KEY', ''))
PERMANENT_SESSION_LIFETIME = 3600 * 24