"""
工具函数模块 - 提供通用的工具函数和映射表
"""
import logging
import os
import pandas as pd
import numpy as np
from datetime import datetime, date
import re
import unicodedata
from typing import Dict, List, Any, Optional
from flask import current_app

# ========== 日志配置 ==========
logger = logging.getLogger(__name__)
logger.propagate = True

# ========== 全局映射表变量（将从数据库加载）==========
_ID_TO_NAME_MAPPING = {}
_FLOWER_TO_NAME_MAPPING = {}
_NAME_TO_GROUP_MAPPING = {}
_USER_NAME_TO_REAL_NAME_MAPPING = {}  # 用户名到真实姓名的映射

# ========== 导出映射表 ==========
ID_TO_NAME_MAPPING = _ID_TO_NAME_MAPPING
FLOWER_TO_NAME_MAPPING = _FLOWER_TO_NAME_MAPPING
NAME_TO_GROUP_MAPPING = _NAME_TO_GROUP_MAPPING
USER_NAME_TO_REAL_NAME_MAPPING = _USER_NAME_TO_REAL_NAME_MAPPING


def load_mappings_from_db(app=None):
    """
    从数据库加载媒介映射表
    使用正确的字段映射：
    - user_id → 媒介ID
    - nike_name → 真实姓名
    - flower_name → 花名
    - user_name → 用户名
    - dept_name → 部门名称
    """
    global _ID_TO_NAME_MAPPING, _FLOWER_TO_NAME_MAPPING, _NAME_TO_GROUP_MAPPING, _USER_NAME_TO_REAL_NAME_MAPPING

    try:
        # 如果没有传入app，尝试获取当前应用的上下文
        if app is None:
            from flask import current_app
            app = current_app._get_current_object() if current_app else None

        if app is None:
            logger.error("无法获取应用上下文，无法加载数据库映射")
            return False

        # 在应用上下文中导入模型
        with app.app_context():
            from models import MediaPersonnel, db

            # 查询所有启用且未删除的媒介
            medias = MediaPersonnel.query.filter_by(deleted=False, state=1).all()

            if not medias:
                logger.warning("数据库中没有找到媒介数据，映射表将为空")
                return False

            # 清空现有映射
            _ID_TO_NAME_MAPPING.clear()
            _FLOWER_TO_NAME_MAPPING.clear()
            _NAME_TO_GROUP_MAPPING.clear()
            _USER_NAME_TO_REAL_NAME_MAPPING.clear()

            # 构建映射
            for media in medias:
                # user_id → 媒介ID（转换为字符串）
                user_id = str(media.user_id) if media.user_id else None

                # nike_name → 真实姓名（去除空格）
                real_name = media.nike_name.strip() if media.nike_name and media.nike_name.strip() else None
                if real_name:
                    real_name = real_name.replace(' ', '')

                # user_name → 用户名（去除空格）
                user_name = media.user_name.strip() if media.user_name and media.user_name.strip() else None
                if user_name:
                    user_name = user_name.replace(' ', '')

                # flower_name → 花名（去除空格）
                flower_name = media.flower_name.strip() if media.flower_name and media.flower_name.strip() else None
                if flower_name:
                    flower_name = flower_name.replace(' ', '')

                # dept_name → 部门名称（直接使用，作为小组名称）
                dept_name = media.dept_name.strip() if media.dept_name and media.dept_name.strip() else '未分组'
                if dept_name == 'NULL':
                    dept_name = '未分组'

                # ID到真名映射（使用nike_name）
                if user_id and real_name:
                    _ID_TO_NAME_MAPPING[user_id] = real_name

                # 花名到真名映射（flower_name → nike_name）
                if flower_name and real_name:
                    _FLOWER_TO_NAME_MAPPING[flower_name] = real_name

                # 用户名到真名映射（user_name → nike_name）
                if user_name and real_name:
                    _USER_NAME_TO_REAL_NAME_MAPPING[user_name] = real_name

                # 真名到小组映射（nike_name → dept_name）
                if real_name:
                    _NAME_TO_GROUP_MAPPING[real_name] = dept_name

            logger.info(f"✅ 从数据库加载映射表成功：")
            logger.info(f"   ID映射: {len(_ID_TO_NAME_MAPPING)} 条")
            logger.info(f"   花名映射: {len(_FLOWER_TO_NAME_MAPPING)} 条")
            logger.info(f"   用户名映射: {len(_USER_NAME_TO_REAL_NAME_MAPPING)} 条")
            logger.info(f"   小组映射: {len(_NAME_TO_GROUP_MAPPING)} 条")
            logger.info(f"   唯一小组: {sorted(set(_NAME_TO_GROUP_MAPPING.values()))}")

            # 打印示例数据
            if _ID_TO_NAME_MAPPING:
                sample_id = list(_ID_TO_NAME_MAPPING.items())[:3]
                logger.info(f"   ID映射示例: {sample_id}")
            if _FLOWER_TO_NAME_MAPPING:
                sample_flower = list(_FLOWER_TO_NAME_MAPPING.items())[:3]
                logger.info(f"   花名映射示例: {sample_flower}")
            if _USER_NAME_TO_REAL_NAME_MAPPING:
                sample_user = list(_USER_NAME_TO_REAL_NAME_MAPPING.items())[:3]
                logger.info(f"   用户名映射示例: {sample_user}")
            if _NAME_TO_GROUP_MAPPING:
                sample_name = list(_NAME_TO_GROUP_MAPPING.items())[:3]
                logger.info(f"   小组映射示例: {sample_name}")

            return True

    except Exception as e:
        logger.error(f"❌ 从数据库加载映射表失败: {e}", exc_info=True)
        return False


