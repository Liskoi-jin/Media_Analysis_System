"""
笔记相关分析路由 - 处理笔记内容表现、达人价值、成本ROI、项目复盘
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
import os
import pandas as pd
import json
from datetime import datetime
import traceback

from analyzers import (
    logger, NAME_TO_GROUP_MAPPING, convert_pandas_types_to_python,
    secure_filename_cn, normalize_media_name, get_media_group,
    read_file_with_auto_encoding
)
from auth.utils import login_required
from flask import current_app as app

# 创建蓝图
note_bp = Blueprint('note_analysis', __name__, url_prefix='/note-analysis')

# 全局变量存储分析结果
note_analysis_results = {}


def _get_latest_analysis():
    """获取最新的分析结果ID"""
    if note_analysis_results:
        return sorted(note_analysis_results.keys())[-1]
    return None


def _get_analysis_result(analysis_id, analysis_type):
    """
    获取分析结果，支持 latest
    返回: (analysis_id, analysis_data, result)
    """
    if analysis_id == 'latest':
        latest_id = _get_latest_analysis()
        if not latest_id:
            return None, None, '暂无分析结果，请先进行笔记分析'
        analysis_id = latest_id

    analysis_data = note_analysis_results.get(analysis_id, {})
    if not analysis_data:
        return None, None, f'分析结果不存在: {analysis_id}'

    logger.info(f"获取分析结果: analysis_id={analysis_id}, analysis_type={analysis_type}")

    # 获取该分析类型的完整数据（包含 overall 和 by_tier）
    result_data = analysis_data.get('result', {}).get(analysis_type, {})

    # 构建返回结果，包含 overall 和 by_tier
    result = {
        'overall': result_data.get('overall', {}),
        'by_tier': result_data.get('by_tier', {}),
        'filter_stats': result_data.get('filter_stats', {}),
        'tier_stats': result_data.get('tier_stats', {})
    }

    # 如果没有 by_tier 数据，尝试从 result_data 直接获取
    if not result['by_tier'] and 'summary' in result_data:
        # 旧格式数据，包装成新格式
        result['overall'] = result_data
        result['by_tier'] = {}

    logger.info(f"  - overall 包含 summary: {bool(result['overall'].get('summary'))}")
    logger.info(f"  - by_tier keys: {list(result['by_tier'].keys())}")

    return analysis_id, analysis_data, result


@note_bp.route('/')
@login_required
def data_source_selector():
    """笔记分析数据来源选择页"""
    return render_template('note_analysis/data_source_selector.html')


@note_bp.route('/upload', methods=['GET'])
@login_required
def upload_index():
    """笔记分析文件上传页面"""
    all_groups = []
    try:
        all_groups = sorted(list(set([v for v in NAME_TO_GROUP_MAPPING.values()
                                      if v != '其他组' and v is not None])))
    except Exception as e:
        logger.warning(f"获取小组列表失败: {e}")
        all_groups = ['家居媒介组', '快消媒介组', '耐消媒介组', '电商媒介组', '户外媒介组']
    return render_template('note_analysis/note_analysis_index.html',
                           all_groups=all_groups, now=datetime.now())


@note_bp.route('/upload', methods=['POST'])
@login_required
def upload_file():
    """处理文件上传"""
    try:
        analysis_types = request.form.getlist('analysis_types[]')
        file = request.files.get('data_file')

        if not file or not file.filename:
            flash('请选择要上传的文件', 'warning')
            return redirect(url_for('note_analysis.upload_index'))

        if len(analysis_types) == 0:
            flash('请至少选择一个分析类型', 'warning')
            return redirect(url_for('note_analysis.upload_index'))

        filename = secure_filename_cn(file.filename)
        file_ext = filename.split('.')[-1].lower()

        if file_ext == 'csv':
            for encoding in ['utf-8', 'gbk', 'gb2312', 'utf-8-sig']:
                try:
                    file.seek(0)
                    df = pd.read_csv(file, encoding=encoding)
                    break
                except:
                    continue
            else:
                flash('无法读取CSV文件，请检查编码', 'warning')
                return redirect(url_for('note_analysis.upload_index'))
        elif file_ext in ['xlsx', 'xls']:
            df = pd.read_excel(file)
        else:
            flash('不支持的文件格式，请上传 CSV 或 Excel 文件', 'warning')
            return redirect(url_for('note_analysis.upload_index'))

        if df.empty:
            flash('文件无有效数据', 'warning')
            return redirect(url_for('note_analysis.upload_index'))

        df['数据类型'] = '定档'

        if '定档媒介' not in df.columns:
            if 'schedule_user_name' in df.columns:
                df['定档媒介'] = df['schedule_user_name']
            elif 'submit_media_user_name' in df.columns:
                df['定档媒介'] = df['submit_media_user_name']
            else:
                df['定档媒介'] = '未知'

        df['定档媒介'] = df['定档媒介'].apply(lambda x: normalize_media_name(str(x)) if pd.notna(x) else '未知')
        df['定档媒介小组'] = df['定档媒介'].apply(get_media_group)

        from analyzers.note_analyzer import NoteAnalyzer
        analyzer = NoteAnalyzer(df)

        combined_result = {}

        for analysis_type in analysis_types:
            logger.info(f"执行分析: {analysis_type}")
            try:
                result = analyzer.analyze(analysis_type)
                combined_result[analysis_type] = convert_pandas_types_to_python(result)
                logger.info(f"  ✅ {analysis_type} 分析完成")
            except Exception as e:
                logger.error(f"分析类型 {analysis_type} 失败: {e}", exc_info=True)
                combined_result[analysis_type] = {'error': str(e), 'message': f'{analysis_type}分析失败'}

        analysis_id = datetime.now().strftime('%Y%m%d%H%M%S')
        analysis_data = {
            'analysis_id': analysis_id,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'analysis_types': analysis_types,
            'selected_groups': [],
            'filename': filename,
            'start_date': '',
            'end_date': '',
            'result': combined_result
        }

        note_analysis_results[analysis_id] = analysis_data

        result_file_path = os.path.join(app.config.get('OUTPUT_DIR', 'outputs'),
                                        'note_analysis_results', f'{analysis_id}.json')
        os.makedirs(os.path.dirname(result_file_path), exist_ok=True)

        converted_data = convert_pandas_types_to_python(analysis_data)
        with open(result_file_path, 'w', encoding='utf-8') as f:
            json.dump(converted_data, f, ensure_ascii=False, indent=2)

        success_count = len([t for t in analysis_types if t in combined_result and 'error' not in combined_result[t]])
        failed_count = len(analysis_types) - success_count

        flash(f'✅ 分析完成！共分析 {len(df)} 条笔记数据，成功执行 {success_count} 个分析，失败 {failed_count} 个', 'success')

        if len(analysis_types) > 1:
            return redirect(url_for('note_analysis.combined_dashboard', analysis_id=analysis_id))
        else:
            return redirect(url_for('note_analysis.dashboard',
                                    analysis_id=analysis_id,
                                    analysis_type=analysis_types[0]))

    except Exception as e:
        logger.error(f"分析失败: {e}", exc_info=True)
        flash(f'分析失败: {str(e)}', 'error')
        return redirect(url_for('note_analysis.upload_index'))


@note_bp.route('/database', methods=['GET'])
@login_required
def database_index():
    """笔记分析数据库配置页"""
    all_groups = []
    try:
        all_groups = sorted(list(set([v for v in NAME_TO_GROUP_MAPPING.values()
                                      if v != '其他组' and v is not None])))
    except Exception as e:
        logger.warning(f"获取小组列表失败: {e}")
        all_groups = ['家居媒介组', '快消媒介组', '耐消媒介组', '电商媒介组', '户外媒介组']
    return render_template('note_analysis/note_analysis_index.html',
                           all_groups=all_groups, now=datetime.now())


@note_bp.route('/database', methods=['POST'])
@login_required
def database_analysis():
    """处理数据库分析"""
    try:
        analysis_types = request.form.getlist('analysis_types[]')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')

        if not start_date or not end_date:
            flash('请填写日期范围', 'error')
            return redirect(url_for('note_analysis.database_index'))

        if len(analysis_types) == 0:
            flash('请至少选择一个分析类型', 'warning')
            return redirect(url_for('note_analysis.database_index'))

        from data_sources.note_db_source import NoteDBSource
        db_source = NoteDBSource()
        df = db_source.query_note_data(start_date, end_date)

        if df.empty:
            flash('在指定日期范围内未查询到任何数据', 'warning')
            return redirect(url_for('note_analysis.database_index'))

        df['数据类型'] = '定档'

        if '定档媒介' not in df.columns:
            if 'schedule_user_name' in df.columns:
                df['定档媒介'] = df['schedule_user_name']
            elif 'submit_media_user_name' in df.columns:
                df['定档媒介'] = df['submit_media_user_name']
            else:
                df['定档媒介'] = '未知'

        df['定档媒介'] = df['定档媒介'].apply(lambda x: normalize_media_name(str(x)) if pd.notna(x) else '未知')
        df['定档媒介小组'] = df['定档媒介'].apply(get_media_group)

        from analyzers.note_analyzer import NoteAnalyzer
        analyzer = NoteAnalyzer(df)

        combined_result = {}

        for analysis_type in analysis_types:
            logger.info(f"执行分析: {analysis_type}")
            try:
                result = analyzer.analyze(analysis_type)
                combined_result[analysis_type] = convert_pandas_types_to_python(result)
                logger.info(f"  ✅ {analysis_type} 分析完成")
            except Exception as e:
                logger.error(f"分析类型 {analysis_type} 失败: {e}", exc_info=True)
                combined_result[analysis_type] = {'error': str(e), 'message': f'{analysis_type}分析失败'}

        analysis_id = datetime.now().strftime('%Y%m%d%H%M%S')
        analysis_data = {
            'analysis_id': analysis_id,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'analysis_types': analysis_types,
            'start_date': start_date,
            'end_date': end_date,
            'selected_groups': [],
            'result': combined_result
        }

        note_analysis_results[analysis_id] = analysis_data

        result_file_path = os.path.join(app.config.get('OUTPUT_DIR', 'outputs'),
                                        'note_analysis_results', f'{analysis_id}.json')
        os.makedirs(os.path.dirname(result_file_path), exist_ok=True)

        converted_data = convert_pandas_types_to_python(analysis_data)
        with open(result_file_path, 'w', encoding='utf-8') as f:
            json.dump(converted_data, f, ensure_ascii=False, indent=2)

        success_count = len([t for t in analysis_types if t in combined_result and 'error' not in combined_result[t]])
        failed_count = len(analysis_types) - success_count

        flash(f'✅ 数据库分析完成！共分析 {len(df)} 条笔记数据，成功执行 {success_count} 个分析，失败 {failed_count} 个', 'success')

        if len(analysis_types) > 1:
            return redirect(url_for('note_analysis.combined_dashboard', analysis_id=analysis_id))
        else:
            return redirect(url_for('note_analysis.dashboard',
                                    analysis_id=analysis_id,
                                    analysis_type=analysis_types[0]))

    except Exception as e:
        logger.error(f"数据库分析失败: {e}", exc_info=True)
        flash(f'分析失败: {str(e)}', 'error')
        return redirect(url_for('note_analysis.database_index'))


@note_bp.route('/combined-dashboard/<analysis_id>')
@login_required
def combined_dashboard(analysis_id):
    """综合仪表盘"""
    try:
        analysis_data = note_analysis_results.get(analysis_id)

        if not analysis_data:
            flash('分析结果不存在', 'error')
            return redirect(url_for('note_analysis.data_source_selector'))

        analysis_types = analysis_data.get('analysis_types', [])
        results = analysis_data.get('result', {})

        type_info = {
            'content': {'name': '内容表现分析', 'icon': 'fa-chart-bar', 'color': 'primary'},
            'value': {'name': '达人价值评估', 'icon': 'fa-user-tie', 'color': 'success'},
            'cost': {'name': '成本与ROI分析', 'icon': 'fa-coins', 'color': 'warning'},
            'review': {'name': '项目与策略复盘', 'icon': 'fa-chart-line', 'color': 'info'}
        }

        summaries = []
        for atype in analysis_types:
            result_data = results.get(atype, {})

            summary = {
                'type': atype,
                'name': type_info.get(atype, {}).get('name', atype),
                'icon': type_info.get(atype, {}).get('icon', 'fa-chart-line'),
                'color': type_info.get(atype, {}).get('color', 'secondary'),
                'has_error': 'error' in result_data
            }

            if summary['has_error']:
                summary['message'] = result_data.get('message', result_data.get('error', '分析执行失败'))
                summary['metrics'] = {}
            else:
                overall_result = result_data.get('overall', {})
                summary_result = overall_result.get('summary', {})

                if atype == 'content':
                    summary['metrics'] = {
                        '总笔记数': summary_result.get('总笔记数', 0),
                        '总互动量': summary_result.get('总互动量', 0),
                        '平均互动量': summary_result.get('平均互动量', 0),
                        '爆款笔记数': summary_result.get('爆款笔记数', 0)
                    }
                elif atype == 'value':
                    summary['metrics'] = {
                        '总达人数': summary_result.get('总达人数', 0),
                        '平均CPE': summary_result.get('平均CPE', 0),
                        'KOL数量': summary_result.get('KOL数量', 0),
                        'KOC数量': summary_result.get('KOC数量', 0)
                    }
                elif atype == 'cost':
                    summary['metrics'] = {
                        '总成本': summary_result.get('总成本', 0),
                        '平均CPM': summary_result.get('平均CPM', 0),
                        '平均CPE': summary_result.get('平均CPE', 0),
                        '有成本数据笔记数': summary_result.get('有成本数据笔记数', 0)
                    }
                elif atype == 'review':
                    summary['metrics'] = {
                        '分析项目数': summary_result.get('分析项目数', 0),
                        '分析笔记数': summary_result.get('分析笔记数', 0),
                        '有效项目数': summary_result.get('有效项目数', 0),
                        '最佳项目': summary_result.get('最佳项目', '未知')
                    }

            summaries.append(summary)

        analysis_data_info = {
            "category": "笔记分析综合报告",
            "timestamp": analysis_data.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
            "start_date": analysis_data.get('start_date', ''),
            "end_date": analysis_data.get('end_date', ''),
            "selected_groups": analysis_data.get('selected_groups', []),
            "analysis_types": analysis_types,
            "analysis_id": analysis_id
        }

        return render_template('note_analysis/combined_dashboard.html',
                               analysis_id=analysis_id,
                               analysis_data=analysis_data_info,
                               summaries=summaries,
                               type_info=type_info,
                               results=results)

    except Exception as e:
        logger.error(f"combined_dashboard 错误: {e}", exc_info=True)
        flash(f'生成综合报告失败: {str(e)}', 'error')
        return redirect(url_for('note_analysis.data_source_selector'))


@note_bp.route('/dashboard/<analysis_id>')
@login_required
def dashboard(analysis_id):
    """笔记分析仪表盘（单分析类型）"""
    analysis_type = request.args.get('analysis_type', 'content')
    analysis_data = note_analysis_results.get(analysis_id)

    if not analysis_data:
        flash('分析结果不存在', 'error')
        return redirect(url_for('note_analysis.data_source_selector'))

    type_map = {
        'content': 'content_report',
        'value': 'value_report',
        'cost': 'cost_report',
        'review': 'review_report'
    }

    report_func = type_map.get(analysis_type, 'content_report')
    return redirect(url_for(f'note_analysis.{report_func}', analysis_id=analysis_id))


@note_bp.route('/content/<analysis_id>')
@login_required
def content_report(analysis_id):
    """内容表现分析报告"""
    aid, analysis_data, result = _get_analysis_result(analysis_id, 'content')

    if not aid:
        flash(result, 'error')
        return redirect(url_for('note_analysis.data_source_selector'))

    start_date = analysis_data.get('start_date', '')
    end_date = analysis_data.get('end_date', '')
    analysis_types = analysis_data.get('analysis_types', [])

    analysis_data_info = {
        "category": "内容表现分析",
        "timestamp": analysis_data.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        "start_date": start_date,
        "end_date": end_date,
        "analysis_types": analysis_types,
        "is_multi_analysis": len(analysis_types) > 1 if analysis_types else False
    }

    return render_template('note_analysis/note_content_analysis.html',
                           analysis_id=aid,
                           analysis_data=analysis_data_info,
                           result=result)


@note_bp.route('/value/<analysis_id>')
@login_required
def value_report(analysis_id):
    """达人价值评估报告"""
    aid, analysis_data, result = _get_analysis_result(analysis_id, 'value')

    if not aid:
        flash(result, 'error')
        return redirect(url_for('note_analysis.data_source_selector'))

    start_date = analysis_data.get('start_date', '')
    end_date = analysis_data.get('end_date', '')
    analysis_types = analysis_data.get('analysis_types', [])

    analysis_data_info = {
        "category": "达人价值评估",
        "timestamp": analysis_data.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        "start_date": start_date,
        "end_date": end_date,
        "analysis_types": analysis_types,
        "is_multi_analysis": len(analysis_types) > 1 if analysis_types else False
    }

    return render_template('note_analysis/note_value_analysis.html',
                           analysis_id=aid,
                           analysis_data=analysis_data_info,
                           result=result)


@note_bp.route('/cost/<analysis_id>')
@login_required
def cost_report(analysis_id):
    """成本与ROI分析报告"""
    aid, analysis_data, result = _get_analysis_result(analysis_id, 'cost')

    if not aid:
        flash(result, 'error')
        return redirect(url_for('note_analysis.data_source_selector'))

    start_date = analysis_data.get('start_date', '')
    end_date = analysis_data.get('end_date', '')
    analysis_types = analysis_data.get('analysis_types', [])

    analysis_data_info = {
        "category": "成本与ROI分析",
        "timestamp": analysis_data.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        "start_date": start_date,
        "end_date": end_date,
        "analysis_types": analysis_types,
        "is_multi_analysis": len(analysis_types) > 1 if analysis_types else False
    }

    return render_template('note_analysis/note_cost_analysis.html',
                           analysis_id=aid,
                           analysis_data=analysis_data_info,
                           result=result)


@note_bp.route('/review/<analysis_id>')
@login_required
def review_report(analysis_id):
    """项目与策略复盘报告"""
    aid, analysis_data, result = _get_analysis_result(analysis_id, 'review')

    if not aid:
        flash(result, 'error')
        return redirect(url_for('note_analysis.data_source_selector'))

    start_date = analysis_data.get('start_date', '')
    end_date = analysis_data.get('end_date', '')
    analysis_types = analysis_data.get('analysis_types', [])

    analysis_data_info = {
        "category": "项目与策略复盘",
        "timestamp": analysis_data.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        "start_date": start_date,
        "end_date": end_date,
        "analysis_types": analysis_types,
        "is_multi_analysis": len(analysis_types) > 1 if analysis_types else False
    }

    return render_template('note_analysis/note_review_analysis.html',
                           analysis_id=aid,
                           analysis_data=analysis_data_info,
                           result=result)


@note_bp.route('/export/<analysis_id>/<export_type>')
@login_required
def export_report(analysis_id, export_type):
    """导出报告"""
    from flask import send_file
    import io

    analysis_data = note_analysis_results.get(analysis_id)
    if not analysis_data:
        flash('分析结果不存在', 'error')
        return redirect(url_for('note_analysis.data_source_selector'))

    data_to_export = []

    if 'analysis_types' in analysis_data:
        for atype in analysis_data.get('analysis_types', []):
            result_data = analysis_data.get('result', {}).get(atype, {})
            overall_result = result_data.get('overall', result_data)
            export_data = overall_result.get(export_type, [])
            if export_data:
                data_to_export = export_data
                break
    else:
        result = analysis_data.get('result', {})
        data_to_export = result.get(export_type, [])

    if not data_to_export:
        flash(f'无{export_type}数据可导出', 'warning')
        return redirect(request.referrer or url_for('note_analysis.dashboard', analysis_id=analysis_id))

    df = pd.DataFrame(data_to_export)
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name=export_type[:31], index=False)

    output.seek(0)
    filename = f"笔记分析_{export_type}_{analysis_id}.xlsx"

    return send_file(
        output,
        download_name=filename,
        as_attachment=True,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )