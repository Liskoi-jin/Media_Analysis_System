"""
数据库分析路由 - 处理数据库分析和查询
职责：
1. 接收前端请求
2. 调用数据源获取原始数据
3. 根据选中的小组过滤数据
4. 调用分析器进行分析
5. 保存结果并返回
6. 处理数据导入功能
"""
import decimal
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, make_response, send_file
import pandas as pd
from datetime import datetime
import traceback
import os
import json
import csv
import io
import chardet
import pymysql
from decimal import Decimal
import tempfile

from data_sources.db_source import DBSource
from analyzers import (
    WorkloadAnalyzer, QualityAnalyzer, CostAnalyzer,
    logger, ID_TO_NAME_MAPPING, FLOWER_TO_NAME_MAPPING, NAME_TO_GROUP_MAPPING,
    convert_pandas_types_to_python, normalize_media_name, get_media_group
)
from auth.utils import login_required
from flask import current_app as app
from config import DB_CONFIG
from utils.csv_to_excel import csv_to_excel

database_bp = Blueprint('database', __name__, url_prefix='/database')

# 全局变量存储分析结果
analysis_results = {}
global_analysis_results = {}


def prepare_workload_data(df):
    """
    为工作量数据准备必要的字段
    只做必要的字段映射，不进行任何业务计算
    """
    from analyzers.utils import normalize_media_name
    logger.info("为工作量数据准备字段...")
    df = df.copy()

    # 确保有定档媒介字段
    if '定档媒介' not in df.columns:
        if 'schedule_user_name' in df.columns:
            df['定档媒介'] = df['schedule_user_name']
            logger.info("使用 'schedule_user_name' 作为定档媒介")
        elif 'submit_media_user_name' in df.columns:
            df['定档媒介'] = df['submit_media_user_name']
            logger.info("使用 'submit_media_user_name' 作为定档媒介")
        else:
            df['定档媒介'] = '未知'
            logger.warning("未找到任何媒介字段，使用默认值'未知'")

    # 标准化定档媒介名称（只做名称映射，不计算业务指标）
    if '定档媒介' in df.columns:
        df['定档媒介'] = df['定档媒介'].fillna('未知').astype(str).str.strip()
        df['定档媒介'] = df['定档媒介'].replace(['', 'nan', 'NaN', 'None', 'null'], '未知')
        df['定档媒介'] = df['定档媒介'].apply(normalize_media_name)

    # 添加定档媒介小组
    if '定档媒介小组' not in df.columns:
        df['定档媒介小组'] = df['定档媒介'].apply(get_media_group)

    # 确保有数据类型字段
    if '数据类型' not in df.columns:
        df['数据类型'] = '定档'

    # 确保分析器需要的字段存在
    if 'schedule_user_name' not in df.columns:
        df['schedule_user_name'] = df['定档媒介']
    if 'submit_media_user_id' not in df.columns:
        df['submit_media_user_id'] = ''

    logger.info(f"工作量数据字段准备完成，定档媒介唯一数: {df['定档媒介'].nunique()}")
    logger.info(f"工作量数据小组分布: {df['定档媒介小组'].value_counts().to_dict()}")
    return df


def prepare_quality_data(df):
    """
    为质量数据准备必要的字段
    只做必要的字段映射，不进行任何业务计算
    """
    from analyzers.utils import normalize_media_name
    logger.info("为质量数据准备字段...")
    df = df.copy()

    # 确保有 '定档媒介' 字段
    if '定档媒介' not in df.columns:
        if 'submit_media_user_name' in df.columns:
            df['定档媒介'] = df['submit_media_user_name']
            logger.info("使用 'submit_media_user_name' 作为定档媒介")
        elif 'schedule_user_name' in df.columns:
            df['定档媒介'] = df['schedule_user_name']
            logger.info("使用 'schedule_user_name' 作为定档媒介")
        elif 'submit_media_user_id' in df.columns:
            def map_id_to_name(media_id):
                if pd.isna(media_id):
                    return '未知'
                media_id_str = str(media_id).replace('.0', '')
                return ID_TO_NAME_MAPPING.get(media_id_str, '未知')
            df['定档媒介'] = df['submit_media_user_id'].apply(map_id_to_name)
            logger.info("使用 'submit_media_user_id' 映射为定档媒介")
        else:
            df['定档媒介'] = '未知'
            logger.warning("未找到任何媒介字段，使用默认值'未知'")

    # 标准化定档媒介名称
    if '定档媒介' in df.columns:
        df['定档媒介'] = df['定档媒介'].fillna('未知').astype(str).str.strip()
        df['定档媒介'] = df['定档媒介'].replace(['', 'nan', 'NaN', 'None', 'null'], '未知')
        df['定档媒介'] = df['定档媒介'].apply(normalize_media_name)

    # 添加定档媒介小组
    if '定档媒介小组' not in df.columns:
        df['定档媒介小组'] = df['定档媒介'].apply(get_media_group)

    # 确保有 '定档媒介ID' 字段
    if '定档媒介ID' not in df.columns:
        if 'submit_media_user_id' in df.columns:
            df['定档媒介ID'] = df['submit_media_user_id'].astype(str).str.replace('.0', '')
        else:
            df['定档媒介ID'] = ''

    # 确保有 '对应名字' 字段
    if '对应名字' not in df.columns:
        df['对应名字'] = df['定档媒介']

    # 确保有 '数据类型' 字段
    if '数据类型' not in df.columns:
        df['数据类型'] = '提报'

    # 确保有 '状态' 字段
    if '状态' not in df.columns and 'state' in df.columns:
        df['状态'] = df['state']

    # 确保有 '原始状态' 字段（质量分析器需要）
    if '原始状态' not in df.columns and '状态' in df.columns:
        df['原始状态'] = df['状态']

    # 确保分析器需要的字段存在
    if 'submit_media_user_id' not in df.columns:
        df['submit_media_user_id'] = ''
    if 'submit_media_user_name' not in df.columns:
        df['submit_media_user_name'] = df['定档媒介']
    if 'schedule_user_name' not in df.columns:
        df['schedule_user_name'] = ''

    logger.info(f"质量数据字段准备完成，定档媒介唯一数: {df['定档媒介'].nunique()}")
    logger.info(f"质量数据小组分布: {df['定档媒介小组'].value_counts().to_dict()}")
    return df