def create_dir_if_not_exist(dir_path):
    """创建目录（如果不存在）"""
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
        logger.info(f"创建目录：{dir_path}")


# ========== 工具函数 ==========

def normalize_media_name(name: str) -> str:
    """
    标准化媒介名称
    使用数据库加载的映射表
    优先顺序：
    1. 花名映射（flower_name）
    2. 用户名映射（user_name）
    3. ID映射
    4. 真实姓名映射
    5. 模糊匹配
    """
    if pd.isna(name) or not isinstance(name, str):
        return '未知'

    name = str(name).strip()
    if not name or name.lower() in ['nan', 'none', 'null', '']:
        return '未知'

    # 去除中间空格，用于匹配
    name_no_spaces = name.replace(' ', '')

    global _FLOWER_TO_NAME_MAPPING, _ID_TO_NAME_MAPPING, _NAME_TO_GROUP_MAPPING, _USER_NAME_TO_REAL_NAME_MAPPING

    # 打印调试信息（仅前20个不同的值）
    if not hasattr(normalize_media_name, '_debug_printed_names'):
        normalize_media_name._debug_printed_names = set()

    if name not in normalize_media_name._debug_printed_names and len(normalize_media_name._debug_printed_names) < 20:
        logger.info(f"normalize_media_name 调试: 正在映射 '{name}'")
        normalize_media_name._debug_printed_names.add(name)

    # ========== 1. 花名映射（精确匹配）==========
    if name in _FLOWER_TO_NAME_MAPPING:
        real_name = _FLOWER_TO_NAME_MAPPING[name]
        logger.debug(f"花名映射: {name} -> {real_name}")
        return real_name

    if name_no_spaces in _FLOWER_TO_NAME_MAPPING:
        real_name = _FLOWER_TO_NAME_MAPPING[name_no_spaces]
        logger.debug(f"花名映射(去空格): {name_no_spaces} -> {real_name}")
        return real_name

    # ========== 2. 用户名映射 ==========
    if name in _USER_NAME_TO_REAL_NAME_MAPPING:
        real_name = _USER_NAME_TO_REAL_NAME_MAPPING[name]
        logger.debug(f"用户名映射: {name} -> {real_name}")
        return real_name

    if name_no_spaces in _USER_NAME_TO_REAL_NAME_MAPPING:
        real_name = _USER_NAME_TO_REAL_NAME_MAPPING[name_no_spaces]
        logger.debug(f"用户名映射(去空格): {name_no_spaces} -> {real_name}")
        return real_name

    # ========== 3. 不区分大小写的花名/用户名映射 ==========
    name_lower = name.lower()
    name_no_spaces_lower = name_no_spaces.lower()

    # 检查花名映射
    for key, value in _FLOWER_TO_NAME_MAPPING.items():
        if key and (key.lower() == name_lower or key.lower() == name_no_spaces_lower):
            logger.debug(f"花名映射(忽略大小写): {key} -> {value}")
            return value

    # 检查用户名映射
    for key, value in _USER_NAME_TO_REAL_NAME_MAPPING.items():
        if key and (key.lower() == name_lower or key.lower() == name_no_spaces_lower):
            logger.debug(f"用户名映射(忽略大小写): {key} -> {value}")
            return value

    # ========== 4. ID映射 ==========
    # 如果是数字ID，尝试ID映射
    if name.replace('.', '').isdigit():
        clean_id = name.replace('.0', '') if name.endswith('.0') else name
        if clean_id in _ID_TO_NAME_MAPPING:
            real_name = _ID_TO_NAME_MAPPING[clean_id]
            logger.debug(f"ID映射: {clean_id} -> {real_name}")
            return real_name

    # ========== 5. 真实姓名映射 ==========
    # 如果已经是真名（在小组映射中），直接返回
    if name in _NAME_TO_GROUP_MAPPING:
        logger.debug(f"已是真实姓名: {name}")
        return name
    if name_no_spaces in _NAME_TO_GROUP_MAPPING:
        logger.debug(f"已是真实姓名(去空格): {name_no_spaces}")
        return name_no_spaces

    # ========== 6. 反向查找（花名映射的值）==========
    for key, value in _FLOWER_TO_NAME_MAPPING.items():
        if value == name or value == name_no_spaces:
            logger.debug(f"反向花名映射: {name} -> {value}")
            return value

    # ========== 7. 反向查找（用户名映射的值）==========
    for key, value in _USER_NAME_TO_REAL_NAME_MAPPING.items():
        if value == name or value == name_no_spaces:
            logger.debug(f"反向用户名映射: {name} -> {value}")
            return value

    # ========== 8. 模糊匹配（包含关系）==========
    # 在花名中查找包含关系
    for key, value in _FLOWER_TO_NAME_MAPPING.items():
        if key and (key in name or name in key):
            logger.debug(f"模糊花名匹配: {name} -> {value}")
            return value

    # 在用户名中查找包含关系
    for key, value in _USER_NAME_TO_REAL_NAME_MAPPING.items():
        if key and (key in name or name in key):
            logger.debug(f"模糊用户名匹配: {name} -> {value}")
            return value

    # 在真实姓名中查找包含关系
    for real_name in _NAME_TO_GROUP_MAPPING.keys():
        if real_name and (real_name in name or name in real_name):
            logger.debug(f"模糊真实姓名匹配: {name} -> {real_name}")
            return real_name

    # ========== 9. 返回原始名称 ==========
    logger.debug(f"未找到映射，返回原始名称: {name}")
    return name


