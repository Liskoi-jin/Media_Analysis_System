import json
import os
import logging
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, g, jsonify, send_file
from auth.utils import login_required

logger = logging.getLogger(__name__)

report_export_bp = Blueprint('report_export', __name__, url_prefix='/report_export')

RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'outputs', 'analysis_results')
NOTE_RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'outputs', 'note_analysis_results')

# 简单缓存：scan_analysis_results 结果缓存 30 秒
_scan_cache = {'time': 0, 'data': []}
_SCAN_CACHE_TTL = 30


def scan_analysis_results():
    global _scan_cache
    now = datetime.now().timestamp()
    if now - _scan_cache['time'] < _SCAN_CACHE_TTL and _scan_cache['data']:
        return _scan_cache['data']

    results = []
    if os.path.exists(RESULTS_DIR):
        for fname in sorted(os.listdir(RESULTS_DIR), reverse=True):
            if fname.endswith('.json'):
                fpath = os.path.join(RESULTS_DIR, fname)
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    analysis_id = data.get('analysis_id', fname.replace('.json', ''))
                    timestamp = data.get('timestamp', '')
                    category = data.get('category', '')
                    selected_groups = data.get('selected_groups', [])
                    has_workload = bool(data.get('full_result', {}).get('workload', {}).get('result'))
                    has_quality = bool(data.get('full_result', {}).get('quality', {}).get('result'))
                    has_cost = bool(data.get('full_result', {}).get('cost', {}).get('result'))
                    results.append({
                        'id': analysis_id,
                        'timestamp': timestamp,
                        'category': category,
                        'groups': selected_groups,
                        'type': '媒介分析',
                        'modules': [m for m, v in [('工作量', has_workload), ('质量', has_quality), ('成本', has_cost)] if v],
                        'source': 'analysis_results',
                        'filename': fname
                    })
                except Exception as e:
                    logger.warning(f"读取分析结果文件失败: {fname} - {e}")

    if os.path.exists(NOTE_RESULTS_DIR):
        for fname in sorted(os.listdir(NOTE_RESULTS_DIR), reverse=True):
            if fname.endswith('.json'):
                fpath = os.path.join(NOTE_RESULTS_DIR, fname)
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    analysis_id = data.get('analysis_id', fname.replace('.json', ''))
                    timestamp = data.get('timestamp', '')
                    analysis_types = data.get('analysis_types', [])
                    type_names = {'content': '内容表现', 'value': '达人价值', 'cost': '成本ROI', 'review': '项目复盘'}
                    results.append({
                        'id': analysis_id,
                        'timestamp': timestamp,
                        'category': '笔记分析',
                        'groups': [],
                        'type': '笔记分析',
                        'modules': [type_names.get(t, t) for t in analysis_types],
                        'source': 'note_analysis_results',
                        'filename': fname
                    })
                except Exception as e:
                    logger.warning(f"读取笔记分析结果文件失败: {fname} - {e}")

    _scan_cache = {'time': datetime.now().timestamp(), 'data': results}
    return results


@report_export_bp.route('/')
@login_required
def index():
    """报告导出首页 - 选择周报或月报"""
    return render_template('ReportExport/report_export_index.html', now=datetime.now())


@report_export_bp.route('/weekly')
@login_required
def weekly():
    """周报导出"""
    results = scan_analysis_results()
    media_results = [r for r in results if r.get('type') == '媒介分析']
    note_results = [r for r in results if r.get('type') == '笔记分析']
    return render_template('ReportExport/report_export_weekly.html',
        media_results=media_results, note_results=note_results, now=datetime.now())


@report_export_bp.route('/monthly')
@login_required
def monthly():
    """月报导出"""
    results = scan_analysis_results()
    media_results = [r for r in results if r.get('type') == '媒介分析']
    note_results = [r for r in results if r.get('type') == '笔记分析']
    return render_template('ReportExport/report_export_monthly.html',
        media_results=media_results, note_results=note_results, now=datetime.now())