def prepare_cost_data(df):
    """
    为成本数据准备必要的字段
    关键修复：保留原始数值，不覆盖已有的成本字段
    """
    from analyzers.utils import normalize_media_name, get_media_group
    logger.info("=" * 50)
    logger.info("为成本数据准备字段...")
    logger.info(f"输入数据行数: {len(df)}")

    if df.empty:
        logger.warning("输入数据为空")
        return df

    df = df.copy()

    # 记录原始字段
    logger.info(f"原始数据列: {list(df.columns)}")

    # 确保有 '定档媒介' 字段
    if '定档媒介' not in df.columns:
        if 'schedule_user_name' in df.columns:
            df['定档媒介'] = df['schedule_user_name']
            logger.info("使用 'schedule_user_name' 作为定档媒介")
        elif 'submit_media_user_name' in df.columns:
            df['定档媒介'] = df['submit_media_user_name']
            logger.info("使用 'submit_media_user_name' 作为定档媒介")
        elif 'submit_media_user_id' in df.columns:
            def map_id_to_name(media_id):
                if pd.isna(media_id):
                    return '未知'
                media_id_str = str(media_id).replace('.0', '')
                return ID_TO_NAME_MAPPING.get(media_id_str, '未知')
            df['定档媒介'] = df['submit_media_user_id'].apply(map_id_to_name)
            logger.info("使用 'submit_media_user_id' 映射为定档媒介")
        else:
            df['定档媒介'] = '未知'
            logger.warning("未找到任何媒介字段，使用默认值'未知'")

    # 标准化定档媒介名称
    if '定档媒介' in df.columns:
        df['定档媒介'] = df['定档媒介'].fillna('未知').astype(str).str.strip()
        df['定档媒介'] = df['定档媒介'].replace(['', 'nan', 'NaN', 'None', 'null'], '未知')
        df['定档媒介'] = df['定档媒介'].apply(normalize_media_name)

    # 添加定档媒介小组
    if '定档媒介小组' not in df.columns:
        df['定档媒介小组'] = df['定档媒介'].apply(get_media_group)

    # 关键修复：不要覆盖已有的数值字段
    # 定义字段映射关系
    field_mapping = {
        '成本': 'cost_amount',
        '报价': 'cooperation_quote',
        '下单价': 'order_amount',
        '返点': 'rebate_amount',
        '互动量': 'interaction_count',
        '阅读量': 'read_count',
        '曝光量': 'exposure_count',
        '粉丝数': 'follower_count'
    }

    # 统计原始数值字段情况
    for cn_field, eng_field in field_mapping.items():
        if eng_field in df.columns:
            non_null = df[eng_field].notna().sum()
            gt_zero = (df[eng_field] > 0).sum()
            if non_null > 0:
                logger.info(f"字段 {eng_field} -> {cn_field}: 非空 {non_null} 条, >0 {gt_zero} 条, 示例值: {df[eng_field].iloc[0] if non_null > 0 else 'N/A'}")

    # 处理数值字段：只映射不存在的字段
    for cn_field, eng_field in field_mapping.items():
        if cn_field not in df.columns:
            if eng_field in df.columns:
                # 如果中文列不存在但英文列存在，进行映射
                df[cn_field] = pd.to_numeric(df[eng_field], errors='coerce').fillna(0.0)
                logger.info(f"映射字段: {eng_field} -> {cn_field}")
            else:
                # 如果都不存在，设为0
                df[cn_field] = 0.0
                logger.warning(f"字段 {cn_field} 和 {eng_field} 都不存在，已设为 0")
        else:
            # 中文列已存在，确保是数值类型
            df[cn_field] = pd.to_numeric(df[cn_field], errors='coerce').fillna(0.0)
            logger.info(f"字段 {cn_field} 已存在，确保为数值类型")

    # 统计处理后的成本字段
    if '成本' in df.columns:
        cost_gt_zero = (df['成本'] > 0).sum()
        logger.info(f"处理后成本字段: 总条数 {len(df)}, 成本>0 {cost_gt_zero} 条")

    # 确保必要的字段存在
    required_fields = [
        '达人昵称', '项目名称', '状态', '达人量级', '笔记类型',
        'schedule_user_name', 'submit_media_user_id', 'submit_media_user_name'
    ]

    # 字段映射（反向映射）
    reverse_mapping = {
        '达人昵称': 'influencer_nickname',
        '项目名称': 'project_name',
        '状态': 'state',
        '达人量级': 'kol_koc_type',
        '笔记类型': 'note_type',
        'schedule_user_name': 'schedule_user_name',
        'submit_media_user_id': 'submit_media_user_id',
        'submit_media_user_name': 'submit_media_user_name'
    }

    for cn_field in required_fields:
        if cn_field not in df.columns:
            eng_field = reverse_mapping.get(cn_field)
            if eng_field and eng_field in df.columns:
                df[cn_field] = df[eng_field]
                logger.info(f"映射字段: {eng_field} -> {cn_field}")
            else:
                if cn_field == '状态':
                    df[cn_field] = 'SCHEDULED'
                else:
                    df[cn_field] = ''
                logger.warning(f"字段 {cn_field} 不存在，已设为默认值")

    # 确保有数据类型字段
    if '数据类型' not in df.columns:
        df['数据类型'] = '定档'

    logger.info(f"成本数据字段准备完成，定档媒介唯一数: {df['定档媒介'].nunique()}")
    logger.info(f"成本数据小组分布: {df['定档媒介小组'].value_counts().to_dict()}")
    logger.info(f"最终数据行数: {len(df)}")
    logger.info("=" * 50)
    return df


def filter_by_selected_groups(df, selected_groups):
    """
    根据选中的小组过滤数据
    :param df: 原始DataFrame
    :param selected_groups: 选中的小组列表
    :return: 过滤后的DataFrame
    """
    if df.empty or not selected_groups:
        return df

    logger.info(f"根据选中的小组过滤数据: {selected_groups}")

    # 确定哪个字段包含小组信息
    group_fields = ['定档媒介小组', '所属小组']
    group_field = None

    for field in group_fields:
        if field in df.columns:
            group_field = field
            break

    if group_field is None:
        logger.warning("数据中未找到小组字段，无法按小组过滤")
        return df

    # 统计过滤前数据
    logger.info(f"过滤前数据行数: {len(df)}")
    logger.info(f"过滤前小组分布: {df[group_field].value_counts().to_dict()}")

    # 过滤数据
    filtered_df = df[df[group_field].isin(selected_groups)].copy()

    # 统计过滤后数据
    logger.info(f"过滤后数据行数: {len(filtered_df)}")
    logger.info(f"过滤后小组分布: {filtered_df[group_field].value_counts().to_dict()}")

    return filtered_df