def get_media_group(media_name: str) -> str:
    """
    根据媒介名字获取所属小组
    使用数据库加载的映射表
    """
    if pd.isna(media_name) or not isinstance(media_name, str):
        return '未分组'

    media_name = str(media_name).strip()
    if not media_name or media_name.lower() in ['nan', 'none', 'null', '', '未知']:
        return '未分组'

    global _NAME_TO_GROUP_MAPPING, _FLOWER_TO_NAME_MAPPING, _ID_TO_NAME_MAPPING, _USER_NAME_TO_REAL_NAME_MAPPING

    # 打印调试信息（仅前20个不同的值）
    if not hasattr(get_media_group, '_debug_printed_names'):
        get_media_group._debug_printed_names = set()

    if media_name not in get_media_group._debug_printed_names and len(get_media_group._debug_printed_names) < 20:
        logger.info(f"get_media_group 调试: 正在查找小组 '{media_name}'")
        get_media_group._debug_printed_names.add(media_name)

    # 方法1: 直接通过花名映射到真实姓名，再查小组
    if media_name in _FLOWER_TO_NAME_MAPPING:
        real_name = _FLOWER_TO_NAME_MAPPING[media_name]
        if real_name in _NAME_TO_GROUP_MAPPING:
            group = _NAME_TO_GROUP_MAPPING[real_name]
            if group and group.strip() and group != 'NULL':
                logger.debug(f"花名映射成功: {media_name} -> {real_name} -> {group}")
                return group.strip()

    # 方法2: 通过用户名映射到真实姓名，再查小组
    if media_name in _USER_NAME_TO_REAL_NAME_MAPPING:
        real_name = _USER_NAME_TO_REAL_NAME_MAPPING[media_name]
        if real_name in _NAME_TO_GROUP_MAPPING:
            group = _NAME_TO_GROUP_MAPPING[real_name]
            if group and group.strip() and group != 'NULL':
                logger.debug(f"用户名映射成功: {media_name} -> {real_name} -> {group}")
                return group.strip()

    # 方法3: 去空格后的花名匹配
    media_name_no_spaces = media_name.replace(' ', '')
    if media_name_no_spaces in _FLOWER_TO_NAME_MAPPING:
        real_name = _FLOWER_TO_NAME_MAPPING[media_name_no_spaces]
        if real_name in _NAME_TO_GROUP_MAPPING:
            group = _NAME_TO_GROUP_MAPPING[real_name]
            if group and group.strip() and group != 'NULL':
                logger.debug(f"花名映射成功(去空格): {media_name_no_spaces} -> {real_name} -> {group}")
                return group.strip()

    # 方法4: 去空格后的用户名匹配
    if media_name_no_spaces in _USER_NAME_TO_REAL_NAME_MAPPING:
        real_name = _USER_NAME_TO_REAL_NAME_MAPPING[media_name_no_spaces]
        if real_name in _NAME_TO_GROUP_MAPPING:
            group = _NAME_TO_GROUP_MAPPING[real_name]
            if group and group.strip() and group != 'NULL':
                logger.debug(f"用户名映射成功(去空格): {media_name_no_spaces} -> {real_name} -> {group}")
                return group.strip()

    # 方法5: 不区分大小写的花名匹配
    media_name_lower = media_name.lower()
    for flower_name, real_name in _FLOWER_TO_NAME_MAPPING.items():
        if flower_name and flower_name.lower() == media_name_lower:
            if real_name in _NAME_TO_GROUP_MAPPING:
                group = _NAME_TO_GROUP_MAPPING[real_name]
                if group and group.strip() and group != 'NULL':
                    logger.debug(f"花名映射成功(忽略大小写): {flower_name} -> {real_name} -> {group}")
                    return group.strip()

    # 方法6: 不区分大小写的用户名匹配
    for user_name, real_name in _USER_NAME_TO_REAL_NAME_MAPPING.items():
        if user_name and user_name.lower() == media_name_lower:
            if real_name in _NAME_TO_GROUP_MAPPING:
                group = _NAME_TO_GROUP_MAPPING[real_name]
                if group and group.strip() and group != 'NULL':
                    logger.debug(f"用户名映射成功(忽略大小写): {user_name} -> {real_name} -> {group}")
                    return group.strip()

    # 方法7: 如果已经是真实姓名，直接查小组
    if media_name in _NAME_TO_GROUP_MAPPING:
        group = _NAME_TO_GROUP_MAPPING[media_name]
        if group and group.strip() and group != 'NULL':
            logger.debug(f"真实姓名映射成功: {media_name} -> {group}")
            return group.strip()

    if media_name_no_spaces in _NAME_TO_GROUP_MAPPING:
        group = _NAME_TO_GROUP_MAPPING[media_name_no_spaces]
        if group and group.strip() and group != 'NULL':
            logger.debug(f"真实姓名映射成功(去空格): {media_name_no_spaces} -> {group}")
            return group.strip()

    # 方法8: 尝试通过ID映射
    if media_name.replace('.', '').isdigit():
        clean_id = media_name.replace('.0', '') if media_name.endswith('.0') else media_name
        if clean_id in _ID_TO_NAME_MAPPING:
            real_name = _ID_TO_NAME_MAPPING[clean_id]
            if real_name in _NAME_TO_GROUP_MAPPING:
                group = _NAME_TO_GROUP_MAPPING[real_name]
                if group and group.strip() and group != 'NULL':
                    logger.debug(f"ID映射成功: {clean_id} -> {real_name} -> {group}")
                    return group.strip()

    # 方法9: 模糊匹配
    for real_name, group in _NAME_TO_GROUP_MAPPING.items():
        if real_name and (real_name in media_name or media_name in real_name):
            if group and group.strip() and group != 'NULL':
                logger.debug(f"模糊映射成功: {media_name} 包含/被包含于 {real_name} -> {group}")
                return group.strip()

    # 找不到映射，返回'未分组'
    logger.debug(f"未找到小组映射: {media_name}")
    return '未分组'