@report_export_bp.route('/export_weekly', methods=['POST'])
@login_required
def export_weekly():
    """导出周报"""
    analysis_id = request.form.get('analysis_id')
    note_analysis_id = request.form.get('note_analysis_id', '')
    source = request.form.get('source', 'analysis_results')
    week_label = request.form.get('week_label', '')

    if not analysis_id and not note_analysis_id:
        flash('❌ 请至少选择一个分析结果', 'danger')
        return redirect(url_for('report_export.weekly'))

    try:
        from ReportExport.report_generator import generate_weekly_report, calc_week_label
        if not week_label:
            week_label = calc_week_label()
        filepath, filename = generate_weekly_report(
            analysis_id or '', source, week_label,
            note_analysis_id=note_analysis_id or '')
        return send_file(filepath, as_attachment=True, download_name=filename)
    except Exception as e:
        logger.error(f"导出周报失败: {e}", exc_info=True)
        flash(f'❌ 导出失败: {str(e)}', 'danger')
        return redirect(url_for('report_export.weekly'))


@report_export_bp.route('/export_html', methods=['POST'])
@login_required
def export_html():
    analysis_id = request.form.get('analysis_id', '')
    note_analysis_id = request.form.get('note_analysis_id', '')
    source = request.form.get('source', 'analysis_results')
    week_label = request.form.get('week_label', '')
    report_type = request.form.get('report_type', 'weekly')

    if not analysis_id and not note_analysis_id:
        flash('请至少选择一个分析结果', 'danger')
        bp_name = 'report_export.weekly' if report_type == 'weekly' else 'report_export.monthly'
        return redirect(url_for(bp_name))

    try:
        from ReportExport.html_exporter import build_html
        from ReportExport.report_generator import load_analysis_data, calc_week_label, calc_month_label
        if not week_label:
            week_label = calc_month_label() if report_type == 'monthly' else calc_week_label()
        data = load_analysis_data(analysis_id, source) if analysis_id else {}
        note_data = load_analysis_data(note_analysis_id, source='note_analysis_results') if note_analysis_id else {}
        filepath, filename = build_html(data, note_data, week_label, report_type == 'monthly')
        return send_file(filepath, as_attachment=True, download_name=filename)
    except Exception as e:
        logger.error(f"导出HTML失败: {e}", exc_info=True)
        flash(f'导出失败: {str(e)}', 'danger')
        bp_name = 'report_export.weekly' if report_type == 'weekly' else 'report_export.monthly'
        return redirect(url_for(bp_name))


@report_export_bp.route('/export_excel', methods=['POST'])
@login_required
def export_excel():
    analysis_id = request.form.get('analysis_id', '')
    note_analysis_id = request.form.get('note_analysis_id', '')
    source = request.form.get('source', 'analysis_results')
    week_label = request.form.get('week_label', '')
    report_type = request.form.get('report_type', 'weekly')

    if not analysis_id and not note_analysis_id:
        flash('请至少选择一个分析结果', 'danger')
        bp_name = 'report_export.weekly' if report_type == 'weekly' else 'report_export.monthly'
        return redirect(url_for(bp_name))

    try:
        from ReportExport.excel_exporter import build_excel
        from ReportExport.report_generator import load_analysis_data, calc_week_label, calc_month_label
        if not week_label:
            week_label = calc_month_label() if report_type == 'monthly' else calc_week_label()
        data = load_analysis_data(analysis_id, source) if analysis_id else {}
        note_data = load_analysis_data(note_analysis_id, source='note_analysis_results') if note_analysis_id else {}
        filepath, filename = build_excel(data, note_data, week_label, report_type == 'monthly')
        return send_file(filepath, as_attachment=True, download_name=filename)
    except Exception as e:
        logger.error(f"导出Excel失败: {e}", exc_info=True)
        flash(f'导出失败: {str(e)}', 'danger')
        bp_name = 'report_export.weekly' if report_type == 'weekly' else 'report_export.monthly'
        return redirect(url_for(bp_name))