@database_bp.route('/')
@login_required
def db_analysis_index():
    """数据库分析配置页"""
    # 从 NAME_TO_GROUP_MAPPING 获取小组列表（和上传页面完全一致）
    try:
        # 从映射表中获取所有唯一的小组值
        all_groups = sorted(list(set([
            group for group in NAME_TO_GROUP_MAPPING.values()
            if group and group != '其他组' and group != '未知'
        ])))
        logger.info(f"从映射表获取到的小组列表: {all_groups}")
    except Exception as e:
        logger.warning(f"从映射表获取小组列表失败: {e}，使用默认小组")
        # 使用默认小组（和上传页面一致）
        all_groups = ['家居媒介组', '快消媒介组', '耐消媒介组', '电商媒介组', '户外媒介组']

    return render_template('db_analysis_index.html', all_groups=all_groups, now=datetime.now())


@database_bp.route('/submit', methods=['POST'])
@login_required
def db_analysis_submit():
    """
    处理数据库分析提交
    职责：
    1. 接收前端表单数据
    2. 调用数据源获取原始数据
    3. 根据选中的小组过滤数据
    4. 调用分析器进行分析
    5. 保存结果并返回
    """
    try:
        logger.info("=" * 50)
        logger.info("开始数据库分析处理")

        # ========== 1. 接收前端请求 ==========
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        analysis_modules = request.form.getlist('analysis_modules')
        selected_groups = request.form.getlist('selected_groups[]')  # 获取选中的小组
        use_original_state = request.form.get('use_original_state', 'false') == 'true'

        logger.info(f"接收到的参数:")
        logger.info(f"  开始日期: {start_date}")
        logger.info(f"  结束日期: {end_date}")
        logger.info(f"  分析模块: {analysis_modules}")
        logger.info(f"  选中小组: {selected_groups}")
        logger.info(f"  使用原始状态: {use_original_state}")

        # 验证参数
        if not all([start_date, end_date]):
            flash('请填写日期范围', 'error')
            return redirect('/database')

        if len(analysis_modules) == 0:
            flash('请至少选择一个分析模块', 'error')
            return redirect('/database')

        if start_date > end_date:
            flash('开始日期不能晚于结束日期', 'error')
            return redirect('/database')

        if len(selected_groups) == 0:
            flash('请至少选择一个分析小组', 'error')
            return redirect('/database')

        # ========== 2. 调用数据源获取原始数据 ==========
        logger.info("调用数据源获取原始数据...")
        db_source = DBSource()
        results = {}

        if 'workload' in analysis_modules:
            workload_data = db_source.query_workload_data(start_date, end_date)
            if not workload_data.empty:
                workload_data = prepare_workload_data(workload_data)
                # 根据选中的小组过滤数据
                workload_data = filter_by_selected_groups(workload_data, selected_groups)
            results['workload'] = workload_data
            logger.info(f"  工作量数据: {len(workload_data)} 条")

        if 'quality' in analysis_modules:
            quality_data = db_source.query_quality_data(start_date, end_date)
            if not quality_data.empty:
                quality_data = prepare_quality_data(quality_data)
                # 根据选中的小组过滤数据
                quality_data = filter_by_selected_groups(quality_data, selected_groups)
            results['quality'] = quality_data
            logger.info(f"  质量数据: {len(quality_data)} 条")

        if 'cost' in analysis_modules:
            # 先尝试查询有成本的数据
            cost_data = db_source.query_cost_data(start_date, end_date)

            # 如果查询不到有成本的数据，尝试查询所有数据用于调试
            if cost_data.empty:
                logger.warning("未查询到成本>0的数据，尝试查询所有数据...")
                cost_data = db_source.query_cost_data_without_conditions(start_date, end_date)

                if not cost_data.empty:
                    logger.warning(f"查询到 {len(cost_data)} 条数据，但其中成本>0的只有 {(cost_data['cost_amount'] > 0).sum()} 条")

            if not cost_data.empty:
                cost_data = prepare_cost_data(cost_data)
                # 根据选中的小组过滤数据
                cost_data = filter_by_selected_groups(cost_data, selected_groups)
            results['cost'] = cost_data
            logger.info(f"  成本数据: {len(cost_data)} 条")

        # 检查是否有数据
        total_records = sum(len(df) for df in results.values() if isinstance(df, pd.DataFrame))
        if total_records == 0:
            flash('在指定日期范围内未查询到任何数据', 'warning')
            return redirect('/database')

        # ========== 3. 创建分析ID ==========
        analysis_id = datetime.now().strftime('%Y%m%d%H%M%S')
        logger.info(f"创建分析ID: {analysis_id}")

        # ========== 4. 调用分析器进行分析 ==========
        logger.info("调用分析器进行分析...")
        analysis_results_dict = {}

        # 工作量分析
        if 'workload' in results and not results['workload'].empty:
            logger.info("  执行工作量分析...")
            workload_df = results['workload']
            workload_analyzer = WorkloadAnalyzer(
                df=workload_df,
                known_id_name_mapping=ID_TO_NAME_MAPPING,
                config={"FLOWER_TO_NAME_MAPPING": FLOWER_TO_NAME_MAPPING}
            )
            workload_analysis = workload_analyzer.analyze(top_n=10)
            workload_result = {
                "result": workload_analysis.get('detail', pd.DataFrame()),
                "summary": workload_analysis.get('summary', {}),
                "group_summary": workload_analysis.get('group_summary', pd.DataFrame()),
                "top_media_ranking": workload_analysis.get('top_media_ranking', pd.DataFrame())
            }
            analysis_results_dict['workload'] = workload_result
            logger.info(f"    工作量分析完成，明细数据行数: {len(workload_result['result'])}")

        # 质量分析
        if 'quality' in results and not results['quality'].empty:
            logger.info("  执行工作质量分析...")
            quality_df = results['quality']
            quality_analyzer = QualityAnalyzer(
                df=quality_df,
                known_id_name_mapping=ID_TO_NAME_MAPPING,
                config={"FLOWER_TO_NAME_MAPPING": FLOWER_TO_NAME_MAPPING}
            )
            quality_analysis = quality_analyzer.analyze(use_original_state=use_original_state)
            quality_result = {
                "result": quality_analysis.get('detail', pd.DataFrame()),
                "summary": quality_analysis.get('summary', {}),
                "group_summary": quality_analysis.get('group_summary', pd.DataFrame()),
                "quality_distribution": quality_analysis.get('quality_distribution', pd.DataFrame()),
                "premium_detail": quality_analysis.get('premium_detail', pd.DataFrame()),
                "high_read_detail": quality_analysis.get('high_read_detail', pd.DataFrame())
            }
            analysis_results_dict['quality'] = quality_result
            logger.info(f"    质量分析完成，明细数据行数: {len(quality_result['result'])}")

        # 成本分析
        if 'cost' in results and not results['cost'].empty:
            logger.info("  执行成本分析...")
            cost_df = results['cost']

            # 记录成本数据统计
            if '成本' in cost_df.columns:
                cost_gt_zero = (cost_df['成本'] > 0).sum()
                logger.info(f"  成本数据统计: 总条数 {len(cost_df)}, 成本>0 {cost_gt_zero} 条")

            # 所有业务计算都在 CostAnalyzer 内部完成
            cost_analyzer = CostAnalyzer(cost_df, pd.DataFrame())
            cost_analysis = cost_analyzer.analyze(top_n=10)

            # 获取分析结果
            cost_result = {
                "result": cost_analysis.get('media_detail', pd.DataFrame()),
                "summary": cost_analysis.get('overall_summary', {}),
                "overall_summary": cost_analysis.get('overall_summary', {}),
                "media_detail": cost_analysis.get('media_detail', pd.DataFrame()),
                "group_summary": cost_analysis.get('group_summary', pd.DataFrame()),
                "filtered_summary": cost_analysis.get('filtered_summary', {'筛除总成本': 0, '筛除成本占比': 0}),
                "cost_efficiency_ranking": cost_analysis.get('cost_efficiency_ranking', pd.DataFrame()),
                "detailed_data": cost_analysis.get('detailed_data', cost_df),
                "media_group_workload": cost_analysis.get('media_group_workload', pd.DataFrame()),
                "fixed_media_workload": cost_analysis.get('fixed_media_workload', pd.DataFrame()),
                "fixed_media_cost": cost_analysis.get('fixed_media_cost', pd.DataFrame()),
                "fixed_media_rebate": cost_analysis.get('fixed_media_rebate', pd.DataFrame()),
                "fixed_media_performance": cost_analysis.get('fixed_media_performance', pd.DataFrame()),
                "fixed_media_level": cost_analysis.get('fixed_media_level', pd.DataFrame()),
                "fixed_media_comprehensive": cost_analysis.get('fixed_media_comprehensive', pd.DataFrame()),
                "invalid_data_detail": cost_analysis.get('invalid_data_detail', []),
                "invalid_data_stats": cost_analysis.get('invalid_data_stats', {}),
                "abnormal_data_detail": cost_analysis.get('abnormal_data_detail', []),
                "abnormal_data_stats": cost_analysis.get('abnormal_data_stats', {})
            }
            analysis_results_dict['cost'] = cost_result

            # 记录分析结果统计
            if 'overall_summary' in cost_result:
                summary = cost_result['overall_summary']
                logger.info(f"    成本分析完成: 总数据 {summary.get('总数据条数', 0)} 条, "
                           f"有效数据 {summary.get('有效数据条数', 0)} 条, "
                           f"无效数据 {summary.get('无效数据条数', 0)} 条")

        # ========== 5. 转换数据格式并保存结果 ==========
        logger.info("转换数据格式并保存结果...")

        # 转换Pandas类型为Python原生类型
        converted_results = {}
        for key, result in analysis_results_dict.items():
            converted_result = {}
            for sub_key, sub_data in result.items():
                if isinstance(sub_data, pd.DataFrame) and not sub_data.empty:
                    converted_result[sub_key] = convert_pandas_types_to_python(sub_data)
                else:
                    converted_result[sub_key] = convert_pandas_types_to_python(sub_data)
            converted_results[key] = converted_result

        # 构建完整的分析数据
        analysis_data = {
            'analysis_id': analysis_id,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'start_date': start_date,
            'end_date': end_date,
            'analysis_modules': analysis_modules,
            'selected_groups': selected_groups,  # 保存选中的小组
            'full_result': converted_results,
            'reports': {},
            'config': {
                'use_original_state': use_original_state
            },
            'category': '数据库分析',
            'data_counts': {
                'workload': len(results.get('workload', pd.DataFrame())),
                'quality': len(results.get('quality', pd.DataFrame())),
                'cost': len(results.get('cost', pd.DataFrame()))
            }
        }

        # 保存到内存
        global_analysis_results[analysis_id] = analysis_data
        analysis_results[analysis_id] = analysis_data

        # 保存到JSON文件（持久化）
        result_file_path = os.path.join(
            app.config.get('OUTPUT_DIR', 'outputs'),
            'analysis_results',
            f'{analysis_id}.json'
        )
        os.makedirs(os.path.dirname(result_file_path), exist_ok=True)

        with open(result_file_path, 'w', encoding='utf-8') as f:
            json.dump(convert_pandas_types_to_python(analysis_data), f, ensure_ascii=False, indent=2)

        # ========== 6. 返回结果给前端 ==========
        logger.info(f"✅ 数据库分析完成，分析ID：{analysis_id}")
        logger.info(f"✅ 选中的小组: {selected_groups}")
        logger.info("=" * 50)

        flash('✅ 数据库分析已完成！', 'success')
        return redirect(url_for('reports.dashboard', analysis_id=analysis_id, upload_success=1))

    except Exception as e:
        logger.error(f"❌ 数据库分析失败：{str(e)}", exc_info=True)
        flash(f'❌ 分析失败：{str(e)}', 'error')
        return redirect('/database')