def convert_pandas_types_to_python(data):
    """递归转换Pandas/numpy特殊类型为Python原生类型"""
    if isinstance(data, pd.DataFrame):
        if data.empty:
            return []
        try:
            records = data.to_dict('records')
            processed_records = []
            for record in records:
                processed_record = {}
                for key, value in record.items():
                    processed_record[key] = convert_pandas_types_to_python(value)
                processed_records.append(processed_record)
            return processed_records
        except Exception as e:
            logger.error(f"转换DataFrame失败: {e}")
            return []

    elif isinstance(data, pd.Series):
        try:
            data = data.to_dict()
        except:
            return {}

    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            result[key] = convert_pandas_types_to_python(value)
        return result

    elif isinstance(data, (list, tuple)):
        return [convert_pandas_types_to_python(item) for item in data]

    elif isinstance(data, (np.integer, np.int8, np.int16, np.int32, np.int64)):
        return int(data)

    elif isinstance(data, (np.floating, np.float16, np.float32, np.float64)):
        return float(data)

    elif isinstance(data, np.bool_):
        return bool(data)

    elif isinstance(data, np.ndarray):
        return data.tolist()

    elif isinstance(data, (pd.Timestamp, datetime)):
        return data.strftime('%Y-%m-%d %H:%M:%S') if pd.notna(data) else ""

    # 处理 date 类型
    elif isinstance(data, date):
        return data.strftime('%Y-%m-%d')

    # 处理其他可能的日期类型
    elif hasattr(data, 'strftime') and callable(getattr(data, 'strftime')):
        try:
            return data.strftime('%Y-%m-%d %H:%M:%S')
        except:
            return str(data)

    elif pd.isna(data):
        return 0 if isinstance(data, (int, float)) else ""

    return data