@report_export_bp.route('/preview_weekly', methods=['POST'])
@login_required
def preview_weekly():
    """预览周报"""
    analysis_id = request.form.get('analysis_id', '')
    note_analysis_id = request.form.get('note_analysis_id', '')
    source = request.form.get('source', 'analysis_results')
    week_label = request.form.get('week_label', '')

    if not analysis_id and not note_analysis_id:
        return jsonify({'success': False, 'error': '请至少选择一个分析结果'})

    try:
        from ReportExport.report_generator import (load_analysis_data, calc_week_label,
            build_summary_table_data, build_workload_detail_data,
            build_chart_data, generate_chart_images, img_to_base64,
            build_quality_detail_data, build_cost_performance_data,
            build_rebate_analysis_data, build_level_analysis_data,
            build_cost_analysis_data, generate_rebate_chart_images,
            build_note_interaction_trend_data, generate_daily_interaction_chart,
            build_note_viral_data, build_note_high_value_data,
            build_note_project_comparison_data, HAS_MPL)
        if not week_label:
            week_label = calc_week_label()

        table_rows = []
        workload_detail = []
        premium_people = []
        high_read_people = []
        cost_performance = []
        rebate_analysis = []
        level_analysis = []
        cost_analysis = []
        chart_images = {}

        if analysis_id:
            data = load_analysis_data(analysis_id, source)
            table_rows = build_summary_table_data(data)
            workload_detail = build_workload_detail_data(data)
            premium_people = build_quality_detail_data(data, 'premium')
            high_read_people = build_quality_detail_data(data, 'high_read')
            cost_performance = build_cost_performance_data(data)
            rebate_analysis = build_rebate_analysis_data(data)
            level_analysis = build_level_analysis_data(data)
            cost_analysis = build_cost_analysis_data(data)

            if HAS_MPL:
                import tempfile
                tmpdir = tempfile.mkdtemp()
                chart_data = build_chart_data(data)
                paths = generate_chart_images(chart_data, tmpdir)
                for k, p in paths.items():
                    chart_images[k] = 'data:image/png;base64,' + img_to_base64(p)
                reb_paths = generate_rebate_chart_images(data, tmpdir)
                for k, p in reb_paths.items():
                    chart_images[k] = 'data:image/png;base64,' + img_to_base64(p)

        # 笔记分析
        note_sections = []
        if note_analysis_id:
            note_data = load_analysis_data(note_analysis_id, source='note_analysis_results')
            analysis_types = note_data.get('analysis_types', [])

            note_html_parts = []
            has_content = 'content' in analysis_types
            has_value = 'value' in analysis_types
            has_review = 'review' in analysis_types

            if has_content:
                trend_data = build_note_interaction_trend_data(note_data)
                stats = trend_data.get('stats', {})
                daily_trend = trend_data.get('daily_trend', [])

                # 内容表现分析表
                if stats:
                    stat_headers = ['总互动量', '平均互动量', '中位数互动量', '最大互动量', '平均互动率(%)', '中位数互动率(%)']
                    stat_keys = ['total_interaction', 'avg_interaction', 'median_interaction', 'max_interaction',
                                 'avg_interaction_rate', 'median_interaction_rate']
                    note_html_parts.append('<h4 style="font-size:12px;color:#4361ee;margin-top:14px;">内容表现分析</h4>')
                    note_html_parts.append('<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:10px;">')
                    note_html_parts.append('<tr>' + ''.join('<th style="background:#66BB6A;color:#fff;font-weight:bold;padding:5px;border:1px solid #ddd;text-align:center;white-space:nowrap;">' + h + '</th>' for h in stat_headers) + '</tr>')
                    note_html_parts.append('<tr>' + ''.join('<td style="padding:5px;border:1px solid #ddd;text-align:center;">' + str(stats.get(k, '-')) + '</td>' for k in stat_keys) + '</tr>')
                    note_html_parts.append('</table></div>')

                # 每日互动量趋势图
                if HAS_MPL and daily_trend:
                    import tempfile
                    tmpdir = tempfile.mkdtemp()
                    chart_paths = generate_daily_interaction_chart(trend_data, tmpdir)
                    if 'daily_interaction' in chart_paths:
                        chart_b64 = 'data:image/png;base64,' + img_to_base64(chart_paths['daily_interaction'])
                        note_html_parts.append('<h4 style="font-size:12px;color:#4361ee;margin-top:16px;">每日互动量趋势</h4>')
                        note_html_parts.append('<p style="text-align:center;font-size:10px;color:#666;">图: 每日互动量趋势（含均值线及3日移动平均线）</p>')
                        note_html_parts.append('<div style="text-align:center;"><img src="' + chart_b64 + '" style="max-width:100%;height:auto;"></div>')

                # 爆款笔记分析
                viral_data = build_note_viral_data(note_data)
                if viral_data:
                    tier_order = ['KOC', 'KOL', '十万KOL']
                    viral_headers = ['达人昵称', '项目名称', '达人量级', '笔记类型', '互动量', '阅读量',
                                     '曝光量', '互动率(%)', 'cpm', 'cpe', '发布时间', '蒲公英链接',
                                     '主页链接', '笔记链接']
                    note_html_parts.append('<h4 style="font-size:12px;color:#4361ee;margin-top:18px;">1.爆款笔记分析</h4>')
                    for ti, tier in enumerate(tier_order):
                        if tier not in viral_data:
                            continue
                        tier_label = {'KOC': 'KOC', 'KOL': 'KOL', '十万KOL': '十万KOL'}.get(tier, tier)
                        note_html_parts.append('<h5 style="font-size:11px;color:#1a1a2e;margin-top:14px;">1.%d 爆款笔记 TOP（%s）</h5>' % (ti + 1, tier_label))
                        note_html_parts.append('<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:7px;">')
                        note_html_parts.append('<tr>' + ''.join(
                            '<th style="background:#66BB6A;color:#fff;font-weight:bold;padding:3px;border:1px solid #ddd;text-align:center;white-space:nowrap;">' + h + '</th>'
                            for h in viral_headers) + '</tr>')
                        for ri, note in enumerate(viral_data[tier]):
                            bg = ri % 2 == 0 and '#fff' or '#f8f9fa'
                            vals = [
                                note['name'], note['project'], note['tier'], note['note_type'],
                                str(note['interaction']), str(note['read_count']),
                                str(note['exposure']), note['interaction_rate'],
                                note['cpm'], note['cpe'], note['publish_time'][:10] if note['publish_time'] else '',
                                '<a href="%s" target="_blank">蒲公英</a>' % note['pgy_url'] if note['pgy_url'] else '',
                                '<a href="%s" target="_blank">主页</a>' % note['home_url'] if note['home_url'] else '',
                                '<a href="%s" target="_blank">笔记</a>' % note['note_url'] if note['note_url'] else ''
                            ]
                            note_html_parts.append('<tr style="background:%s;">' % bg +
                                ''.join('<td style="padding:2px 3px;border:1px solid #ddd;text-align:center;%s">%s</td>' %
                                        ('background:#E8F5E9;' + ('max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;' if ci >= 11 else '') if ci == 0 else
                                         'max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;' if ci >= 11 else '', v)
                                        for ci, v in enumerate(vals)) + '</tr>')
                        note_html_parts.append('</table></div>')

            if has_value:
                hv_data = build_note_high_value_data(note_data)
                if hv_data:
                    note_html_parts.append('<h4 style="font-size:12px;color:#4361ee;margin-top:18px;">2.高价值达人分析</h4>')
                    hv_headers = ['达人昵称', '达人量级', '互动量', '成本', 'CPE', '互动率(%)',
                                  '蒲公英链接', '主页链接', '笔记链接']
                    hv_tier_order = ['KOC', 'KOL', '十万KOL']
                    for hti, tier in enumerate(hv_tier_order):
                        if tier not in hv_data:
                            continue
                        tier_label = {'KOC': 'KOC', 'KOL': 'KOL', '十万KOL': '十万KOL'}.get(tier, tier)
                        note_html_parts.append('<h5 style="font-size:11px;color:#1a1a2e;margin-top:14px;">2.%d 高价值达人（%s）</h5>' % (hti + 1, tier_label))
                        note_html_parts.append('<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:8px;">')
                        note_html_parts.append('<tr>' + ''.join(
                            '<th style="background:#66BB6A;color:#fff;font-weight:bold;padding:3px;border:1px solid #ddd;text-align:center;white-space:nowrap;">' + h + '</th>'
                            for h in hv_headers) + '</tr>')
                        for ri, note in enumerate(hv_data[tier]):
                            bg = ri % 2 == 0 and '#fff' or '#f8f9fa'
                            cost_str = '%.2f' % note['cost'] if note['cost'] else '0'
                            vals = [
                                note['name'], note['tier'], str(note['interaction']), cost_str,
                                note['cpe'], note['interaction_rate'],
                                '<a href="%s" target="_blank">蒲公英</a>' % note['pgy_url'] if note['pgy_url'] else '',
                                '<a href="%s" target="_blank">主页</a>' % note['home_url'] if note['home_url'] else '',
                                '<a href="%s" target="_blank">笔记</a>' % note['note_url'] if note['note_url'] else ''
                            ]
                            note_html_parts.append('<tr style="background:%s;">' % bg +
                                ''.join('<td style="padding:2px 4px;border:1px solid #ddd;text-align:center;%s">%s</td>' %
                                        ('background:#E8F5E9;' + ('max-width:100px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;' if ci >= 6 else '') if ci == 0 else
                                         'max-width:100px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;' if ci >= 6 else '', v)
                                        for ci, v in enumerate(vals)) + '</tr>')
                        note_html_parts.append('</table></div>')

            if has_review:
                pc_rows = build_note_project_comparison_data(note_data)
                if pc_rows:
                    note_html_parts.append('<h4 style="font-size:12px;color:#4361ee;margin-top:18px;">3.项目效果对比</h4>')
                    pc_headers = ['项目名称', '达人量级', '平均互动量', '平均阅读量', '平均成本',
                                  '平均CPM', '平均CPE', '平均互动率(%)', '综合得分', '效果评级']
                    note_html_parts.append('<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:8px;">')
                    note_html_parts.append('<tr>' + ''.join(
                        '<th style="background:#66BB6A;color:#fff;font-weight:bold;padding:3px;border:1px solid #ddd;text-align:center;white-space:nowrap;">' + h + '</th>'
                        for h in pc_headers) + '</tr>')
                    for ri, rr in enumerate(pc_rows):
                        bg = ri % 2 == 0 and '#fff' or '#f8f9fa'
                        rating_color = '#d4edda' if rr['rating'] == '优秀' else ('#cfe2ff' if rr['rating'] == '良好' else ('#fff3cd' if rr['rating'] == '一般' else '#f8d7da'))
                        vals = [
                            rr['project'], rr['tier'], '%.0f' % rr['avg_interaction'],
                            '%.0f' % rr['avg_read'], '%.2f' % rr['avg_cost'],
                            '%.2f' % rr['avg_cpm'], '%.2f' % rr['avg_cpe'],
                            '%.2f' % rr['avg_rate'], '%.2f' % rr['score'],
                            '<span style="background:%s;padding:2px 6px;border-radius:3px;font-weight:bold;">%s</span>' % (rating_color, rr['rating'])
                        ]
                        note_html_parts.append('<tr style="background:%s;">' % bg +
                            ''.join('<td style="padding:2px 4px;border:1px solid #ddd;text-align:center;%s">%s</td>' %
                                    ('background:#E8F5E9;' if ci == 0 else '', v)
                                    for ci, v in enumerate(vals)) + '</tr>')
                    note_html_parts.append('</table></div>')

            note_sections = [{'html': ''.join(note_html_parts)}] if note_html_parts else []

        return jsonify({
            'success': True,
            'title': f'媒介-审计报告（{week_label}）',
            'week_label': week_label,
            'table_data': table_rows,
            'workload_detail': workload_detail,
            'premium_people': premium_people,
            'high_read_people': high_read_people,
            'cost_performance': cost_performance,
            'rebate_analysis': rebate_analysis,
            'level_analysis': level_analysis,
            'cost_analysis': cost_analysis,
            'chart_images': chart_images,
            'note_sections': note_sections,
            'analysis_id': analysis_id
        })
    except Exception as e:
        logger.error(f"预览周报失败: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)})


@report_export_bp.route('/export_monthly', methods=['POST'])
@login_required
def export_monthly():
    """导出月报"""
    analysis_id = request.form.get('analysis_id')
    note_analysis_id = request.form.get('note_analysis_id', '')
    month_label = request.form.get('month_label', '')

    if not analysis_id and not note_analysis_id:
        flash('❌ 请至少选择一个分析结果', 'danger')
        return redirect(url_for('report_export.monthly'))

    try:
        from ReportExport.report_generator import generate_monthly_report, calc_month_label
        if not month_label:
            month_label = calc_month_label()
        filepath, filename = generate_monthly_report(
            analysis_id=analysis_id or '',
            source='analysis_results',
            month_label=month_label,
            note_analysis_id=note_analysis_id or ''
        )
        return send_file(filepath, as_attachment=True, download_name=filename)
    except Exception as e:
        logger.error(f"导出月报失败: {e}", exc_info=True)
        flash(f'❌ 导出失败: {str(e)}', 'danger')
        return redirect(url_for('report_export.monthly'))


@report_export_bp.route('/preview_monthly', methods=['POST'])
@login_required
def preview_monthly():
    """预览月报"""
    analysis_id = request.form.get('analysis_id', '')
    note_analysis_id = request.form.get('note_analysis_id', '')
    month_label = request.form.get('month_label', '')

    if not analysis_id and not note_analysis_id:
        return jsonify({'success': False, 'error': '请至少选择一个分析结果'})

    try:
        from ReportExport.report_generator import (load_analysis_data, calc_month_label,
            build_summary_table_data, build_workload_detail_data,
            build_chart_data, generate_chart_images, img_to_base64,
            build_quality_detail_data, build_cost_performance_data,
            build_rebate_analysis_data, build_level_analysis_data,
            build_cost_analysis_data, generate_rebate_chart_images,
            build_note_interaction_trend_data, generate_daily_interaction_chart,
            build_note_viral_data, build_note_high_value_data,
            build_note_project_comparison_data, HAS_MPL)
        if not month_label:
            month_label = calc_month_label()

        # 加载媒介分析数据
        table_rows = []
        workload_detail = []
        premium_people = []
        high_read_people = []
        cost_performance = []
        rebate_analysis = []
        level_analysis = []
        cost_analysis = []
        chart_images = {}

        if analysis_id:
            data = load_analysis_data(analysis_id)
            table_rows = build_summary_table_data(data)
            workload_detail = build_workload_detail_data(data)
            premium_people = build_quality_detail_data(data, 'premium')
            high_read_people = build_quality_detail_data(data, 'high_read')
            cost_performance = build_cost_performance_data(data)
            rebate_analysis = build_rebate_analysis_data(data)
            level_analysis = build_level_analysis_data(data)
            cost_analysis = build_cost_analysis_data(data)

            if HAS_MPL:
                import tempfile
                tmpdir = tempfile.mkdtemp()
                chart_data = build_chart_data(data)
                paths = generate_chart_images(chart_data, tmpdir)
                for k, p in paths.items():
                    chart_images[k] = 'data:image/png;base64,' + img_to_base64(p)
                reb_paths = generate_rebate_chart_images(data, tmpdir)
                for k, p in reb_paths.items():
                    chart_images[k] = 'data:image/png;base64,' + img_to_base64(p)

        # 加载笔记分析数据
        note_sections = []
        if note_analysis_id:
            note_data = load_analysis_data(note_analysis_id, source='note_analysis_results')
            analysis_types = note_data.get('analysis_types', [])
            has_content = 'content' in analysis_types
            has_value = 'value' in analysis_types
            has_review = 'review' in analysis_types

            note_html_parts = []

            if has_content:
                trend_data = build_note_interaction_trend_data(note_data)
                stats = trend_data.get('stats', {})
                daily_trend = trend_data.get('daily_trend', [])

                # 内容表现分析表
                if stats:
                    stat_headers = ['总互动量', '平均互动量', '中位数互动量', '最大互动量', '平均互动率(%)', '中位数互动率(%)']
                    stat_keys = ['total_interaction', 'avg_interaction', 'median_interaction', 'max_interaction',
                                 'avg_interaction_rate', 'median_interaction_rate']
                    note_html_parts.append('<h4 style="font-size:12px;color:#4361ee;margin-top:14px;">内容表现分析</h4>')
                    note_html_parts.append('<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:10px;">')
                    note_html_parts.append('<tr>' + ''.join('<th style="background:#66BB6A;color:#fff;font-weight:bold;padding:5px;border:1px solid #ddd;text-align:center;white-space:nowrap;">' + h + '</th>' for h in stat_headers) + '</tr>')
                    note_html_parts.append('<tr>' + ''.join('<td style="padding:5px;border:1px solid #ddd;text-align:center;">' + str(stats.get(k, '-')) + '</td>' for k in stat_keys) + '</tr>')
                    note_html_parts.append('</table></div>')

                # 每日互动量趋势图
                if HAS_MPL and daily_trend:
                    import tempfile
                    tmpdir = tempfile.mkdtemp()
                    chart_paths = generate_daily_interaction_chart(trend_data, tmpdir)
                    if 'daily_interaction' in chart_paths:
                        chart_b64 = 'data:image/png;base64,' + img_to_base64(chart_paths['daily_interaction'])
                        note_html_parts.append('<h4 style="font-size:12px;color:#4361ee;margin-top:16px;">每日互动量趋势</h4>')
                        note_html_parts.append('<p style="text-align:center;font-size:10px;color:#666;">图5: 每日互动量趋势（含均值线及3日移动平均线）</p>')
                        note_html_parts.append('<div style="text-align:center;"><img src="' + chart_b64 + '" style="max-width:100%;height:auto;"></div>')

                # 爆款笔记分析
                viral_data = build_note_viral_data(note_data)
                if viral_data:
                    note_html_parts.append('<h4 style="font-size:12px;color:#4361ee;margin-top:18px;">1.爆款笔记分析</h4>')
                    tier_order = ['KOC', 'KOL', '十万KOL']
                    viral_headers = ['达人昵称', '项目名称', '达人量级', '笔记类型', '互动量', '阅读量',
                                     '曝光量', '互动率(%)', 'cpm', 'cpe', '发布时间', '蒲公英链接',
                                     '主页链接', '笔记链接']
                    for ti, tier in enumerate(tier_order):
                        if tier not in viral_data:
                            continue
                        tier_label = {'KOC': 'KOC', 'KOL': 'KOL', '十万KOL': '十万KOL'}.get(tier, tier)
                        note_html_parts.append('<h5 style="font-size:11px;color:#1a1a2e;margin-top:14px;">1.%d 爆款笔记 TOP（%s）</h5>' % (ti + 1, tier_label))
                        note_html_parts.append('<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:7px;">')
                        note_html_parts.append('<tr>' + ''.join(
                            '<th style="background:#66BB6A;color:#fff;font-weight:bold;padding:3px;border:1px solid #ddd;text-align:center;white-space:nowrap;">' + h + '</th>'
                            for h in viral_headers) + '</tr>')
                        for ri, note in enumerate(viral_data[tier]):
                            bg = ri % 2 == 0 and '#fff' or '#f8f9fa'
                            vals = [
                                note['name'], note['project'], note['tier'], note['note_type'],
                                str(note['interaction']), str(note['read_count']),
                                str(note['exposure']), note['interaction_rate'],
                                note['cpm'], note['cpe'], note['publish_time'][:10] if note['publish_time'] else '',
                                '<a href="%s" target="_blank">蒲公英</a>' % note['pgy_url'] if note['pgy_url'] else '',
                                '<a href="%s" target="_blank">主页</a>' % note['home_url'] if note['home_url'] else '',
                                '<a href="%s" target="_blank">笔记</a>' % note['note_url'] if note['note_url'] else ''
                            ]
                            note_html_parts.append('<tr style="background:%s;">' % bg +
                                ''.join('<td style="padding:2px 3px;border:1px solid #ddd;text-align:center;%s">%s</td>' %
                                        ('background:#E8F5E9;' + ('max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;' if ci >= 11 else '') if ci == 0 else
                                         'max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;' if ci >= 11 else '', v)
                                        for ci, v in enumerate(vals)) + '</tr>')
                        note_html_parts.append('</table></div>')

            if has_value:
                hv_data = build_note_high_value_data(note_data)
                if hv_data:
                    note_html_parts.append('<h4 style="font-size:12px;color:#4361ee;margin-top:18px;">2.高价值达人分析</h4>')
                    hv_headers = ['达人昵称', '达人量级', '互动量', '成本', 'CPE', '互动率(%)',
                                  '蒲公英链接', '主页链接', '笔记链接']
                    hv_tier_order = ['KOC', 'KOL', '十万KOL']
                    for hti, tier in enumerate(hv_tier_order):
                        if tier not in hv_data:
                            continue
                        tier_label = {'KOC': 'KOC', 'KOL': 'KOL', '十万KOL': '十万KOL'}.get(tier, tier)
                        note_html_parts.append('<h5 style="font-size:11px;color:#1a1a2e;margin-top:14px;">2.%d 高价值达人（%s）</h5>' % (hti + 1, tier_label))
                        note_html_parts.append('<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:8px;">')
                        note_html_parts.append('<tr>' + ''.join(
                            '<th style="background:#66BB6A;color:#fff;font-weight:bold;padding:3px;border:1px solid #ddd;text-align:center;white-space:nowrap;">' + h + '</th>'
                            for h in hv_headers) + '</tr>')
                        for ri, note in enumerate(hv_data[tier]):
                            bg = ri % 2 == 0 and '#fff' or '#f8f9fa'
                            cost_str = '%.2f' % note['cost'] if note['cost'] else '0'
                            vals = [
                                note['name'], note['tier'], str(note['interaction']), cost_str,
                                note['cpe'], note['interaction_rate'],
                                '<a href="%s" target="_blank">蒲公英</a>' % note['pgy_url'] if note['pgy_url'] else '',
                                '<a href="%s" target="_blank">主页</a>' % note['home_url'] if note['home_url'] else '',
                                '<a href="%s" target="_blank">笔记</a>' % note['note_url'] if note['note_url'] else ''
                            ]
                            note_html_parts.append('<tr style="background:%s;">' % bg +
                                ''.join('<td style="padding:2px 4px;border:1px solid #ddd;text-align:center;%s">%s</td>' %
                                        ('background:#E8F5E9;' + ('max-width:100px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;' if ci >= 6 else '') if ci == 0 else
                                         'max-width:100px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;' if ci >= 6 else '', v)
                                        for ci, v in enumerate(vals)) + '</tr>')
                        note_html_parts.append('</table></div>')

            if has_review:
                pc_rows = build_note_project_comparison_data(note_data)
                if pc_rows:
                    note_html_parts.append('<h4 style="font-size:12px;color:#4361ee;margin-top:18px;">3.项目效果对比</h4>')
                    pc_headers = ['项目名称', '达人量级', '平均互动量', '平均阅读量', '平均成本',
                                  '平均CPM', '平均CPE', '平均互动率(%)', '综合得分', '效果评级']
                    note_html_parts.append('<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:8px;">')
                    note_html_parts.append('<tr>' + ''.join(
                        '<th style="background:#66BB6A;color:#fff;font-weight:bold;padding:3px;border:1px solid #ddd;text-align:center;white-space:nowrap;">' + h + '</th>'
                        for h in pc_headers) + '</tr>')
                    for ri, rr in enumerate(pc_rows):
                        bg = ri % 2 == 0 and '#fff' or '#f8f9fa'
                        rating_color = '#d4edda' if rr['rating'] == '优秀' else ('#cfe2ff' if rr['rating'] == '良好' else ('#fff3cd' if rr['rating'] == '一般' else '#f8d7da'))
                        vals = [
                            rr['project'], rr['tier'], '%.0f' % rr['avg_interaction'],
                            '%.0f' % rr['avg_read'], '%.2f' % rr['avg_cost'],
                            '%.2f' % rr['avg_cpm'], '%.2f' % rr['avg_cpe'],
                            '%.2f' % rr['avg_rate'], '%.2f' % rr['score'],
                            '<span style="background:%s;padding:2px 6px;border-radius:3px;font-weight:bold;">%s</span>' % (rating_color, rr['rating'])
                        ]
                        note_html_parts.append('<tr style="background:%s;">' % bg +
                            ''.join('<td style="padding:2px 4px;border:1px solid #ddd;text-align:center;%s">%s</td>' %
                                    ('background:#E8F5E9;' if ci == 0 else '', v)
                                    for ci, v in enumerate(vals)) + '</tr>')
                    note_html_parts.append('</table></div>')

            note_sections = [{'html': ''.join(note_html_parts)}] if note_html_parts else []

        return jsonify({
            'success': True,
            'title': f'媒介-审计报告（{month_label}）',
            'month_label': month_label,
            'table_data': table_rows,
            'workload_detail': workload_detail,
            'premium_people': premium_people,
            'high_read_people': high_read_people,
            'cost_performance': cost_performance,
            'rebate_analysis': rebate_analysis,
            'level_analysis': level_analysis,
            'cost_analysis': cost_analysis,
            'chart_images': chart_images,
            'note_sections': note_sections
        })
    except Exception as e:
        logger.error(f"预览月报失败: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)})