@database_bp.route('/debug-cost/<start_date>/<end_date>')
@login_required
def debug_cost_data(start_date, end_date):
    """调试路由：查看成本数据查询结果"""
    try:
        db_source = DBSource()

        # 查询有成本条件的数据
        cost_data_with_condition = db_source.query_cost_data(start_date, end_date)

        # 查询无成本条件的数据
        cost_data_without_condition = db_source.query_cost_data_without_conditions(start_date, end_date)

        result = {
            'with_condition': {
                'count': len(cost_data_with_condition),
                'columns': list(cost_data_with_condition.columns) if not cost_data_with_condition.empty else []
            },
            'without_condition': {
                'count': len(cost_data_without_condition),
                'columns': list(cost_data_without_condition.columns) if not cost_data_without_condition.empty else []
            }
        }

        if not cost_data_without_condition.empty and 'cost_amount' in cost_data_without_condition.columns:
            result['without_condition']['cost_stats'] = {
                '非空': cost_data_without_condition['cost_amount'].notna().sum(),
                '>0': (cost_data_without_condition['cost_amount'] > 0).sum(),
                '最小值': float(cost_data_without_condition['cost_amount'].min()) if cost_data_without_condition['cost_amount'].notna().any() else 0,
                '最大值': float(cost_data_without_condition['cost_amount'].max()) if cost_data_without_condition['cost_amount'].notna().any() else 0,
                '平均值': float(cost_data_without_condition['cost_amount'].mean()) if cost_data_without_condition['cost_amount'].notna().any() else 0
            }

        return jsonify(result)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ========== 导入功能 ==========