def preprocess_percent_str_to_float(percent_str):
    """预处理百分数字符串转浮点型"""
    if not percent_str:
        return 0.0
    if not isinstance(percent_str, str):
        try:
            return float(percent_str)
        except:
            return 0.0
    try:
        num_str = percent_str.replace('%', '').strip()
        return float(num_str) if num_str else 0.0
    except:
        return 0.0


def fill_group_data_fields(group_list):
    """为小组数据补全字段"""
    filled_group = []
    for group in group_list:
        if isinstance(group, dict):
            group['总定档数'] = group.get('总定档数', 0) or 0
            group['总提报数'] = group.get('总提报数', 0) or 0
            group['定档数'] = group.get('定档数', 0) or 0
            group['提报数'] = group.get('提报数', 0) or 0
            group['小组名称'] = group.get('小组名称', '未知小组') or '未知小组'
        filled_group.append(group)
    return filled_group


def fill_cost_data_fields(cost_data_list):
    """为成本数据的每条数据补全字段"""
    filled_cost = []
    cost_fields = [
        '筛除总成本', '筛除成本占比', '筛除达人数量', '筛除发布数量',
        '总成本', '平均成本', '总返点金额', '返点占比',
        '媒介名称', '小组名称', '总发布数', '总达人数',
        '有效发布数', '有效达人数', '成本发挥率'
    ]
    for row in cost_data_list:
        if isinstance(row, dict):
            for field in cost_fields:
                if field not in row or row[field] is None or pd.isna(row[field]):
                    row[field] = 0
        filled_cost.append(row)
    return filled_cost


