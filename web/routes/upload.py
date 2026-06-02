"""
上传分析路由 - 处理文件上传和分析
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, g, jsonify
import os
import pandas as pd
import json
from datetime import datetime
import traceback

from analyzers import (
    WorkloadAnalyzer, QualityAnalyzer, CostAnalyzer,
    logger, ID_TO_NAME_MAPPING, FLOWER_TO_NAME_MAPPING, NAME_TO_GROUP_MAPPING,
    convert_pandas_types_to_python, read_file_with_auto_encoding, secure_filename_cn,
    normalize_media_name, get_media_group
)
from data_sources.file_source import FileSource
from auth.utils import login_required
from flask import current_app as app

upload_bp = Blueprint('upload', __name__, url_prefix='/upload')

analysis_results = {}
global_analysis_results = {}


def basic_field_mapping(df, mapping_dict):
    """基础字段映射函数"""
    df = df.copy()
    for old_col, new_col in mapping_dict.items():
        if old_col in df.columns and new_col not in df.columns:
            df[new_col] = df[old_col]
            logger.debug(f"映射字段: {old_col} -> {new_col}")
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


def prepare_workload_data(df):
    """为工作量数据准备必要的字段 - 极简版"""
    logger.info("为工作量数据准备字段...")
    df = df.copy()

    # 字段映射
    mapping = {
        'influencer_nickname': '达人昵称',
        'project_name': '项目名称',
        'schedule_user_name': 'schedule_user_name',
        'submit_media_user_id': 'submit_media_user_id',
        'submit_media_user_name': 'submit_media_user_name',
        'state': '状态',
        'follower_count': '粉丝数',
        'cooperation_quote': '报价',
        'order_amount': '下单价',
        'rebate_amount': '返点',
        'cost_amount': '成本'
    }
    df = basic_field_mapping(df, mapping)

    # 确保定档媒介字段存在
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

    # 标准化媒介名称
    if '定档媒介' in df.columns:
        df['定档媒介'] = df['定档媒介'].fillna('未知').astype(str).str.strip()
        df['定档媒介'] = df['定档媒介'].replace(['', 'nan', 'NaN', 'None', 'null'], '未知')
        df['定档媒介'] = df['定档媒介'].apply(normalize_media_name)

    # 添加媒介小组
    df['定档媒介小组'] = df['定档媒介'].apply(get_media_group)

    # 确保数据类型字段
    if '数据类型' not in df.columns:
        df['数据类型'] = '定档'

    logger.info(f"工作量数据字段准备完成，定档媒介唯一数: {df['定档媒介'].nunique()}")
    logger.info(f"工作量数据小组分布: {df['定档媒介小组'].value_counts().to_dict()}")
    return df


def prepare_quality_data(df):
    """为质量数据准备必要的字段 - 极简版"""
    logger.info("为质量数据准备字段...")
    df = df.copy()

    # 字段映射
    mapping = {
        'influencer_nickname': '达人昵称',
        'project_name': '项目名称',
        'submit_media_user_name': 'submit_media_user_name',
        'submit_media_user_id': 'submit_media_user_id',
        'state': '状态',
        'influencer_purpose': '达人用途',
        'kol_koc_type': '达人量级'
    }
    df = basic_field_mapping(df, mapping)

    # 确保定档媒介字段存在
    if '定档媒介' not in df.columns:
        if 'submit_media_user_name' in df.columns:
            df['定档媒介'] = df['submit_media_user_name']
            logger.info("使用 'submit_media_user_name' 作为定档媒介")
        elif 'schedule_user_name' in df.columns:
            df['定档媒介'] = df['schedule_user_name']
            logger.info("使用 'schedule_user_name' 作为定档媒介")
        else:
            df['定档媒介'] = '未知'
            logger.warning("未找到任何媒介字段，使用默认值'未知'")

    # 标准化媒介名称
    if '定档媒介' in df.columns:
        df['定档媒介'] = df['定档媒介'].fillna('未知').astype(str).str.strip()
        df['定档媒介'] = df['定档媒介'].replace(['', 'nan', 'NaN', 'None', 'null'], '未知')
        df['定档媒介'] = df['定档媒介'].apply(normalize_media_name)

    # 添加媒介小组
    df['定档媒介小组'] = df['定档媒介'].apply(get_media_group)

    # 添加定档媒介ID
    if '定档媒介ID' not in df.columns:
        if 'submit_media_user_id' in df.columns:
            df['定档媒介ID'] = df['submit_media_user_id'].astype(str).str.replace('.0', '')
        else:
            df['定档媒介ID'] = ''

    # 添加对应名字
    if '对应名字' not in df.columns:
        df['对应名字'] = df['定档媒介']

    # 添加原始状态
    if '原始状态' not in df.columns and '状态' in df.columns:
        df['原始状态'] = df['状态']

    # 确保数据类型字段
    if '数据类型' not in df.columns:
        df['数据类型'] = '提报'

    logger.info(f"质量数据字段准备完成，定档媒介唯一数: {df['定档媒介'].nunique()}")
    logger.info(f"质量数据小组分布: {df['定档媒介小组'].value_counts().to_dict()}")
    return df


def prepare_cost_data(df):
    """
    为成本数据准备必要的字段 - 只做基础映射，复杂逻辑在CostAnalyzer中
    """
    logger.info("=" * 50)
    logger.info("为成本数据准备字段...")
    logger.info(f"输入数据行数: {len(df)}")

    if df.empty:
        logger.warning("输入数据为空")
        return df

    df = df.copy()
    logger.info(f"原始数据列: {list(df.columns)}")

    # 字段映射
    mapping = {
        'influencer_nickname': '达人昵称',
        'project_name': '项目名称',
        'schedule_user_name': 'schedule_user_name',
        'submit_media_user_id': 'submit_media_user_id',
        'submit_media_user_name': 'submit_media_user_name',
        'state': '状态',
        'kol_koc_type': '达人量级',
        'note_type': '笔记类型',
        'follower_count': '粉丝数',
        'cooperation_quote': '报价',
        'order_amount': '下单价',
        'rebate_amount': '返点',
        'cost_amount': '成本',
        'interaction_count': '互动量',
        'read_count': '阅读量',
        'exposure_count': '曝光量',
        'read_uv_count': '阅读uv数'
    }
    df = basic_field_mapping(df, mapping)

    # 确保定档媒介字段存在
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

    # 标准化媒介名称
    if '定档媒介' in df.columns:
        df['定档媒介'] = df['定档媒介'].fillna('未知').astype(str).str.strip()
        df['定档媒介'] = df['定档媒介'].replace(['', 'nan', 'NaN', 'None', 'null'], '未知')
        df['定档媒介'] = df['定档媒介'].apply(normalize_media_name)

    # 添加媒介小组
    if '定档媒介小组' not in df.columns:
        df['定档媒介小组'] = df['定档媒介'].apply(get_media_group)

    # 数值字段类型转换 - 只转换，不覆盖原始值
    numeric_fields = ['成本', '报价', '下单价', '返点', '互动量', '阅读量', '曝光量', '粉丝数']
    for field in numeric_fields:
        if field in df.columns:
            df[field] = pd.to_numeric(df[field], errors='coerce').fillna(0)
            # 统计非零值
            non_zero = (df[field] > 0).sum()
            if non_zero > 0:
                logger.info(f"字段 {field}: 非零值 {non_zero} 条")
        else:
            df[field] = 0
            logger.warning(f"字段 {field} 不存在，设为0")

    # 确保数据类型字段
    if '数据类型' not in df.columns:
        df['数据类型'] = '定档'

    logger.info(f"成本数据字段准备完成，定档媒介唯一数: {df['定档媒介'].nunique()}")
    logger.info(f"成本数据小组分布: {df['定档媒介小组'].value_counts().to_dict()}")
    logger.info(f"最终数据行数: {len(df)}")
    logger.info("=" * 50)
    return df


@upload_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    """文件上传首页和处理"""
    if request.method == 'GET':
        if not session.get('user_id'):
            return redirect(url_for('auth.login', next=url_for('upload.index')))

        all_groups = []
        try:
            all_groups = sorted(list(set([v for v in NAME_TO_GROUP_MAPPING.values() if v != '其他组' and v is not None])))
            logger.info(f"从映射表获取到的小组列表: {all_groups}")
        except Exception as e:
            logger.warning(f"获取小组列表失败: {e}")
            all_groups = ['家居媒介组', '快消媒介组', '耐消媒介组', '电商媒介组', '户外媒介组']

        return render_template('index.html', all_groups=all_groups, now=datetime.now())

    return file_upload_handler()


def file_upload_handler():
    """处理文件上传和分析"""
    try:
        g.uploaded_files = set()
        category = request.form.get('category', '默认类目').strip()
        selected_groups = request.form.getlist('selected_groups[]')
        use_original_state = request.form.get('use_original_state', 'false') == 'true'

        workload_files = request.files.getlist('workload_files[]')
        quality_files = request.files.getlist('quality_files[]')
        cost_files = request.files.getlist('cost_files[]')

        has_valid_file = any([file and file.filename.strip() for file_list in
                             [workload_files, quality_files, cost_files] for file in file_list])
        if not has_valid_file:
            flash('⚠️ 请至少上传一个非空的Excel/CSV文件', 'warning')
            return redirect(url_for('upload.index'))

        if len(selected_groups) == 0:
            flash('⚠️ 请至少选择一个分析小组', 'warning')
            return redirect(url_for('upload.index'))

        file_source = FileSource(app.config.get('UPLOAD_FOLDER', 'uploads'))

        # 工作量分析
        workload_result = {"result": pd.DataFrame(), "summary": {}, "group_summary": pd.DataFrame(),
                          "top_media_ranking": pd.DataFrame()}
        if workload_files and workload_files[0].filename:
            logger.info("开始处理工作量文件...")
            file_paths = []
            for f in workload_files:
                if f and f.filename.strip():
                    filename = secure_filename_cn(f.filename)
                    if filename in g.uploaded_files:
                        continue
                    g.uploaded_files.add(filename)
                    save_path = file_source.save_uploaded_file(f, filename)
                    file_paths.append(save_path)

            if file_paths:
                workload_df = file_source.read_files(file_paths)
                if not workload_df.empty:
                    workload_df = prepare_workload_data(workload_df)
                    # 根据选中的小组过滤数据
                    workload_df = filter_by_selected_groups(workload_df, selected_groups)

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
                    logger.info(f"工作量分析完成，明细数据行数: {len(workload_result['result'])}")

        # 质量分析
        quality_result = {"result": pd.DataFrame(), "summary": {}, "group_summary": pd.DataFrame(),
                         "quality_distribution": pd.DataFrame(), "premium_detail": pd.DataFrame(),
                         "high_read_detail": pd.DataFrame()}
        if quality_files and quality_files[0].filename:
            logger.info("开始处理质量文件...")
            file_paths = []
            for f in quality_files:
                if f and f.filename.strip():
                    filename = secure_filename_cn(f.filename)
                    if filename in g.uploaded_files:
                        continue
                    g.uploaded_files.add(filename)
                    save_path = file_source.save_uploaded_file(f, filename)
                    file_paths.append(save_path)

            if file_paths:
                quality_df = file_source.read_files(file_paths)
                if not quality_df.empty:
                    quality_df = prepare_quality_data(quality_df)
                    # 根据选中的小组过滤数据
                    quality_df = filter_by_selected_groups(quality_df, selected_groups)

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
                    logger.info(f"质量分析完成，明细数据行数: {len(quality_result['result'])}")

        # 成本分析
        cost_result = {
            "result": pd.DataFrame(), "summary": {}, "overall_summary": {},
            "media_detail": pd.DataFrame(), "group_summary": pd.DataFrame(),
            "filtered_summary": {'筛除总成本': 0, '筛除成本占比': 0},
            "cost_efficiency_ranking": pd.DataFrame(),
            "media_group_workload": pd.DataFrame(), "fixed_media_workload": pd.DataFrame(),
            "fixed_media_cost": pd.DataFrame(), "fixed_media_rebate": pd.DataFrame(),
            "fixed_media_performance": pd.DataFrame(), "fixed_media_level": pd.DataFrame(),
            "fixed_media_comprehensive": pd.DataFrame(), "detailed_data": pd.DataFrame()
        }
        if cost_files and cost_files[0].filename:
            logger.info("开始处理成本文件...")
            file_paths = []
            for f in cost_files:
                if f and f.filename.strip():
                    filename = secure_filename_cn(f.filename)
                    if filename in g.uploaded_files:
                        continue
                    g.uploaded_files.add(filename)
                    save_path = file_source.save_uploaded_file(f, filename)
                    file_paths.append(save_path)

            if file_paths:
                cost_df = file_source.read_files(file_paths)
                if not cost_df.empty:
                    logger.info(f"原始成本数据行数: {len(cost_df)}")
                    if 'cost_amount' in cost_df.columns:
                        cost_gt_zero = (pd.to_numeric(cost_df['cost_amount'], errors='coerce') > 0).sum()
                        logger.info(f"原始成本数据(cost_amount): 成本>0 {cost_gt_zero} 条")
                    if 'rebate_amount' in cost_df.columns:
                        rebate_gt_zero = (pd.to_numeric(cost_df['rebate_amount'], errors='coerce') > 0).sum()
                        logger.info(f"原始返点数据(rebate_amount): 返点>0 {rebate_gt_zero} 条")

                    cost_df = prepare_cost_data(cost_df)
                    # 根据选中的小组过滤数据
                    cost_df = filter_by_selected_groups(cost_df, selected_groups)

                    # 复杂清洗在CostAnalyzer内部完成
                    cost_analyzer = CostAnalyzer(cost_df, pd.DataFrame())
                    cost_analysis = cost_analyzer.analyze(top_n=10)

                    cost_summary = cost_analysis.get('overall_summary', cost_analysis.get('summary', {}))
                    cost_media_detail = cost_analysis.get('media_detail', pd.DataFrame())

                    cost_result = {
                        "result": cost_media_detail,
                        "summary": cost_summary,
                        "overall_summary": cost_summary,
                        "media_detail": cost_media_detail,
                        "group_summary": cost_analysis.get('group_summary', pd.DataFrame()),
                        "filtered_summary": cost_analysis.get('filtered_summary', {'筛除总成本': 0, '筛除成本占比': 0}),
                        "cost_efficiency_ranking": cost_analysis.get('cost_efficiency_ranking', pd.DataFrame()),
                        "media_group_workload": cost_analysis.get('media_group_workload', pd.DataFrame()),
                        "fixed_media_workload": cost_analysis.get('fixed_media_workload', pd.DataFrame()),
                        "fixed_media_cost": cost_analysis.get('fixed_media_cost', pd.DataFrame()),
                        "fixed_media_rebate": cost_analysis.get('fixed_media_rebate', pd.DataFrame()),
                        "fixed_media_performance": cost_analysis.get('fixed_media_performance', pd.DataFrame()),
                        "fixed_media_level": cost_analysis.get('fixed_media_level', pd.DataFrame()),
                        "fixed_media_comprehensive": cost_analysis.get('fixed_media_comprehensive', pd.DataFrame()),
                        "detailed_data": cost_analysis.get('detailed_data', pd.DataFrame())
                    }
                    logger.info(f"成本分析完成，总数据: {len(cost_df)} 条")

        analysis_id = datetime.now().strftime('%Y%m%d%H%M%S')

        # 转换数据格式并保存
        workload_for_storage = {
            "result": convert_pandas_types_to_python(workload_result.get("result", [])),
            "summary": convert_pandas_types_to_python(workload_result.get("summary", {})),
            "group_summary": convert_pandas_types_to_python(workload_result.get("group_summary", [])),
            "top_media_ranking": convert_pandas_types_to_python(workload_result.get("top_media_ranking", []))
        }

        quality_for_storage = {
            "result": convert_pandas_types_to_python(quality_result.get("result", [])),
            "summary": convert_pandas_types_to_python(quality_result.get("summary", {})),
            "group_summary": convert_pandas_types_to_python(quality_result.get("group_summary", [])),
            "quality_distribution": convert_pandas_types_to_python(quality_result.get("quality_distribution", [])),
            "premium_detail": convert_pandas_types_to_python(quality_result.get("premium_detail", [])),
            "high_read_detail": convert_pandas_types_to_python(quality_result.get("high_read_detail", []))
        }

        cost_for_storage = {
            "result": convert_pandas_types_to_python(cost_result.get("result", [])),
            "summary": convert_pandas_types_to_python(cost_result.get("summary", {})),
            "overall_summary": convert_pandas_types_to_python(cost_result.get("overall_summary", {})),
            "media_detail": convert_pandas_types_to_python(cost_result.get("media_detail", [])),
            "group_summary": convert_pandas_types_to_python(cost_result.get("group_summary", [])),
            "filtered_summary": convert_pandas_types_to_python(cost_result.get("filtered_summary", {})),
            "cost_efficiency_ranking": convert_pandas_types_to_python(cost_result.get("cost_efficiency_ranking", [])),
            "media_group_workload": convert_pandas_types_to_python(cost_result.get("media_group_workload", [])),
            "fixed_media_workload": convert_pandas_types_to_python(cost_result.get("fixed_media_workload", [])),
            "fixed_media_cost": convert_pandas_types_to_python(cost_result.get("fixed_media_cost", [])),
            "fixed_media_rebate": convert_pandas_types_to_python(cost_result.get("fixed_media_rebate", [])),
            "fixed_media_performance": convert_pandas_types_to_python(cost_result.get("fixed_media_performance", [])),
            "fixed_media_level": convert_pandas_types_to_python(cost_result.get("fixed_media_level", [])),
            "fixed_media_comprehensive": convert_pandas_types_to_python(cost_result.get("fixed_media_comprehensive", [])),
            "detailed_data": convert_pandas_types_to_python(cost_result.get("detailed_data", []))
        }

        analysis_data_full = {
            "analysis_id": analysis_id,
            "full_result": {
                "workload": workload_for_storage,
                "quality": quality_for_storage,
                "cost": cost_for_storage
            },
            "reports": {},
            "category": category,
            "selected_groups": selected_groups,
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        analysis_results[analysis_id] = analysis_data_full
        global_analysis_results[analysis_id] = analysis_data_full

        # 保存到文件
        result_file_path = os.path.join(app.config.get('OUTPUT_DIR', 'outputs'), 'analysis_results', f'{analysis_id}.json')
        os.makedirs(os.path.dirname(result_file_path), exist_ok=True)

        with open(result_file_path, 'w', encoding='utf-8') as f:
            json.dump(convert_pandas_types_to_python(analysis_data_full), f, ensure_ascii=False, indent=2)

        logger.info(f"✅ 分析完成，分析ID：{analysis_id}")
        logger.info(f"✅ 选中的小组: {selected_groups}")
        logger.info(f"数据统计: 工作量 {len(workload_for_storage['result'])} 条, "
                   f"质量 {len(quality_for_storage['result'])} 条, "
                   f"成本 {len(cost_for_storage.get('result', []))} 条")

        flash('✅ 文件上传成功，分析已完成！', 'success')
        return redirect(url_for('reports.dashboard', analysis_id=analysis_id, upload_success=1))

    except Exception as e:
        error_msg = f"❌ 分析失败：{str(e)}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")
        flash(error_msg, 'error')
        return redirect(url_for('upload.index'))