@database_bp.route('/import', methods=['GET', 'POST'])
@login_required
def db_import():
    """
    数据导入页面
    支持将CSV/Excel文件导入到数据库，严格检查完全重复的数据
    """
    if request.method == 'GET':
        return render_template('db_import.html')

    # POST请求 - 处理文件上传和导入
    return _handle_import_file()


# ========== 导入功能辅助函数 ==========

def _handle_import_file():
    """处理导入文件（主逻辑）"""
    temp_files = []
    try:
        # 1. 验证文件
        file, file_ext, error = _validate_import_request()
        if error:
            flash(error['message'], error['level'])
            return redirect(request.url)

        # 2. 获取导入选项
        dry_run = request.form.get('dry_run') == 'on'
        encoding = request.form.get('encoding', 'auto')
        num_format = request.form.get('num_format', '文本格式')
        null_display = request.form.get('null_display', 'NULL')
        width_setting = request.form.get('width_setting', '自动调整')
        fixed_width = request.form.get('fixed_width', '15')
        clean_empty = request.form.get('clean_empty', 'true') == 'true'

        logger.info(f"开始导入文件: {file.filename}, dry_run={dry_run}")

        # 3. 读取数据
        df, temp_excel_path, new_temp_files = _read_import_file(
            file, file_ext, encoding, num_format, null_display,
            width_setting, fixed_width, clean_empty
        )
        temp_files.extend(new_temp_files)

        if df.empty:
            flash('❌ 文件为空或读取失败', 'danger')
            return redirect(request.url)

        # 4. 获取数据库连接和表结构
        conn, valid_columns, error = _get_db_connection_and_columns()
        if error:
            flash(error['message'], error['level'])
            return redirect(request.url)

        # 5. 验证字段
        df_columns = list(df.columns)
        valid_columns_in_file = [col for col in df_columns if col in valid_columns]
        invalid_columns = [col for col in df_columns if col not in valid_columns]

        if invalid_columns:
            logger.warning(f"以下字段在数据库表中不存在，将被忽略: {invalid_columns}")

        if not valid_columns_in_file:
            flash('❌ 文件中没有有效的字段名，请下载模板参考', 'danger')
            return redirect(request.url)

        logger.info(f"有效字段: {len(valid_columns_in_file)} 个")
        logger.info(f"总记录数: {len(df)} 条")

        # 6. 准备唯一键字段和可更新字段
        existing_unique_fields = _get_existing_unique_fields(valid_columns_in_file)
        preserve_fields = ['cooperation_quote', 'order_amount', 'rebate_amount', 'cost_amount']
        updateable_fields = _get_updateable_fields(valid_columns_in_file, existing_unique_fields, preserve_fields)

        logger.info(f"用于匹配的唯一键字段: {existing_unique_fields}")
        logger.info(f"可更新的字段: {updateable_fields}")
        logger.info(f"保留原值的字段(不更新): {preserve_fields}")

        # 7. 执行导入（预览或实际）
        if dry_run:
            result = _execute_dry_run(df, valid_columns_in_file, existing_unique_fields, temp_excel_path)
        else:
            result = _execute_actual_import(
                df, valid_columns_in_file, existing_unique_fields,
                updateable_fields, preserve_fields, conn
            )

        # 8. 保存结果到session
        session['last_import_result'] = result

        # 9. 显示提示信息
        if result['level'] == 'success':
            flash(result['message'], 'success')
        elif result['level'] == 'warning':
            flash(result['message'], 'warning')
        else:
            flash(result['message'], 'danger')

        return redirect(url_for('database.db_import'))

    except Exception as e:
        logger.error(f"导入处理失败: {e}", exc_info=True)
        flash(f'❌ 导入处理失败: {str(e)}', 'danger')
        return redirect(request.url)
    finally:
        # 清理临时文件
        _cleanup_temp_files(temp_files, locals().get('dry_run', False), session)


def _validate_import_request():
    """验证导入请求"""
    if 'file' not in request.files:
        return None, None, {'message': '❌ 请选择要上传的文件', 'level': 'danger'}

    file = request.files['file']
    if file.filename == '':
        return None, None, {'message': '❌ 未选择文件', 'level': 'danger'}

    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in ['.csv', '.xlsx', '.xls']:
        return None, None, {'message': '❌ 请上传CSV或Excel格式文件', 'level': 'danger'}

    return file, file_ext, None