def read_file_with_auto_encoding(file_path):
    """自动识别编码读取Excel/CSV"""
    if not os.path.exists(file_path):
        logger.error(f"❌ 文件不存在：{file_path}")
        return pd.DataFrame()
    file_ext = os.path.splitext(file_path)[1].lower()
    try:
        if file_ext in ['.xlsx', '.xls']:
            return pd.read_excel(file_path, engine='openpyxl' if file_ext == '.xlsx' else 'xlrd')
        elif file_ext == '.csv':
            encoding_list = ['utf-8-sig', 'gbk', 'gb2312', 'latin-1', 'utf-8']
            for encoding in encoding_list:
                try:
                    return pd.read_csv(file_path, encoding=encoding)
                except:
                    continue
            raise Exception(f"编码不兼容：{os.path.basename(file_path)}")
        else:
            logger.warning(f"⚠️ 不支持的文件格式：{file_ext}")
            return pd.DataFrame()
    except Exception as e:
        logger.error(f"❌ 读取文件失败：{file_path}，错误：{e}")
        return pd.DataFrame()


def secure_filename_cn(filename):
    """兼容中文的安全文件名处理"""
    if not filename:
        return 'unnamed_file'
    filename = unicodedata.normalize('NFKC', filename)
    illegal_chars = r'[\\/:*?"<>|]'
    filename = re.sub(illegal_chars, '_', filename)
    filename = filename.strip()
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:200] + ext
    return filename if filename else 'unnamed_file'


def safe_read_csv(file_path: str, encodings: List[str] = None) -> pd.DataFrame:
    """安全读取CSV文件，尝试多种编码"""
    if encodings is None:
        encodings = ['utf-8', 'gbk', 'gb2312', 'latin1', 'utf-8-sig']
    for encoding in encodings:
        try:
            df = pd.read_csv(file_path, encoding=encoding, engine='python')
            logger.info(f"使用 {encoding} 编码成功读取文件: {os.path.basename(file_path)}")
            return df
        except Exception as e:
            logger.debug(f"编码 {encoding} 读取失败: {str(e)[:100]}")
            continue
    try:
        df = pd.read_csv(file_path, engine='python')
        logger.info(f"使用默认编码成功读取文件: {os.path.basename(file_path)}")
        return df
    except Exception as e:
        logger.error(f"所有编码都读取失败: {str(e)}")
        raise ValueError(f"无法读取CSV文件: {os.path.basename(file_path)}")


