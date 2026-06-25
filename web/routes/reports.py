"""
报告路由 - 处理报告展示和下载
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify, send_from_directory
import os
import pandas as pd
import json
from datetime import datetime
from io import BytesIO
import traceback

from analyzers.utils import (
    logger, fill_group_data_fields, fill_cost_data_fields,
    preprocess_percent_str_to_float, convert_pandas_types_to_python
)
from analyzers.report_generator import ReportGenerator
from auth.utils import login_required
from flask import current_app as app

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')

analysis_results = {}


def load_analysis_result(analysis_id):
    """从内存/本地文件加载分析结果"""
    if analysis_id in analysis_results:
        analysis_data = analysis_results[analysis_id].copy()

        if 'full_result' not in analysis_data:
            analysis_data['full_result'] = {
                'workload': analysis_data.get('workload', {}),
                'quality': analysis_data.get('quality', {}),
                'cost': analysis_data.get('cost', {})
            }

        full_result = analysis_data.get('full_result', {})
        full_result = convert_pandas_types_to_python(full_result)

        # 统一数据键名
        if 'workload' in full_result:
            workload_data = full_result['workload']
            if isinstance(workload_data, dict):
                if 'detail' in workload_data and 'result' not in workload_data:
                    workload_data['result'] = workload_data.pop('detail', [])
                workload_data['summary'] = workload_data.get('summary', {})
                workload_data['group_summary'] = workload_data.get('group_summary', [])
                workload_data['top_media_ranking'] = workload_data.get('top_media_ranking', [])

        if 'quality' in full_result:
            quality_data = full_result['quality']
            if isinstance(quality_data, dict):
                if 'detail' in quality_data and 'result' not in quality_data:
                    quality_data['result'] = quality_data.pop('detail', [])
                quality_data['premium_detail'] = quality_data.get('premium_detail', [])
                quality_data['high_read_detail'] = quality_data.get('high_read_detail', [])
                quality_data['summary'] = quality_data.get('summary', {})
                quality_data['group_summary'] = quality_data.get('group_summary', [])
                quality_data['quality_distribution'] = quality_data.get('quality_distribution', [])

        # 补全小组数据
        workload_group = full_result.get('workload', {}).get('group_summary', [])
        if isinstance(workload_group, list):
            workload_group = fill_group_data_fields(workload_group)
            full_result['workload']['group_summary'] = workload_group

        quality_group = full_result.get('quality', {}).get('group_summary', [])
        if isinstance(quality_group, list):
            quality_group = fill_group_data_fields(quality_group)
            full_result['quality']['group_summary'] = quality_group

        # 补全成本数据
        if 'cost' in full_result:
            cost_data = full_result['cost']
            if not isinstance(cost_data, dict):
                cost_data = {}
                full_result['cost'] = cost_data

            if 'invalid_data_detail' not in cost_data:
                cost_data['invalid_data_detail'] = []

            overall_summary = cost_data.get('overall_summary', {})
            if not isinstance(overall_summary, dict):
                overall_summary = {}
                cost_data['overall_summary'] = overall_summary

            overall_summary['总数据条数'] = overall_summary.get('总数据条数', 0)
            overall_summary['有效数据条数'] = overall_summary.get('有效数据条数', 0)
            overall_summary['无效数据条数'] = overall_summary.get('无效数据条数', 0)

            cost_data['media_group_workload'] = cost_data.get('media_group_workload', [])
            cost_data['fixed_media_workload'] = cost_data.get('fixed_media_workload', [])
            cost_data['fixed_media_cost'] = cost_data.get('fixed_media_cost', [])
            cost_data['fixed_media_rebate'] = cost_data.get('fixed_media_rebate', [])
            cost_data['fixed_media_performance'] = cost_data.get('fixed_media_performance', [])
            cost_data['fixed_media_level'] = cost_data.get('fixed_media_level', [])
            cost_data['fixed_media_comprehensive'] = cost_data.get('fixed_media_comprehensive', [])
            cost_data['detailed_data'] = cost_data.get('detailed_data', [])

        analysis_data['full_result'] = full_result
        analysis_data['category'] = analysis_data.get('category', '未知类目')
        analysis_data['timestamp'] = analysis_data.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        return analysis_data

    # 从本地 JSON 文件加载
    result_file = os.path.join(app.config.get('OUTPUT_DIR', 'outputs'), 'analysis_results', f'{analysis_id}.json')
    if os.path.exists(result_file):
        try:
            with open(result_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            result = {
                'analysis_id': analysis_id,
                'timestamp': data.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                'category': data.get('category', '数据库分析'),
                'selected_groups': data.get('selected_groups', []),
                'full_result': data.get('full_result', {}),
                'reports': data.get('reports', {}),
                'config': data.get('config', {})
            }
            return result
        except Exception as e:
            logger.error(f"❌ 读取数据库分析结果失败：{result_file}，错误：{e}")
            return None

    return None


@reports_bp.route('/')
def root_redirect():
    """根路径重定向到首页"""
    return redirect(url_for('reports.home'))


@reports_bp.route('/home')
@login_required
def home():
    """全局首页 - 整合媒介分析与笔记分析核心指标"""
    media_data = None
    note_data = None
    all_analyses = []

    # ---- 读取最新的媒介分析结果 ----
    media_results_dir = os.path.join(app.config.get('OUTPUT_DIR', 'outputs'), 'analysis_results')
    if os.path.exists(media_results_dir):
        media_files = sorted([f for f in os.listdir(media_results_dir) if f.endswith('.json')])
        if media_files:
            latest_file = os.path.join(media_results_dir, media_files[-1])
            try:
                with open(latest_file, 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                full_result = raw.get('full_result', {})
                wl = full_result.get('workload', {})
                ql = full_result.get('quality', {})
                ct = full_result.get('cost', {})

                wl_summary = wl.get('summary', {}) or {}
                ql_summary = ql.get('summary', {}) or {}
                ct_summary = ct.get('summary', {}) or {}
                ct_overall = ct.get('overall_summary', {}) or {}

                # 提取分布数据用于图表
                group_dist = wl_summary.get('主要小组分布', {})
                quality_dist_raw = ql_summary.get('质量分布', ql.get('quality_distribution', []))
                ql_quality_dist = ql.get('quality_distribution', [])

                media_data = {
                    'analysis_id': raw.get('analysis_id', ''),
                    'timestamp': raw.get('timestamp', ''),
                    'category': raw.get('category', ''),
                    'workload': wl_summary,
                    'quality': ql_summary,
                    'cost': ct_summary,
                    'cost_overall': ct_overall,
                    'group_distribution': group_dist,
                    'quality_distribution': ql_quality_dist if isinstance(ql_quality_dist, list) else []
                }

                all_analyses.append({
                    'type': 'media',
                    'label': '媒介分析',
                    'analysis_id': raw.get('analysis_id', ''),
                    'timestamp': raw.get('timestamp', ''),
                    'category': raw.get('category', '')
                })
            except Exception as e:
                logger.warning(f"读取媒介分析结果失败: {e}")

        # 收集所有历史媒介分析用于时间线
        for fname in reversed(media_files[-6:]):
            try:
                with open(os.path.join(media_results_dir, fname), 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                all_analyses.append({
                    'type': 'media',
                    'label': '媒介分析',
                    'analysis_id': raw.get('analysis_id', fname.replace('.json', '')),
                    'timestamp': raw.get('timestamp', ''),
                    'category': raw.get('category', '')
                })
            except Exception:
                pass

    # ---- 读取最新的笔记分析结果 ----
    note_results_dir = os.path.join(app.config.get('OUTPUT_DIR', 'outputs'), 'note_analysis_results')
    if os.path.exists(note_results_dir):
        note_files = sorted([f for f in os.listdir(note_results_dir) if f.endswith('.json')])
        if note_files:
            latest_file = os.path.join(note_results_dir, note_files[-1])
            try:
                with open(latest_file, 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                result = raw.get('result', {})
                analysis_types = raw.get('analysis_types', [])

                type_info = {
                    'content': {'name': '内容表现分析', 'icon': 'fa-chart-bar', 'color': 'primary'},
                    'value': {'name': '达人价值评估', 'icon': 'fa-user-tie', 'color': 'success'},
                    'cost': {'name': '成本与ROI分析', 'icon': 'fa-coins', 'color': 'warning'},
                    'review': {'name': '项目与策略复盘', 'icon': 'fa-chart-line', 'color': 'info'}
                }

                note_summaries = []
                # 提取额外图表数据
                note_charts = {}

                for atype in analysis_types:
                    r = result.get(atype, {})
                    overall = r.get('overall', {})
                    summary = overall.get('summary', {})

                    if not summary:
                        continue

                    metrics = {}
                    if atype == 'content':
                        metrics = {
                            '总笔记数': summary.get('总笔记数', 0),
                            '总互动量': summary.get('总互动量', 0),
                            '平均互动量': summary.get('平均互动量', 0),
                            '爆款笔记数': summary.get('爆款笔记数', 0)
                        }
                        # 量级分布
                        tier_dist = summary.get('量级分布', {})
                        if tier_dist:
                            note_charts['tier_distribution'] = tier_dist
                        # 类型比较
                        type_cmp = overall.get('type_comparison', {})
                        if type_cmp:
                            note_charts['type_comparison'] = type_cmp
                    elif atype == 'value':
                        metrics = {
                            '总达人数': summary.get('总达人数', 0),
                            '平均CPE': summary.get('平均CPE', 0),
                            'KOL数量': summary.get('KOL数量', 0),
                            'KOC数量': summary.get('KOC数量', 0)
                        }
                        high_value = summary.get('高互动达人比例(%)', 0)
                        if high_value:
                            note_charts['high_value_ratio'] = high_value
                    elif atype == 'cost':
                        metrics = {
                            '总成本': summary.get('总成本', 0),
                            '平均CPM': summary.get('平均CPM', 0),
                            '平均CPE': summary.get('平均CPE', 0),
                            '有成本数据笔记数': summary.get('有成本数据笔记数', 0)
                        }
                        # 按量级成本
                        tier_cost = summary.get('按量级成本汇总', {})
                        if tier_cost:
                            note_charts['tier_cost'] = tier_cost
                    elif atype == 'review':
                        metrics = {
                            '分析项目数': summary.get('分析项目数', 0),
                            '分析笔记数': summary.get('分析笔记数', 0),
                            '有效项目数': summary.get('有效项目数', 0),
                            '最佳项目': summary.get('最佳项目', '未知')
                        }

                    note_summaries.append({
                        'type': atype,
                        'name': type_info.get(atype, {}).get('name', atype),
                        'icon': type_info.get(atype, {}).get('icon', 'fa-chart-line'),
                        'color': type_info.get(atype, {}).get('color', 'secondary'),
                        'metrics': metrics
                    })

                note_data = {
                    'analysis_id': raw.get('analysis_id', ''),
                    'timestamp': raw.get('timestamp', ''),
                    'summaries': note_summaries,
                    'charts': note_charts
                }

                all_analyses.append({
                    'type': 'note',
                    'label': '笔记分析',
                    'analysis_id': raw.get('analysis_id', ''),
                    'timestamp': raw.get('timestamp', ''),
                    'category': '笔记分析综合报告'
                })
            except Exception as e:
                logger.warning(f"读取笔记分析结果失败: {e}")

        # 收集历史笔记分析
        for fname in reversed(note_files[-5:]):
            try:
                with open(os.path.join(note_results_dir, fname), 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                all_analyses.append({
                    'type': 'note',
                    'label': '笔记分析',
                    'analysis_id': raw.get('analysis_id', fname.replace('.json', '')),
                    'timestamp': raw.get('timestamp', ''),
                    'category': '笔记分析综合报告'
                })
            except Exception:
                pass

    # 按时间排序
    all_analyses.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    all_analyses = all_analyses[:12]

    return render_template('home.html',
                          media_data=media_data,
                          note_data=note_data,
                          all_analyses=all_analyses)


@reports_bp.route('/data-source')
@login_required
def data_source_selector():
    """媒介分析数据来源选择页"""
    return render_template('data_source_selector.html')


@reports_bp.route('/dashboard/<analysis_id>')
@login_required
def dashboard(analysis_id=None):
    """仪表盘"""
    analysis_id = analysis_id or request.args.get('analysis_id', 'latest')
    upload_success = request.args.get('upload_success', '0')
    analysis_data = None

    if analysis_id == 'latest':
        if analysis_results:
            latest_id = sorted(analysis_results.keys())[-1]
            analysis_data = load_analysis_result(latest_id)
            analysis_id = latest_id
        else:
            flash('⚠️ 暂无分析结果，请先上传文件进行分析', 'info')
            return redirect(url_for('reports.data_source_selector'))
    else:
        analysis_data = load_analysis_result(analysis_id)
        if not analysis_data:
            flash(f"❌ 分析结果 {analysis_id} 不存在", 'error')
            return redirect(url_for('reports.data_source_selector'))

    return render_template('dashboard.html',
                          analysis_id=analysis_id,
                          analysis_data=analysis_data,
                          upload_success=upload_success)


@reports_bp.route('/workload/<analysis_id>')
@login_required
def workload_report(analysis_id):
    """工作量分析报告"""
    if analysis_id == 'latest':
        results_dir = os.path.join(app.config.get('OUTPUT_DIR', 'outputs'), 'analysis_results')
        try:
            result_files = [f for f in os.listdir(results_dir) if f.endswith('.json')]
            if not result_files:
                return render_template('workload_analysis.html',
                                       analysis_id='latest',
                                       analysis_data={"category": "暂无类目", "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')},
                                       detail_data=[], workload_summary={}, group_summary=[], top_ranking=[], report={"excel": ""})
            result_files.sort(reverse=True)
            latest_file = result_files[0]
            analysis_id = latest_file.replace('.json', '')
        except Exception as e:
            logger.error(f"获取最新分析结果失败: {e}")

    analysis_data = load_analysis_result(analysis_id)
    if not analysis_data:
        return render_template('workload_analysis.html',
                               analysis_id=analysis_id,
                               analysis_data={"category": "暂无类目", "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')},
                               detail_data=[], workload_summary={}, group_summary=[], top_ranking=[], report={"excel": ""})

    full_result = analysis_data.get("full_result", {})
    workload_data = full_result.get("workload", {})
    category = analysis_data.get("category", "暂无类目")

    detail_data = workload_data.get("result", [])
    workload_summary = workload_data.get("summary", {})
    group_summary = workload_data.get("group_summary", [])
    top_ranking = workload_data.get("top_media_ranking", [])

    if not detail_data and "detail" in workload_data:
        detail_data = workload_data.get("detail", [])

    report = analysis_data.get("reports", {}).get("workload", {"excel": ""})
    analysis_data_info = {
        "category": category,
        "timestamp": analysis_data.get("timestamp", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    }

    if not workload_summary:
        workload_summary = {
            '总定档量': 0, '总CHAIN_RETURNED数': 0, '整体定档率': '0%',
            '总处理量': 0, '媒介总数': len(detail_data) if detail_data else 0
        }

    return render_template('workload_analysis.html',
                           analysis_id=analysis_id,
                           analysis_data=analysis_data_info,
                           detail_data=detail_data,
                           workload_summary=workload_summary,
                           group_summary=group_summary,
                           top_ranking=top_ranking,
                           report=report)


@reports_bp.route('/quality/<analysis_id>')
@login_required
def quality_report(analysis_id):
    """工作质量分析报告"""
    if analysis_id == 'latest':
        results_dir = os.path.join(app.config.get('OUTPUT_DIR', 'outputs'), 'analysis_results')
        try:
            result_files = [f for f in os.listdir(results_dir) if f.endswith('.json')]
            if not result_files:
                return render_template('quality_analysis.html',
                                       analysis_id='latest',
                                       analysis_data={"category": "暂无类目", "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')},
                                       detail_data=[], summary={}, group_summary=[], quality_distribution=[],
                                       premium_detail=[], high_read_detail=[], report={"excel": ""})
            result_files.sort(reverse=True)
            latest_file = result_files[0]
            analysis_id = latest_file.replace('.json', '')
        except Exception as e:
            logger.error(f"获取最新分析结果失败: {e}")

    analysis_data = load_analysis_result(analysis_id)
    if not analysis_data:
        return render_template('quality_analysis.html',
                               analysis_id=analysis_id,
                               analysis_data={"category": "暂无类目", "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')},
                               detail_data=[], summary={}, group_summary=[], quality_distribution=[],
                               premium_detail=[], high_read_detail=[], report={"excel": ""})

    full_result = analysis_data.get("full_result", {})
    quality_data = full_result.get("quality", {})

    detail_data = quality_data.get("result", [])
    summary = quality_data.get("summary", {})
    group_summary = quality_data.get("group_summary", [])
    quality_distribution = quality_data.get("quality_distribution", [])
    premium_detail = quality_data.get("premium_detail", [])
    high_read_detail = quality_data.get("high_read_detail", [])

    if not detail_data and "detail" in quality_data:
        detail_data = quality_data.get("detail", [])

    if not isinstance(detail_data, list): detail_data = []
    if not isinstance(group_summary, list): group_summary = []
    if not isinstance(quality_distribution, list): quality_distribution = []
    if not isinstance(premium_detail, list): premium_detail = []
    if not isinstance(high_read_detail, list): high_read_detail = []

    report = analysis_data.get("reports", {}).get("quality", {"excel": ""})
    analysis_data_info = {
        "category": analysis_data.get("category", "暂无类目"),
        "timestamp": analysis_data.get("timestamp", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    }

    return render_template('quality_analysis.html',
                           analysis_id=analysis_id,
                           analysis_data=analysis_data_info,
                           detail_data=detail_data,
                           summary=summary,
                           group_summary=group_summary,
                           quality_distribution=quality_distribution,
                           premium_detail=premium_detail,
                           high_read_detail=high_read_detail,
                           report=report)


@reports_bp.route('/cost/<analysis_id>')
@login_required
def cost_report(analysis_id):
    """成本分析报告"""
    if analysis_id == 'latest':
        results_dir = os.path.join(app.config.get('OUTPUT_DIR', 'outputs'), 'analysis_results')
        try:
            result_files = [f for f in os.listdir(results_dir) if f.endswith('.json')]
            if not result_files:
                return render_template('cost_analysis.html',
                                       analysis_id='latest',
                                       analysis_data={"category": "暂无类目", "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')},
                                       overall_summary={}, invalid_data_stats={}, invalid_data_detail_count=0,
                                       abnormal_data_stats={}, abnormal_data_detail_count=0,
                                       media_group_workload=[], fixed_media_workload=[], fixed_media_cost=[],
                                       fixed_media_rebate=[], fixed_media_performance=[], fixed_media_level=[],
                                       fixed_media_comprehensive=[], report={"excel": ""})
            result_files.sort(reverse=True)
            latest_file = result_files[0]
            analysis_id = latest_file.replace('.json', '')
        except Exception as e:
            logger.error(f"获取最新分析结果失败: {e}")

    analysis_data = load_analysis_result(analysis_id)
    if not analysis_data:
        return render_template('cost_analysis.html',
                               analysis_id=analysis_id,
                               analysis_data={"category": "暂无类目", "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')},
                               overall_summary={}, invalid_data_stats={}, invalid_data_detail_count=0,
                               abnormal_data_stats={}, abnormal_data_detail_count=0,
                               media_group_workload=[], fixed_media_workload=[], fixed_media_cost=[],
                               fixed_media_rebate=[], fixed_media_performance=[], fixed_media_level=[],
                               fixed_media_comprehensive=[], report={"excel": ""})

    full_result = analysis_data.get("full_result", {})
    cost_data = full_result.get("cost", {})

    overall_summary = cost_data.get("overall_summary", {})
    if not overall_summary:
        overall_summary = cost_data.get("summary", {})

    # 确保 basic fields
    if '总数据条数' not in overall_summary:
        overall_summary['总数据条数'] = 0
    if '有效数据条数' not in overall_summary:
        overall_summary['有效数据条数'] = 0
    if '无效数据条数' not in overall_summary:
        overall_summary['无效数据条数'] = 0
    if '异常数据条数' not in overall_summary:
        overall_summary['异常数据条数'] = 0
    if '参与分析数据条数' not in overall_summary:
        overall_summary['参与分析数据条数'] = 0
    if '异常数据比例(%)' not in overall_summary:
        overall_summary['异常数据比例(%)'] = '0%'
    if '参与分析数据比例(%)' not in overall_summary:
        overall_summary['参与分析数据比例(%)'] = '0%'

    # 从 cost_data 中获取异常数据统计
    if 'abnormal_data_stats' in cost_data:
        abnormal_stats = cost_data['abnormal_data_stats']
        if abnormal_stats:
            overall_summary['异常数据条数'] = abnormal_stats.get('异常数据条数', 0)
            overall_summary['异常数据比例(%)'] = abnormal_stats.get('异常数据比例(%)', '0%')
            overall_summary['参与分析数据条数'] = abnormal_stats.get('参与分析数据条数', 0)
            overall_summary['参与分析数据比例(%)'] = abnormal_stats.get('参与分析数据比例(%)', '0%')
            overall_summary['异常数据总成本(元)'] = abnormal_stats.get('异常数据总成本(元)', 0)
            overall_summary['异常数据原因分布'] = abnormal_stats.get('异常数据原因分布', {})

    total = overall_summary.get('总数据条数', 0)
    if total > 0:
        if '有效数据比例(%)' not in overall_summary:
            overall_summary['有效数据比例(%)'] = f"{(overall_summary.get('有效数据条数', 0) / total * 100):.2f}%"
        if '无效数据比例(%)' not in overall_summary:
            overall_summary['无效数据比例(%)'] = f"{(overall_summary.get('无效数据条数', 0) / total * 100):.2f}%"
        if '异常数据比例(%)' not in overall_summary:
            overall_summary['异常数据比例(%)'] = f"{(overall_summary.get('异常数据条数', 0) / total * 100):.2f}%"
        if '参与分析数据比例(%)' not in overall_summary:
            overall_summary['参与分析数据比例(%)'] = f"{(overall_summary.get('参与分析数据条数', 0) / total * 100):.2f}%"

    invalid_data_stats = cost_data.get("invalid_data_stats", {})
    if not invalid_data_stats:
        invalid_data_stats = {
            '总数据条数': overall_summary.get('总数据条数', 0),
            '有效数据条数': overall_summary.get('有效数据条数', 0),
            '无效数据条数': overall_summary.get('无效数据条数', 0),
            '有效数据比例(%)': overall_summary.get('有效数据比例(%)', '0%'),
            '无效数据比例(%)': overall_summary.get('无效数据比例(%)', '0%'),
            '无效数据总成本(元)': overall_summary.get('无效数据总成本(元)', 0)
        }

    abnormal_data_stats = cost_data.get("abnormal_data_stats", {})
    if not abnormal_data_stats:
        abnormal_data_stats = {
            '异常数据条数': overall_summary.get('异常数据条数', 0),
            '异常数据比例(%)': overall_summary.get('异常数据比例(%)', '0%'),
            '异常数据总成本(元)': overall_summary.get('异常数据总成本(元)', 0),
            '参与分析数据条数': overall_summary.get('参与分析数据条数', 0),
            '参与分析数据比例(%)': overall_summary.get('参与分析数据比例(%)', '0%')
        }

    invalid_data_detail = cost_data.get("invalid_data_detail", [])
    invalid_data_detail_count = len(invalid_data_detail) if isinstance(invalid_data_detail, list) else 0

    abnormal_data_detail = cost_data.get("abnormal_data_detail", [])
    abnormal_data_detail_count = len(abnormal_data_detail) if isinstance(abnormal_data_detail, list) else 0

    media_group_workload = cost_data.get("media_group_workload", [])
    fixed_media_workload = cost_data.get("fixed_media_workload", [])
    fixed_media_cost = cost_data.get("fixed_media_cost", [])
    fixed_media_rebate = cost_data.get("fixed_media_rebate", [])
    fixed_media_performance = cost_data.get("fixed_media_performance", [])
    fixed_media_level = cost_data.get("fixed_media_level", [])
    fixed_media_comprehensive = cost_data.get("fixed_media_comprehensive", [])

    # 确保都是列表
    for var in [media_group_workload, fixed_media_workload, fixed_media_cost, fixed_media_rebate,
                fixed_media_performance, fixed_media_level, fixed_media_comprehensive]:
        if not isinstance(var, list):
            if isinstance(var, pd.DataFrame):
                var = var.to_dict('records')
            else:
                var = []

    report = analysis_data.get("reports", {}).get("cost", {"excel": ""})
    analysis_data_info = {
        "category": analysis_data.get("category", "暂无类目"),
        "timestamp": analysis_data.get("timestamp", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    }

    return render_template('cost_analysis.html',
                           analysis_id=analysis_id,
                           analysis_data=analysis_data_info,
                           overall_summary=overall_summary,
                           invalid_data_stats=invalid_data_stats,
                           invalid_data_detail_count=invalid_data_detail_count,
                           abnormal_data_stats=abnormal_data_stats,
                           abnormal_data_detail_count=abnormal_data_detail_count,
                           media_group_workload=media_group_workload,
                           fixed_media_workload=fixed_media_workload,
                           fixed_media_cost=fixed_media_cost,
                           fixed_media_rebate=fixed_media_rebate,
                           fixed_media_performance=fixed_media_performance,
                           fixed_media_level=fixed_media_level,
                           fixed_media_comprehensive=fixed_media_comprehensive,
                           report=report)


@reports_bp.route('/cost/invalid-data/<analysis_id>')
@login_required
def cost_invalid_data_report(analysis_id):
    """成本分析无效数据详情页"""
    if analysis_id == 'latest':
        results_dir = os.path.join(app.config.get('OUTPUT_DIR', 'outputs'), 'analysis_results')
        try:
            result_files = [f for f in os.listdir(results_dir) if f.endswith('.json')]
            if not result_files:
                return render_template('cost_invalid_data.html',
                                       analysis_id='latest',
                                       analysis_data={"category": "暂无类目",
                                                      "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')},
                                       invalid_data_detail=[], invalid_data_stats={})
            result_files.sort(reverse=True)
            latest_file = result_files[0]
            analysis_id = latest_file.replace('.json', '')
        except Exception as e:
            logger.error(f"获取最新分析结果失败: {e}")

    analysis_data = load_analysis_result(analysis_id)
    if not analysis_data:
        return render_template('cost_invalid_data.html',
                               analysis_id=analysis_id,
                               analysis_data={"category": "暂无类目",
                                              "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')},
                               invalid_data_detail=[], invalid_data_stats={})

    full_result = analysis_data.get("full_result", {})
    cost_data = full_result.get("cost", {})

    logger.info(f"加载成本分析数据，analysis_id={analysis_id}")
    logger.info(f"cost_data keys: {list(cost_data.keys())}")

    # 优先使用 cost_data 中已有的 invalid_data_detail
    invalid_data_detail = cost_data.get("invalid_data_detail", [])

    # 如果 invalid_data_detail 为空，尝试从 detailed_data 中筛选
    if not invalid_data_detail or len(invalid_data_detail) == 0:
        detailed_data = cost_data.get("detailed_data", [])
        logger.info(f"从 detailed_data 中筛选无效数据，detailed_data 类型: {type(detailed_data)}, 长度: {len(detailed_data) if detailed_data else 0}")

        if detailed_data and isinstance(detailed_data, list) and len(detailed_data) > 0:
            invalid_data_detail = []
            for idx, item in enumerate(detailed_data):
                if isinstance(item, dict):
                    # 检查是否是无效数据 - 注意字段名可能是 '成本无效' 或 '成本无效原因'
                    cost_invalid = item.get('成本无效', False)
                    if cost_invalid:
                        detail = {
                            '记录序号': idx + 1,
                            '达人昵称': item.get('达人昵称', '未知'),
                            '项目名称': item.get('项目名称', '未知'),
                            '定档媒介': item.get('定档媒介', '未知'),
                            '成本': float(item.get('成本', 0)) if item.get('成本') else 0,
                            '报价': float(item.get('报价', 0)) if item.get('报价') else 0,
                            '下单价': float(item.get('下单价', 0)) if item.get('下单价') else 0,
                            '返点': float(item.get('返点', 0)) if item.get('返点') else 0,
                            '返点比例': float(item.get('返点比例', 0)) * 100 if item.get('返点比例') else 0,
                            '成本无效原因': item.get('成本无效原因', '成本为0或缺失'),
                            '无效类型': '成本为0或缺失' if '成本为0' in item.get('成本无效原因', '') else '其他原因',
                            '是否被筛除': item.get('被筛除标志', False),
                            '筛除原因': item.get('筛除原因', ''),
                            '是否参与分析': False
                        }
                        invalid_data_detail.append(detail)
                    # 调试：打印第一条数据的关键字段
                    if idx == 0:
                        logger.info(f"第一条数据字段: 成本无效={item.get('成本无效')}, 成本无效原因={item.get('成本无效原因')}")

            logger.info(f"从 detailed_data 中筛选出 {len(invalid_data_detail)} 条无效数据")
        else:
            logger.warning("detailed_data 为空或不是列表")

    # 确保 invalid_data_detail 是列表
    if not isinstance(invalid_data_detail, list):
        if isinstance(invalid_data_detail, pd.DataFrame):
            invalid_data_detail = invalid_data_detail.to_dict('records')
            logger.info(f"将 DataFrame 转换为列表，长度: {len(invalid_data_detail)}")
        elif isinstance(invalid_data_detail, dict):
            invalid_data_detail = [invalid_data_detail]
            logger.info("将 dict 转换为列表")
        else:
            invalid_data_detail = []
            logger.warning(f"invalid_data_detail 类型异常: {type(invalid_data_detail)}，已重置为空列表")

    # 获取无效数据统计
    invalid_data_stats = cost_data.get("invalid_data_stats", {})
    if not invalid_data_stats or not isinstance(invalid_data_stats, dict):
        invalid_data_stats = {}
        logger.warning("invalid_data_stats 为空或不是字典")

    # 如果 invalid_data_stats 为空，从 overall_summary 中获取
    overall_summary = cost_data.get("overall_summary", {})
    if overall_summary:
        if '无效数据条数' not in invalid_data_stats:
            invalid_data_stats['无效数据条数'] = overall_summary.get('无效数据条数', len(invalid_data_detail))
        if '无效数据总成本(元)' not in invalid_data_stats:
            invalid_data_stats['无效数据总成本(元)'] = overall_summary.get('无效数据总成本(元)', 0)
        if '无效数据原因分布' not in invalid_data_stats:
            invalid_data_stats['无效数据原因分布'] = overall_summary.get('无效数据原因分布', {})

    # 确保统计信息中有无效数据条数
    if '无效数据条数' not in invalid_data_stats:
        invalid_data_stats['无效数据条数'] = len(invalid_data_detail)
        logger.info(f"设置无效数据条数为: {len(invalid_data_detail)}")

    # 确保有总数据条数
    if '总数据条数' not in invalid_data_stats:
        total = overall_summary.get('总数据条数', len(cost_data.get('detailed_data', []))) or len(cost_data.get('media_detail', [])) or 0
        invalid_data_stats['总数据条数'] = total
        logger.info(f"设置总数据条数为: {total}")

    # 计算比例
    if invalid_data_stats.get('总数据条数', 0) > 0:
        invalid_data_stats['无效数据比例(%)'] = f"{(invalid_data_stats['无效数据条数'] / invalid_data_stats['总数据条数'] * 100):.2f}%"
        invalid_data_stats['有效数据条数'] = invalid_data_stats['总数据条数'] - invalid_data_stats['无效数据条数']
        invalid_data_stats['有效数据比例(%)'] = f"{(invalid_data_stats['有效数据条数'] / invalid_data_stats['总数据条数'] * 100):.2f}%"

    # 计算无效数据总成本（如果还没有）
    if '无效数据总成本(元)' not in invalid_data_stats and invalid_data_detail:
        total_cost = sum(item.get('成本', 0) for item in invalid_data_detail)
        invalid_data_stats['无效数据总成本(元)'] = round(total_cost, 2)
        logger.info(f"计算无效数据总成本: {total_cost}")

    logger.info(f"最终 invalid_data_detail 长度: {len(invalid_data_detail)}")
    logger.info(f"最终 invalid_data_stats: {invalid_data_stats}")

    analysis_data_info = {
        "category": analysis_data.get("category", "暂无类目"),
        "timestamp": analysis_data.get("timestamp", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    }

    return render_template('cost_invalid_data.html',
                           analysis_id=analysis_id,
                           analysis_data=analysis_data_info,
                           invalid_data_detail=invalid_data_detail,
                           invalid_data_stats=invalid_data_stats)


@reports_bp.route('/cost/abnormal-data/<analysis_id>')
@login_required
def cost_abnormal_data_report(analysis_id):
    """成本分析异常数据详情页"""
    if analysis_id == 'latest':
        results_dir = os.path.join(app.config.get('OUTPUT_DIR', 'outputs'), 'analysis_results')
        try:
            result_files = [f for f in os.listdir(results_dir) if f.endswith('.json')]
            if not result_files:
                return render_template('cost_abnormal_data.html',
                                       analysis_id='latest',
                                       analysis_data={"category": "暂无类目", "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')},
                                       abnormal_data_detail=[], abnormal_data_stats={})
            result_files.sort(reverse=True)
            latest_file = result_files[0]
            analysis_id = latest_file.replace('.json', '')
        except Exception as e:
            logger.error(f"获取最新分析结果失败: {e}")

    analysis_data = load_analysis_result(analysis_id)
    if not analysis_data:
        return render_template('cost_abnormal_data.html',
                               analysis_id=analysis_id,
                               analysis_data={"category": "暂无类目", "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')},
                               abnormal_data_detail=[], abnormal_data_stats={})

    full_result = analysis_data.get("full_result", {})
    cost_data = full_result.get("cost", {})

    logger.info(f"加载成本分析数据，analysis_id={analysis_id}")
    logger.info(f"cost_data keys: {list(cost_data.keys())}")

    # 优先使用 cost_data 中已有的 abnormal_data_detail
    abnormal_data_detail = cost_data.get("abnormal_data_detail", [])

    # 如果 abnormal_data_detail 为空，尝试从 detailed_data 中筛选
    if not abnormal_data_detail or len(abnormal_data_detail) == 0:
        detailed_data = cost_data.get("detailed_data", [])
        logger.info(f"从 detailed_data 中筛选异常数据，detailed_data 类型: {type(detailed_data)}, 长度: {len(detailed_data) if detailed_data else 0}")

        if detailed_data and isinstance(detailed_data, list) and len(detailed_data) > 0:
            abnormal_data_detail = []
            for idx, item in enumerate(detailed_data):
                if isinstance(item, dict):
                    # 检查是否是异常数据（数据异常为True且不是成本无效）
                    data_abnormal = item.get('数据异常', False)
                    cost_invalid = item.get('成本无效', False)

                    if data_abnormal and not cost_invalid:
                        # 获取异常原因
                        abnormal_reason = item.get('数据异常原因', '未知异常')
                        # 判断异常类型
                        if '返点比例' in str(abnormal_reason):
                            abnormal_type = '返点异常'
                        elif '筛除' in str(abnormal_reason):
                            abnormal_type = '筛除异常'
                        else:
                            abnormal_type = '数据异常'

                        detail = {
                            '记录序号': idx + 1,
                            '达人昵称': item.get('达人昵称', '未知'),
                            '项目名称': item.get('项目名称', '未知'),
                            '定档媒介': item.get('定档媒介', '未知'),
                            '成本': float(item.get('成本', 0)) if item.get('成本') else 0,
                            '报价': float(item.get('报价', 0)) if item.get('报价') else 0,
                            '下单价': float(item.get('下单价', 0)) if item.get('下单价') else 0,
                            '返点': float(item.get('返点', 0)) if item.get('返点') else 0,
                            '返点比例': float(item.get('返点比例', 0)) * 100 if item.get('返点比例') else 0,
                            '数据异常原因': abnormal_reason,
                            '异常类型': abnormal_type,
                            '是否参与分析': True,
                            '参与分析标识': '异常数据'
                        }
                        abnormal_data_detail.append(detail)

                    # 调试：打印第一条异常数据的字段
                    if idx == 0 and data_abnormal:
                        logger.info(f"发现异常数据: 数据异常={data_abnormal}, 成本无效={cost_invalid}, 异常原因={item.get('数据异常原因')}")

            logger.info(f"从 detailed_data 中筛选出 {len(abnormal_data_detail)} 条异常数据")
        else:
            logger.warning("detailed_data 为空或不是列表")

    # 确保 abnormal_data_detail 是列表
    if not isinstance(abnormal_data_detail, list):
        if isinstance(abnormal_data_detail, pd.DataFrame):
            abnormal_data_detail = abnormal_data_detail.to_dict('records')
            logger.info(f"将 DataFrame 转换为列表，长度: {len(abnormal_data_detail)}")
        elif isinstance(abnormal_data_detail, dict):
            abnormal_data_detail = [abnormal_data_detail]
            logger.info("将 dict 转换为列表")
        else:
            abnormal_data_detail = []
            logger.warning(f"abnormal_data_detail 类型异常: {type(abnormal_data_detail)}，已重置为空列表")

    # 获取异常数据统计
    abnormal_data_stats = cost_data.get("abnormal_data_stats", {})
    if not abnormal_data_stats or not isinstance(abnormal_data_stats, dict):
        abnormal_data_stats = {}
        logger.warning("abnormal_data_stats 为空或不是字典")

    # 如果 abnormal_data_stats 为空，从 overall_summary 中获取
    overall_summary = cost_data.get("overall_summary", {})
    if overall_summary:
        if '异常数据条数' not in abnormal_data_stats:
            abnormal_data_stats['异常数据条数'] = overall_summary.get('异常数据条数', len(abnormal_data_detail))
            logger.info(f"从 overall_summary 获取异常数据条数: {abnormal_data_stats['异常数据条数']}")
        if '异常数据总成本(元)' not in abnormal_data_stats:
            abnormal_data_stats['异常数据总成本(元)'] = overall_summary.get('异常数据总成本(元)', 0)
        if '异常数据原因分布' not in abnormal_data_stats:
            abnormal_data_stats['异常数据原因分布'] = overall_summary.get('异常数据原因分布', {})
        if '参与分析数据条数' not in abnormal_data_stats:
            abnormal_data_stats['参与分析数据条数'] = overall_summary.get('参与分析数据条数', 0)
        if '参与分析数据比例(%)' not in abnormal_data_stats:
            abnormal_data_stats['参与分析数据比例(%)'] = overall_summary.get('参与分析数据比例(%)', '0%')

    # 确保统计信息中有异常数据条数
    if '异常数据条数' not in abnormal_data_stats:
        abnormal_data_stats['异常数据条数'] = len(abnormal_data_detail)
        logger.info(f"设置异常数据条数为: {len(abnormal_data_detail)}")

    # 计算比例
    total_data = overall_summary.get('总数据条数', 0)
    if total_data > 0:
        abnormal_data_stats['异常数据比例(%)'] = f"{(abnormal_data_stats['异常数据条数'] / total_data * 100):.2f}%"
        abnormal_data_stats['参与分析数据比例(%)'] = f"{(abnormal_data_stats.get('参与分析数据条数', 0) / total_data * 100):.2f}%"

    # 计算异常数据总成本（如果还没有）
    if '异常数据总成本(元)' not in abnormal_data_stats and abnormal_data_detail:
        total_cost = sum(item.get('成本', 0) for item in abnormal_data_detail)
        abnormal_data_stats['异常数据总成本(元)'] = round(total_cost, 2)
        logger.info(f"计算异常数据总成本: {total_cost}")

    logger.info(f"最终 abnormal_data_detail 长度: {len(abnormal_data_detail)}")
    logger.info(f"最终 abnormal_data_stats: {abnormal_data_stats}")

    analysis_data_info = {
        "category": analysis_data.get("category", "暂无类目"),
        "timestamp": analysis_data.get("timestamp", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    }

    return render_template('cost_abnormal_data.html',
                           analysis_id=analysis_id,
                           analysis_data=analysis_data_info,
                           abnormal_data_detail=abnormal_data_detail,
                           abnormal_data_stats=abnormal_data_stats)


@reports_bp.route('/download/table/<string:table_type>/<string:analysis_id>')
@login_required
def download_table(table_type, analysis_id):
    """下载单个表格数据"""
    try:
        analysis_data = load_analysis_result(analysis_id)
        if not analysis_data:
            return jsonify({"error": "分析结果不存在"}), 404

        full_result = analysis_data.get('full_result', {})
        workload_data = full_result.get('workload', {})

        if table_type == 'workload_detail':
            data = workload_data.get('result', [])
            sheet_name = '工作量明细'
        elif table_type == 'workload_group':
            data = workload_data.get('group_summary', [])
            sheet_name = '工作量小组汇总'
        elif table_type == 'workload_top':
            data = workload_data.get('top_media_ranking', [])
            sheet_name = '工作量TOP排名'
        else:
            return jsonify({"error": "不支持的表格类型"}), 400

        if not data:
            return jsonify({"error": "表格数据为空"}), 404

        df = pd.DataFrame(data)
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=False)

        output.seek(0)
        filename = f"{sheet_name}_{analysis_id}.xlsx"
        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        logger.error(f"下载表格失败: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@reports_bp.route('/download/cost-sheet/<string:sheet_key>/<string:analysis_id>')
@login_required
def download_cost_sheet(sheet_key, analysis_id):
    """下载成本分析单个工作表"""
    logger.info(f"下载工作表: sheet_key={sheet_key}, analysis_id={analysis_id}")

    try:
        if analysis_id == 'latest':
            if not analysis_results:
                return "没有可用的分析数据，请先进行分析", 404
            latest_id = sorted(analysis_results.keys())[-1]
            analysis_id = latest_id

        analysis_data = load_analysis_result(analysis_id)
        if not analysis_data:
            return "分析结果不存在", 404

        full_result = analysis_data.get('full_result', {})
        cost_data = full_result.get('cost', {})

        sheet_mapping = {
            'media_group_workload': '媒介小组工作量分析',
            'fixed_media_workload': '定档媒介工作量分析',
            'fixed_media_cost': '定档媒介成本分析',
            'fixed_media_rebate': '定档媒介返点分析',
            'fixed_media_performance': '定档媒介效果分析',
            'fixed_media_level': '定档媒介达人量级分析',
            'fixed_media_comprehensive': '定档媒介综合分析'
        }

        data = None
        sheet_name = sheet_mapping.get(sheet_key, sheet_key)

        if sheet_key == 'media_group_workload':
            data = cost_data.get("media_group_workload", [])
        elif sheet_key == 'fixed_media_workload':
            data = cost_data.get("fixed_media_workload", [])
        elif sheet_key == 'fixed_media_cost':
            data = cost_data.get("fixed_media_cost", [])
        elif sheet_key == 'fixed_media_rebate':
            data = cost_data.get("fixed_media_rebate", [])
        elif sheet_key == 'fixed_media_performance':
            data = cost_data.get("fixed_media_performance", [])
        elif sheet_key == 'fixed_media_level':
            data = cost_data.get("fixed_media_level", [])
        elif sheet_key == 'fixed_media_comprehensive':
            data = cost_data.get("fixed_media_comprehensive", [])
        else:
            return f"不支持的工作表类型: {sheet_key}", 400

        if not data:
            return f"工作表数据为空: {sheet_key}", 404

        df = pd.DataFrame(data)
        output = BytesIO()

        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=False)

        output.seek(0)
        timestamp = datetime.now().strftime('%Y%m%d')
        filename = f"{sheet_name}_{analysis_id}_{timestamp}.xlsx"

        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        logger.error(f"下载失败: {e}", exc_info=True)
        return f"下载失败: {str(e)}", 500


@reports_bp.route('/download/excel/<analysis_id>')
@login_required
def download_excel_report(analysis_id):
    """下载Excel报告"""
    excel_dir = os.path.join(app.config.get('OUTPUT_DIR', 'outputs'), 'excel')

    excel_filename = None
    for file in os.listdir(excel_dir):
        if file.endswith('.xlsx') and analysis_id in file:
            excel_filename = file
            break

    if not excel_filename:
        excel_files = [f for f in os.listdir(excel_dir) if f.endswith('.xlsx')]
        if excel_files:
            excel_files.sort(reverse=True)
            excel_filename = excel_files[0]

    if not excel_filename:
        flash('❌ 未找到该分析ID对应的Excel报告', 'error')
        return redirect(url_for('reports.dashboard', analysis_id=analysis_id))

    try:
        return send_from_directory(
            excel_dir,
            excel_filename,
            as_attachment=True,
            download_name=excel_filename
        )
    except Exception as e:
        logger.error(f"❌ 下载失败：{str(e)}")
        flash(f"❌ 下载失败：{str(e)}", 'error')
        return redirect(url_for('reports.dashboard', analysis_id=analysis_id))


@reports_bp.route('/download/<analysis_id>/<report_type>')
@login_required
def download_report(analysis_id, report_type):
    """下载报告"""
    try:
        analysis_data = load_analysis_result(analysis_id)
        if not analysis_data:
            flash('❌ 分析结果不存在', 'error')
            return redirect(url_for('reports.dashboard', analysis_id=analysis_id))

        full_result = analysis_data.get('full_result', {})
        output = BytesIO()

        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            if report_type == 'workload':
                workload_data = full_result.get('workload', {})
                if workload_data.get('result'):
                    df_detail = pd.DataFrame(workload_data['result'])
                    df_detail.to_excel(writer, sheet_name='工作量明细', index=False)
                if workload_data.get('group_summary'):
                    df_group = pd.DataFrame(workload_data['group_summary'])
                    df_group.to_excel(writer, sheet_name='工作量小组汇总', index=False)
                if workload_data.get('top_media_ranking'):
                    df_top = pd.DataFrame(workload_data['top_media_ranking'])
                    df_top.to_excel(writer, sheet_name='工作量TOP排名', index=False)

            elif report_type == 'quality':
                quality_data = full_result.get('quality', {})
                if quality_data.get('result'):
                    df_detail = pd.DataFrame(quality_data['result'])
                    df_detail.to_excel(writer, sheet_name='质量明细', index=False)
                if quality_data.get('group_summary'):
                    df_group = pd.DataFrame(quality_data['group_summary'])
                    df_group.to_excel(writer, sheet_name='质量小组汇总', index=False)
                if quality_data.get('quality_distribution'):
                    df_dist = pd.DataFrame(quality_data['quality_distribution'])
                    df_dist.to_excel(writer, sheet_name='质量分布', index=False)
                if quality_data.get('premium_detail'):
                    df_premium = pd.DataFrame(quality_data['premium_detail'])
                    df_premium.to_excel(writer, sheet_name='优质达人质量明细', index=False)
                if quality_data.get('high_read_detail'):
                    df_high = pd.DataFrame(quality_data['high_read_detail'])
                    df_high.to_excel(writer, sheet_name='高阅读达人质量明细', index=False)

            elif report_type == 'cost':
                cost_data = full_result.get('cost', {})
                sheets = [
                    ('media_group_workload', '媒介小组工作量分析'),
                    ('fixed_media_workload', '定档媒介工作量分析'),
                    ('fixed_media_cost', '定档媒介成本分析'),
                    ('fixed_media_rebate', '定档媒介返点分析'),
                    ('fixed_media_performance', '定档媒介效果分析'),
                    ('fixed_media_level', '定档媒介达人量级分析'),
                    ('fixed_media_comprehensive', '定档媒介综合分析'),
                    ('media_detail', '详细数据'),
                    ('group_summary', '小组汇总'),
                    ('cost_efficiency_ranking', '成本效率排名')
                ]
                for sheet_key, sheet_name in sheets:
                    if cost_data.get(sheet_key):
                        df_sheet = pd.DataFrame(cost_data[sheet_key])
                        df_sheet.to_excel(writer, sheet_name=sheet_name, index=False)

            else:
                if 'workload' in full_result and full_result['workload'].get('result'):
                    pd.DataFrame(full_result['workload']['result']).to_excel(writer, sheet_name='工作量分析', index=False)
                if 'quality' in full_result and full_result['quality'].get('result'):
                    pd.DataFrame(full_result['quality']['result']).to_excel(writer, sheet_name='质量分析', index=False)
                if 'cost' in full_result and full_result['cost'].get('media_detail'):
                    pd.DataFrame(full_result['cost']['media_detail']).to_excel(writer, sheet_name='成本分析', index=False)

        output.seek(0)
        filename = f"媒介分析报告_{report_type}_{analysis_id}.xlsx"

        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        logger.error(f"导出报告失败: {e}", exc_info=True)
        flash(f'❌ 导出报告失败: {str(e)}', 'error')
        return redirect(url_for('reports.dashboard', analysis_id=analysis_id))


@reports_bp.route('/export/invalid-data/<analysis_id>')
@login_required
def export_invalid_data(analysis_id):
    """导出无效数据为Excel"""
    try:
        analysis_data = load_analysis_result(analysis_id)
        if not analysis_data:
            flash('❌ 分析结果不存在', 'error')
            return redirect(url_for('reports.cost_report', analysis_id=analysis_id))

        full_result = analysis_data.get('full_result', {})
        cost_data = full_result.get('cost', {})
        invalid_data_detail = cost_data.get('invalid_data_detail', [])

        if not invalid_data_detail or len(invalid_data_detail) == 0:
            detailed_data = cost_data.get("detailed_data", [])
            if detailed_data and isinstance(detailed_data, list) and len(detailed_data) > 0:
                invalid_data_detail = []
                for idx, item in enumerate(detailed_data):
                    if isinstance(item, dict):
                        cost_invalid = item.get('成本无效', False)
                        if cost_invalid:
                            detail = {
                                '记录序号': idx + 1,
                                '达人昵称': item.get('达人昵称', '未知'),
                                '项目名称': item.get('项目名称', '未知'),
                                '定档媒介': item.get('定档媒介', '未知'),
                                '成本': float(item.get('成本', 0)) if item.get('成本') else 0,
                                '报价': float(item.get('报价', 0)) if item.get('报价') else 0,
                                '下单价': float(item.get('下单价', 0)) if item.get('下单价') else 0,
                                '返点': float(item.get('返点', 0)) if item.get('返点') else 0,
                                '返点比例': float(item.get('返点比例', 0)) * 100 if item.get('返点比例') else 0,
                                '成本无效原因': item.get('成本无效原因', '成本为0或缺失'),
                                '无效类型': '成本为0或缺失' if '成本为0' in item.get('成本无效原因', '') else '其他原因',
                                '是否被筛除': item.get('被筛除标志', False),
                                '筛除原因': item.get('筛除原因', ''),
                                '是否参与分析': False
                            }
                            invalid_data_detail.append(detail)

        if not invalid_data_detail:
            flash('⚠️ 无无效数据可导出', 'info')
            return redirect(url_for('reports.cost_report', analysis_id=analysis_id))

        df = pd.DataFrame(invalid_data_detail)
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='无效数据明细', index=False)

        output.seek(0)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"无效数据明细_{analysis_id}_{timestamp}.xlsx"

        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        logger.error(f"❌ 导出无效数据失败: {e}", exc_info=True)
        flash(f'❌ 导出失败: {str(e)}', 'error')
        return redirect(url_for('reports.cost_report', analysis_id=analysis_id))


@reports_bp.route('/export/abnormal-data/<analysis_id>')
@login_required
def export_abnormal_data(analysis_id):
    """导出异常数据为Excel"""
    try:
        analysis_data = load_analysis_result(analysis_id)
        if not analysis_data:
            flash('❌ 分析结果不存在', 'error')
            return redirect(url_for('reports.cost_report', analysis_id=analysis_id))

        full_result = analysis_data.get('full_result', {})
        cost_data = full_result.get('cost', {})
        abnormal_data_detail = cost_data.get('abnormal_data_detail', [])

        if not abnormal_data_detail or len(abnormal_data_detail) == 0:
            detailed_data = cost_data.get("detailed_data", [])
            if detailed_data and isinstance(detailed_data, list) and len(detailed_data) > 0:
                abnormal_data_detail = []
                for idx, item in enumerate(detailed_data):
                    if isinstance(item, dict):
                        data_abnormal = item.get('数据异常', False)
                        cost_invalid = item.get('成本无效', False)

                        if data_abnormal and not cost_invalid:
                            abnormal_reason = item.get('数据异常原因', '未知异常')
                            if '返点比例' in str(abnormal_reason):
                                abnormal_type = '返点异常'
                            elif '筛除' in str(abnormal_reason):
                                abnormal_type = '筛除异常'
                            else:
                                abnormal_type = '数据异常'

                            detail = {
                                '记录序号': idx + 1,
                                '达人昵称': item.get('达人昵称', '未知'),
                                '项目名称': item.get('项目名称', '未知'),
                                '定档媒介': item.get('定档媒介', '未知'),
                                '成本': float(item.get('成本', 0)) if item.get('成本') else 0,
                                '报价': float(item.get('报价', 0)) if item.get('报价') else 0,
                                '下单价': float(item.get('下单价', 0)) if item.get('下单价') else 0,
                                '返点': float(item.get('返点', 0)) if item.get('返点') else 0,
                                '返点比例': float(item.get('返点比例', 0)) * 100 if item.get('返点比例') else 0,
                                '数据异常原因': abnormal_reason,
                                '异常类型': abnormal_type,
                                '是否参与分析': True,
                                '参与分析标识': '异常数据'
                            }
                            abnormal_data_detail.append(detail)

        if not abnormal_data_detail:
            flash('⚠️ 无异常数据可导出', 'info')
            return redirect(url_for('reports.cost_abnormal_data_report', analysis_id=analysis_id))

        df = pd.DataFrame(abnormal_data_detail)
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='异常数据明细', index=False)

        output.seek(0)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"异常数据明细_{analysis_id}_{timestamp}.xlsx"

        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        logger.error(f"❌ 导出异常数据失败: {e}", exc_info=True)
        flash(f'❌ 导出失败: {str(e)}', 'error')
        return redirect(url_for('reports.cost_abnormal_data_report', analysis_id=analysis_id))


@reports_bp.route('/test-data/<analysis_id>')
@login_required
def test_data(analysis_id):
    """测试路由：查看内存中的数据"""
    if analysis_id in analysis_results:
        data = analysis_results[analysis_id]
        return jsonify({
            'success': True,
            'analysis_id': analysis_id,
            'keys': list(data.keys()),
            'full_result_keys': list(data.get('full_result', {}).keys()) if data.get('full_result') else [],
            'timestamp': data.get('timestamp', ''),
            'category': data.get('category', '')
        })
    else:
        result_file = os.path.join(app.config.get('OUTPUT_DIR', 'outputs'), 'analysis_results', f'{analysis_id}.json')
        if os.path.exists(result_file):
            with open(result_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return jsonify({
                'success': True,
                'source': 'file',
                'data_keys': list(data.keys())
            })
        return jsonify({'success': False, 'error': '数据不存在'})


@reports_bp.route('/download/audit-report/<analysis_id>')
@login_required
def download_audit_report(analysis_id):
    """下载审计报告（Word格式）"""
    try:
        # 加载分析结果
        analysis_data = load_analysis_result(analysis_id)
        if not analysis_data:
            flash('❌ 分析结果不存在', 'error')
            return redirect(url_for('reports.dashboard', analysis_id=analysis_id))

        # 使用报告生成器生成 Word 报告
        generator = ReportGenerator(data=analysis_data)
        output = generator.generate_word_report()

        # 生成文件名
        analysis_id_str = analysis_data.get('analysis_id', analysis_id)
        filename = f"媒介-审计报告_{analysis_id_str}.docx"

        # 返回文件供用户下载
        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )

    except Exception as e:
        logger.error(f"❌ 下载审计报告失败: {e}", exc_info=True)
        flash(f'❌ 下载审计报告失败: {str(e)}', 'error')
        return redirect(url_for('reports.dashboard', analysis_id=analysis_id))