def _read_import_file(file, file_ext, encoding, num_format, null_display, width_setting, fixed_width, clean_empty):
    """读取导入文件"""
    temp_files = []

    # 保存上传的文件
    upload_dir = app.config.get('UPLOAD_FOLDER', 'uploads')
    os.makedirs(upload_dir, exist_ok=True)

    temp_upload_path = os.path.join(upload_dir, f"temp_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
    file.save(temp_upload_path)
    temp_files.append(temp_upload_path)

    # 如果是CSV文件，先转换为Excel
    if file_ext == '.csv':
        logger.info(f"正在将CSV转换为Excel...")

        # 生成临时Excel文件
        temp_excel_path = os.path.join(tempfile.gettempdir(), f'import_{datetime.now().strftime("%Y%m%d%H%M%S")}.xlsx')
        temp_files.append(temp_excel_path)

        # 调用CSV转Excel函数
        success, excel_path, message = csv_to_excel(
            csv_path=temp_upload_path,
            output_path=temp_excel_path,
            encoding=encoding,
            num_format=num_format,
            null_display=null_display,
            width_setting=width_setting,
            fixed_width=float(fixed_width) if fixed_width else 15,
            clean_empty=clean_empty
        )

        if not success:
            raise Exception(f"CSV转换失败: {message}")

        # 读取转换后的Excel
        df = pd.read_excel(temp_excel_path, engine='openpyxl')
        logger.info(f"CSV转换成功，读取到 {len(df)} 行数据")
        return df, temp_excel_path, temp_files

    else:
        # 直接读取Excel文件
        df = pd.read_excel(temp_upload_path, engine='openpyxl' if file_ext == '.xlsx' else 'xlrd')
        logger.info(f"Excel文件读取成功，共 {len(df)} 行，列数: {len(df.columns)}")
        return df, temp_upload_path, temp_files


def _get_db_connection_and_columns():
    """获取数据库连接和表结构"""
    try:
        conn = pymysql.connect(
            host=DB_CONFIG['host'],
            port=DB_CONFIG['port'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            database=DB_CONFIG['database'],
            charset=DB_CONFIG.get('charset', 'utf8mb4'),
            cursorclass=pymysql.cursors.DictCursor
        )

        with conn.cursor() as cursor:
            cursor.execute("DESCRIBE lgc_project_influencer")
            table_columns = [row['Field'] for row in cursor.fetchall()]
            logger.info(f"数据库表字段: {table_columns}")

        return conn, table_columns, None
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")
        return None, None, {'message': f'❌ 数据库连接失败: {str(e)}', 'level': 'danger'}


def _get_existing_unique_fields(valid_columns):
    """获取存在的唯一键字段"""
    unique_key_fields = [
        'id', 'project_influencer_id', 'home_url', 'pgy_url',
        'influencer_id', 'xhs_id', 'influencer_nickname', 'project_id', 'project_name'
    ]
    return [field for field in unique_key_fields if field in valid_columns]


def _get_updateable_fields(valid_columns, existing_unique_fields, preserve_fields):
    """获取可更新的字段"""
    return [col for col in valid_columns
            if col not in existing_unique_fields and col not in preserve_fields]


def _execute_dry_run(df, valid_columns, existing_unique_fields, temp_excel_path):
    """执行预览模式"""
    # 创建预览Excel文件（添加状态列）
    preview_df = df.copy()
    preview_df['导入状态'] = '待处理'
    preview_df['提示'] = '预览模式，数据未实际导入'
    preview_df['唯一键字段'] = ', '.join(existing_unique_fields) if existing_unique_fields else '无唯一键'

    preview_path = os.path.join(tempfile.gettempdir(), f'preview_{datetime.now().strftime("%Y%m%d%H%M%S")}.xlsx')
    preview_df.to_excel(preview_path, index=False, engine='openpyxl')

    return {
        'total_records': len(df),
        'to_insert': len(df),
        'updated': 0,
        'skipped': 0,
        'errors': 0,
        'skipped_records': [],
        'updated_records': [],
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'dry_run': True,
        'has_excel': True,
        'preview_path': preview_path,
        'unique_key_fields': existing_unique_fields,
        'preserve_fields': ['cooperation_quote', 'order_amount', 'rebate_amount', 'cost_amount'],
        'message': f'✅ 预览完成：文件中共 {len(df)} 条记录，将使用 {existing_unique_fields} 作为唯一键',
        'level': 'success'
    }


def _execute_actual_import(df, valid_columns, existing_unique_fields, updateable_fields, preserve_fields, conn):
    """执行实际导入 - 最终修复版：同时检查唯一键和id"""
    to_insert = 0
    updated = 0
    skipped = 0
    errors = 0
    skipped_records = []
    updated_records = []

    try:
        with conn.cursor() as cursor:
            # 如果没有唯一键字段，全部作为新增处理
            if not existing_unique_fields:
                logger.info("无唯一键字段，全部作为新增记录处理")

                # 插入时包含所有字段，包括id
                insert_columns = valid_columns

                if not insert_columns:
                    logger.error("没有可插入的字段")
                    errors = len(df)
                    raise Exception("没有可插入的字段")

                # 构建INSERT语句
                placeholders = ', '.join(['%s'] * len(insert_columns))
                columns_str = ', '.join([f'`{col}`' for col in insert_columns])
                insert_sql = f"INSERT INTO lgc_project_influencer ({columns_str}) VALUES ({placeholders})"

                # 批量插入数据
                batch_size = 100
                current_batch = []

                for index, row in df.iterrows():
                    try:
                        # ========== 关键修复：先检查id是否已存在 ==========
                        id_val = row.get('id')
                        if id_val is not None and not pd.isna(id_val):
                            cursor.execute("SELECT id FROM lgc_project_influencer WHERE id = %s", [id_val])
                            if cursor.fetchone():
                                # id已存在，应该更新而不是插入
                                logger.warning(f"第 {index + 2} 行: id {id_val} 已存在，将尝试更新")

                                # 获取可更新字段的值（所有非id字段）
                                update_fields = [col for col in valid_columns if col != 'id']
                                if update_fields:
                                    update_values = []
                                    for field in update_fields:
                                        val = row.get(field)
                                        if pd.isna(val) or val is None:
                                            update_values.append(None)
                                        else:
                                            if isinstance(val, (int, float, Decimal)):
                                                update_values.append(val)
                                            else:
                                                update_values.append(str(val))

                                    update_sql = f"UPDATE lgc_project_influencer SET {', '.join([f'`{field}` = %s' for field in update_fields])} WHERE id = %s"
                                    cursor.execute(update_sql, update_values + [id_val])
                                    conn.commit()
                                    updated += 1
                                    if updated <= 50:
                                        updated_record = {
                                            'row_num': index + 2,
                                            'unique_key': {'id': id_val},
                                            'action': '更新（id匹配）',
                                            'updated_fields': update_fields
                                        }
                                        updated_records.append(updated_record)
                                continue

                        # 构建插入数据的值列表（包含所有字段）
                        row_values = []
                        for col in insert_columns:
                            val = row.get(col)
                            if pd.isna(val) or val is None:
                                row_values.append(None)
                            else:
                                if isinstance(val, (int, float, Decimal)):
                                    row_values.append(val)
                                else:
                                    row_values.append(str(val))

                        current_batch.append(row_values)

                        if len(current_batch) >= batch_size:
                            cursor.executemany(insert_sql, current_batch)
                            conn.commit()
                            to_insert += len(current_batch)
                            logger.info(f"已批量插入 {to_insert} 条记录")
                            current_batch = []

                    except Exception as e:
                        errors += 1
                        logger.error(f"处理第 {index + 2} 行数据失败: {e}", exc_info=True)
                        continue

                # 插入剩余的数据
                if current_batch:
                    try:
                        cursor.executemany(insert_sql, current_batch)
                        conn.commit()
                        to_insert += len(current_batch)
                        logger.info(f"最后批量插入 {len(current_batch)} 条记录")
                    except Exception as e:
                        errors += len(current_batch)
                        logger.error(f"批量插入剩余数据失败: {e}", exc_info=True)

                logger.info(f"导入完成: 总记录 {len(df)}, 成功新增 {to_insert}, 更新 {updated}, 错误 {errors}")

            else:
                # ========== 有唯一键字段：执行更新或插入 ==========
                logger.info(f"将根据唯一键字段 {existing_unique_fields} 判断是更新还是插入")
                logger.info(f"保留字段(不更新): {preserve_fields}")

                # 插入时包含所有字段，包括id
                insert_columns = valid_columns

                if not insert_columns:
                    logger.error("没有可插入的字段")
                    errors = len(df)
                    raise Exception("没有可插入的字段")

                insert_placeholders = ', '.join(['%s'] * len(insert_columns))
                columns_str = ', '.join([f'`{col}`' for col in insert_columns])
                insert_sql = f"INSERT INTO lgc_project_influencer ({columns_str}) VALUES ({insert_placeholders})"

                # 逐行处理数据
                for index, row in df.iterrows():
                    try:
                        # ========== 关键修复1：先检查id是否已存在 ==========
                        id_val = row.get('id')
                        if id_val is not None and not pd.isna(id_val):
                            cursor.execute("SELECT id FROM lgc_project_influencer WHERE id = %s", [id_val])
                            if cursor.fetchone():
                                # id已存在，应该更新而不是插入
                                logger.debug(f"第 {index + 2} 行: id {id_val} 已存在，将尝试更新")

                                # 获取可更新字段的值（排除保留字段）
                                update_fields = [col for col in valid_columns
                                                if col not in preserve_fields and col != 'id']
                                if update_fields:
                                    update_values = []
                                    for field in update_fields:
                                        val = row.get(field)
                                        if pd.isna(val) or val is None:
                                            update_values.append(None)
                                        else:
                                            if isinstance(val, (int, float, Decimal)):
                                                update_values.append(val)
                                            else:
                                                update_values.append(str(val))

                                    update_sql = f"UPDATE lgc_project_influencer SET {', '.join([f'`{field}` = %s' for field in update_fields])} WHERE id = %s"
                                    cursor.execute(update_sql, update_values + [id_val])
                                    conn.commit()
                                    updated += 1
                                    if updated <= 50:
                                        updated_record = {
                                            'row_num': index + 2,
                                            'unique_key': {'id': id_val},
                                            'action': '更新（id匹配）',
                                            'updated_fields': update_fields
                                        }
                                        updated_records.append(updated_record)
                                else:
                                    # 没有可更新的字段，跳过
                                    skipped += 1
                                    skipped_record = {
                                        'row_num': index + 2,
                                        'unique_key': {'id': id_val},
                                        'reason': '记录已存在且无可更新字段'
                                    }
                                    skipped_records.append(skipped_record)
                                continue

                        # ========== 关键修复2：动态构建WHERE条件，正确处理NULL值 ==========
                        where_clauses = []
                        check_values = []

                        for field in existing_unique_fields:
                            val = row.get(field)
                            if pd.isna(val) or val is None:
                                # 对于NULL值，使用 IS NULL
                                where_clauses.append(f"`{field}` IS NULL")
                            else:
                                # 对于非NULL值，使用 = %s
                                where_clauses.append(f"`{field}` = %s")
                                if isinstance(val, (int, float, Decimal)):
                                    check_values.append(val)
                                else:
                                    check_values.append(str(val))

                        # 检查记录是否存在（通过唯一键）
                        check_sql = f"SELECT id FROM lgc_project_influencer WHERE {' AND '.join(where_clauses)}"
                        cursor.execute(check_sql, check_values)
                        existing_record = cursor.fetchone()
                        exists = existing_record is not None

                        if exists:
                            # ========== 记录存在：执行更新 ==========
                            existing_id = existing_record['id']

                            if updateable_fields:
                                # 获取可更新字段的值
                                update_values = []
                                for field in updateable_fields:
                                    val = row.get(field)
                                    if pd.isna(val) or val is None:
                                        update_values.append(None)
                                    else:
                                        if isinstance(val, (int, float, Decimal)):
                                            update_values.append(val)
                                        else:
                                            update_values.append(str(val))

                                # 构建完整的 UPDATE SQL
                                update_sql = f"UPDATE lgc_project_influencer SET {', '.join([f'`{field}` = %s' for field in updateable_fields])} WHERE id = %s"

                                # 执行更新
                                cursor.execute(update_sql, update_values + [existing_id])
                                conn.commit()
                                updated += 1

                                if updated <= 50:
                                    updated_record = {
                                        'row_num': index + 2,
                                        'unique_key': {field: str(row.get(field)) for field in existing_unique_fields},
                                        'action': '更新（唯一键匹配）',
                                        'updated_fields': updateable_fields,
                                        'id': existing_id
                                    }
                                    updated_records.append(updated_record)
                            else:
                                # 没有可更新的字段，跳过
                                skipped += 1
                                skipped_record = {
                                    'row_num': index + 2,
                                    'unique_key': {field: str(row.get(field)) for field in existing_unique_fields},
                                    'reason': '记录已存在且无可更新字段',
                                    'id': existing_id
                                }
                                skipped_records.append(skipped_record)
                        else:
                            # ========== 记录不存在：执行插入（包含id） ==========
                            # 构建所有字段的值（包含id）
                            row_values = []
                            for col in insert_columns:
                                val = row.get(col)
                                if pd.isna(val) or val is None:
                                    row_values.append(None)
                                else:
                                    if isinstance(val, (int, float, Decimal)):
                                        row_values.append(val)
                                    else:
                                        row_values.append(str(val))

                            # 执行插入
                            cursor.execute(insert_sql, row_values)
                            conn.commit()
                            to_insert += 1

                        # 每100条记录提交一次并打印进度
                        if (to_insert + updated + skipped) % 100 == 0:
                            logger.info(f"已处理 {(to_insert + updated + skipped)} 条记录，新增: {to_insert}, 更新: {updated}, 跳过: {skipped}")

                    except Exception as e:
                        errors += 1
                        logger.error(f"处理第 {index + 2} 行数据失败: {e}", exc_info=True)
                        # 打印行数据摘要
                        try:
                            row_summary = {}
                            for key in ['id', 'influencer_nickname', 'project_name'] + existing_unique_fields[:3]:
                                if key in row and not pd.isna(row.get(key)):
                                    row_summary[key] = str(row.get(key))
                            logger.error(f"  行数据摘要: {row_summary}")
                        except:
                            pass
                        continue

                logger.info(f"导入完成: 总记录 {len(df)}, 新增 {to_insert}, 更新 {updated}, 跳过 {skipped}, 错误 {errors}")

    except Exception as e:
        conn.rollback()
        logger.error(f"导入失败: {e}", exc_info=True)
        raise
    finally:
        conn.close()

    # 构建结果消息
    if errors == 0:
        if updated > 0 and to_insert > 0:
            message = f'✅ 导入完成！总记录 {len(df)} 条，新增 {to_insert} 条，更新 {updated} 条，跳过 {skipped} 条'
            level = 'success'
        elif updated > 0:
            message = f'✅ 导入完成！总记录 {len(df)} 条，更新 {updated} 条，跳过 {skipped} 条'
            level = 'success'
        elif to_insert > 0:
            message = f'✅ 导入完成！成功新增 {to_insert} 条记录，跳过 {skipped} 条'
            level = 'success'
        else:
            message = f'✅ 导入完成！所有 {len(df)} 条记录均已存在且无更新'
            level = 'info'
    else:
        message = f'⚠️ 导入完成但有错误！总记录 {len(df)} 条，新增 {to_insert} 条，更新 {updated} 条，跳过 {skipped} 条，失败 {errors} 条'
        level = 'warning'

    return {
        'total_records': len(df),
        'inserted': to_insert,
        'updated': updated,
        'skipped': skipped,
        'errors': errors,
        'skipped_records': skipped_records[:50],
        'updated_records': updated_records[:50],
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'dry_run': False,
        'has_excel': False,
        'unique_key_fields': existing_unique_fields if existing_unique_fields else ['无唯一键'],
        'preserve_fields': preserve_fields,
        'updateable_fields': updateable_fields,
        'message': message,
        'level': level
    }


def _cleanup_temp_files(temp_files, dry_run, session=None):
    """清理临时文件"""
    for temp_file in temp_files:
        try:
            if os.path.exists(temp_file):
                # 如果是预览文件且是dry_run模式，保留
                if dry_run and session and temp_file == session.get('last_import_result', {}).get('preview_path'):
                    continue
                os.remove(temp_file)
                logger.info(f"已删除临时文件: {temp_file}")
        except Exception as e:
            logger.error(f"删除临时文件失败: {temp_file}, 错误: {e}")


@database_bp.route('/download-preview')
@login_required
def download_preview():
    """下载预览Excel文件"""
    try:
        result = session.get('last_import_result')
        if not result or not result.get('preview_path'):
            flash('❌ 没有可用的预览文件', 'danger')
            return redirect(url_for('database.db_import'))

        preview_path = result['preview_path']
        if not os.path.exists(preview_path):
            flash('❌ 预览文件已过期', 'danger')
            return redirect(url_for('database.db_import'))

        return send_file(
            preview_path,
            as_attachment=True,
            download_name=f'import_preview_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        logger.error(f"下载预览文件失败: {e}", exc_info=True)
        flash(f'❌ 下载失败: {str(e)}', 'danger')
        return redirect(url_for('database.db_import'))


@database_bp.route('/export-template')
@login_required
def db_export_template():
    """导出导入模板CSV"""
    try:
        # 获取表结构
        conn = pymysql.connect(
            host=DB_CONFIG['host'],
            port=DB_CONFIG['port'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            database=DB_CONFIG['database'],
            charset=DB_CONFIG.get('charset', 'utf8mb4'),
            cursorclass=pymysql.cursors.DictCursor
        )

        with conn.cursor() as cursor:
            cursor.execute("DESCRIBE lgc_project_influencer")
            columns = [row['Field'] for row in cursor.fetchall()]

        conn.close()

        # 创建CSV模板（只有表头，没有数据）
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(columns)

        # 创建响应
        response = make_response(output.getvalue())
        response.headers['Content-Disposition'] = f'attachment; filename=lgc_project_influencer_template.csv'
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'

        return response

    except Exception as e:
        logger.error(f"导出模板失败: {e}", exc_info=True)
        flash(f'❌ 导出模板失败: {str(e)}', 'danger')
        return redirect(url_for('database.db_import'))


@database_bp.route('/import/clear-result', methods=['POST'])
@login_required
def clear_import_result():
    """清除上次导入结果"""
    if 'last_import_result' in session:
        # 如果有预览文件，也删除
        preview_path = session['last_import_result'].get('preview_path')
        if preview_path and os.path.exists(preview_path):
            try:
                os.remove(preview_path)
            except:
                pass
        del session['last_import_result']
    return jsonify({'success': True})