def safe_read_excel(file_path: str, engines: List[str] = None) -> pd.DataFrame:
    """安全读取Excel文件，尝试多种引擎"""
    if engines is None:
        engines = ['openpyxl', 'xlrd']
    for engine in engines:
        try:
            df = pd.read_excel(file_path, engine=engine)
            logger.info(f"使用 {engine} 引擎成功读取Excel文件: {os.path.basename(file_path)}")
            return df
        except Exception as e:
            logger.debug(f"引擎 {engine} 读取失败: {str(e)[:100]}")
            continue
    logger.error(f"所有引擎都读取Excel失败: {os.path.basename(file_path)}")
    raise ValueError(f"无法读取Excel文件: {os.path.basename(file_path)}")


def read_data_file(file_path: str, data_type: str = None) -> pd.DataFrame:
    """智能读取数据文件（支持CSV和Excel），并添加数据类型标记"""
    ext = file_path.rsplit('.', 1)[1].lower() if '.' in file_path else ''
    if ext in ['csv']:
        df = safe_read_csv(file_path)
    elif ext in ['xlsx', 'xls']:
        df = safe_read_excel(file_path)
    else:
        raise ValueError(f"不支持的文件格式: {ext}")
    if data_type:
        df['数据类型'] = data_type
    else:
        file_name = os.path.basename(file_path).lower()
        if '定档' in file_name:
            df['数据类型'] = '定档'
        elif '提报' in file_name:
            df['数据类型'] = '提报'
        else:
            df['数据类型'] = '未知'
    logger.info(f"文件 {os.path.basename(file_path)} 已标记为 {df['数据类型'].iloc[0]} 数据")
    return df


def clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """清理列名：去除空格、特殊字符"""
    df = df.copy()
    rename_dict = {}
    for col in df.columns:
        if isinstance(col, str):
            new_col = col.strip()
            new_col = new_col.replace('（', '(').replace('）', ')')
            new_col = re.sub(r'[^\w\u4e00-\u9fff()（）]', '_', new_col)
            new_col = new_col.strip('_')
            if new_col != col:
                rename_dict[col] = new_col
    if rename_dict:
        df = df.rename(columns=rename_dict)
        logger.debug(f"清理列名: {list(rename_dict.values())[:10]}...")
    return df


def calculate_percentage(numerator: float, denominator: float, default: float = 0.0) -> float:
    """安全计算百分比"""
    if denominator == 0 or pd.isna(denominator):
        return default
    return (numerator / denominator) * 100


def format_number(value: Any, decimals: int = 2, as_percentage: bool = False) -> str:
    """格式化数字显示"""
    if pd.isna(value):
        return 'N/A'
    if as_percentage:
        return f"{value:.{decimals}f}%"
    elif isinstance(value, float):
        return f"{value:.{decimals}f}"
    else:
        return f"{value:,}"


def validate_dataframe(df: pd.DataFrame, required_columns: List[str] = None) -> bool:
    """验证DataFrame是否包含必需的列"""
    if df.empty:
        logger.warning("DataFrame为空")
        return False
    if required_columns:
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            logger.warning(f"缺少必需的列: {missing_columns}")
            return False
    return True


def deduplicate_dataframe(df: pd.DataFrame, subset: List[str] = None, keep: str = 'first') -> pd.DataFrame:
    """去重DataFrame"""
    if subset:
        return df.drop_duplicates(subset=subset, keep=keep)
    else:
        return df.drop_duplicates(keep=keep)


# ========== 导出映射表变量 ==========
__all__ = [
    'logger',
    'normalize_media_name',
    'get_media_group',
    'ID_TO_NAME_MAPPING',
    'FLOWER_TO_NAME_MAPPING',
    'NAME_TO_GROUP_MAPPING',
    'USER_NAME_TO_REAL_NAME_MAPPING',
    'convert_pandas_types_to_python',
    'preprocess_percent_str_to_float',
    'fill_group_data_fields',
    'fill_cost_data_fields',
    'read_file_with_auto_encoding',
    'secure_filename_cn',
    'load_mappings_from_db'
]