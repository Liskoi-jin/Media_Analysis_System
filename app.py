"""
媒介自动化审计分析系统 - 主应用
整合工作量、工作质量、成本三大分析模块 + 笔记分析模块
提供Web交互界面（兼容中文文件名+编码自动适配+去重上传+完整异常兜底）
"""
import logging
import os
from flask import Flask, render_template, redirect, url_for, session, g, send_from_directory
from datetime import datetime

# ========== 一次性日志配置 ==========
def setup_logging_once():
    """一次性日志配置，避免重复输出"""
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    root_logger.setLevel(logging.INFO)

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)
    root_logger.propagate = False
    return root_logger

root_logger = setup_logging_once()
logger = logging.getLogger(__name__)
logger.info("✅ 日志系统配置完成")

# ========== 导入模块 ==========
from models import db
from auth import auth_bp, init_db as init_auth_db
from auth.utils import login_required
from media import media_bp
from web.routes import upload_bp, database_bp, reports_bp, note_bp
from flask_bcrypt import Bcrypt
from analyzers.utils import load_mappings_from_db

# ========== 初始化应用 ==========
app = Flask(__name__)
bcrypt = Bcrypt(app)

# ========== 加载配置 ==========
app.config.from_object('config.Config')
app.config['SECRET_KEY'] = app.config.get('SECRET_KEY', 'media-audit-2025-secure-key')

# ========== 数据库配置 ==========
from config import DB_CONFIG
app.config['SQLALCHEMY_DATABASE_URI'] = f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}?charset={DB_CONFIG['charset']}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# ========== 初始化认证模块 ==========
init_auth_db(app)

# ========== 注册蓝图 ==========
app.register_blueprint(auth_bp)
app.register_blueprint(media_bp)
app.register_blueprint(upload_bp)
app.register_blueprint(database_bp)
app.register_blueprint(reports_bp)
app.register_blueprint(note_bp)  # 注册笔记分析蓝图

# ========== 创建必要目录 ==========
def create_directories():
    """创建必要的目录"""
    dirs = [
        app.config.get('UPLOAD_FOLDER', 'uploads'),
        app.config.get('OUTPUT_DIR', 'outputs'),
        os.path.join(app.config.get('OUTPUT_DIR', 'outputs'), 'analysis_results'),
        os.path.join(app.config.get('OUTPUT_DIR', 'outputs'), 'logs'),
        os.path.join(app.config.get('OUTPUT_DIR', 'outputs'), 'reports'),
        os.path.join(app.config.get('OUTPUT_DIR', 'outputs'), 'excel'),
        os.path.join(app.config.get('OUTPUT_DIR', 'outputs'), 'note_analysis_results'),  # 笔记分析结果目录
    ]
    for dir_path in dirs:
        os.makedirs(dir_path, exist_ok=True)
        logger.info(f"📂 目录创建成功：{dir_path}")

create_directories()

# ========== 加载媒介映射表 ==========
@app.before_request
def load_mappings():
    """在每个请求前确保映射表已加载"""
    # 只在第一次请求时加载
    if not hasattr(app, '_mappings_loaded'):
        with app.app_context():
            success = load_mappings_from_db(app)
            if success:
                logger.info("✅ 媒介映射表加载成功")
            else:
                logger.warning("⚠️ 媒介映射表加载失败，请检查数据库")
            app._mappings_loaded = True

# ========== 上下文处理器 ==========
@app.context_processor
def inject_common_variables():
    """注入全局通用变量到所有模板"""
    now = datetime.now()
    return {
        'current_year': now.year,
        'current_date': now.strftime('%Y-%m-%d'),
        'current_datetime': now.strftime('%Y-%m-%d %H:%M:%S'),
        'app': app,
        'has_endpoint': lambda endpoint: endpoint in app.view_functions
    }

# ========== 全局过滤器 ==========
@app.template_filter('format_number')
def format_number_filter(value, decimal_places=2):
    """Jinja2过滤器：格式化数字"""
    try:
        if value is None or value == '':
            return f"0.{'0' * decimal_places}"
        import pandas as pd
        if pd.isna(value):
            return f"0.{'0' * decimal_places}"
        num = float(value)
        return f"{num:.{decimal_places}f}"
    except (ValueError, TypeError, Exception):
        return f"0.{'0' * decimal_places}"

@app.template_filter('safe_min')
def safe_min_filter(value, min_val):
    """安全最小值过滤器"""
    try:
        val = float(value) if value else 0.0
        minv = float(min_val) if min_val else 0.0
        return min(val, minv)
    except:
        return min_val

@app.template_filter('format_percentage')
def format_percentage_filter(value, default='0.00%'):
    """格式化百分比"""
    try:
        if value is None:
            return default
        import pandas as pd
        if pd.isna(value):
            return default
        if isinstance(value, (int, float)):
            return f"{value:.2f}%"
        if isinstance(value, str):
            if '%' in value:
                return value
            try:
                num = float(value)
                return f"{num:.2f}%"
            except:
                return default
        return default
    except:
        return default

# ========== 根路由 ==========
@app.route('/')
def root_redirect():
    """根路径重定向到数据来源选择页"""
    return redirect(url_for('reports.data_source_selector'))

# ========== favicon路由 ==========
@app.route('/favicon.ico')
def favicon():
    """返回favicon.ico文件"""
    try:
        return send_from_directory(
            os.path.join(app.root_path, 'static'),
            'favicon.ico',
            mimetype='image/vnd.microsoft.icon'
        )
    except Exception as e:
        logger.warning(f"favicon.ico 文件不存在或无法访问: {e}")
        return '', 204

# ========== 错误处理 ==========
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    error_msg = f"❌ 服务器内部错误：{str(e)}"
    logger.error(error_msg, exc_info=True)
    return render_template('500.html', error_message=error_msg), 500

# ========== 主题配置 ==========
@app.context_processor
def inject_theme_config():
    """注入主题配置到模板"""
    return {
        'theme_config': {
            'default_theme': 'light',
            'themes': ['light', 'dark']
        }
    }

# ========== 应用入口 ==========
if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("🚀 LG-DBM系统 启动成功")
    logger.info(f"🌐 服务访问地址：http://0.0.0.0:5000")
    logger.info(f"📂 上传目录：{app.config.get('UPLOAD_FOLDER', 'uploads')}")
    logger.info(f"📤 输出目录：{app.config.get('OUTPUT_DIR', 'outputs')}")
    logger.info("📊 分析模块：工作量分析、质量分析、成本分析、笔记分析")
    logger.info("=" * 50)

    # 启动前加载映射表
    with app.app_context():
        success = load_mappings_from_db(app)
        if success:
            logger.info("✅ 媒介映射表加载成功")
        else:
            logger.warning("⚠️ 媒介映射表加载失败，请检查数据库")

    app.run(
        host='0.0.0.0',
        port=5000,
        debug=app.config.get('DEBUG', True),
        threaded=True,
        use_reloader=False  # 设为False避免重载时重复加载
    )