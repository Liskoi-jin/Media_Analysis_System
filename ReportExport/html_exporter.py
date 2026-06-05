import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

STYLE = """
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: "Microsoft YaHei","Segoe UI",sans-serif; background:#f0f2f5; color:#333; padding:40px 20px; }
.container { max-width:1100px; margin:0 auto; background:#fff; border-radius:12px; box-shadow:0 4px 20px rgba(0,0,0,0.08); padding:40px 50px; }
h1 { font-size:22px; color:#1a1a2e; margin:30px 0 15px; padding-bottom:8px; border-bottom:3px solid #4361ee; }
h2 { font-size:18px; color:#4361ee; margin:24px 0 12px; }
h3 { font-size:15px; color:#1a1a2e; margin:18px 0 10px; }
.title { text-align:center; font-size:26px; font-weight:bold; color:#1a1a2e; margin-bottom:8px; }
.info { text-align:center; color:#888; font-size:13px; margin-bottom:30px; }
table { width:100%; border-collapse:collapse; margin:12px 0 20px; font-size:13px; }
th { background:#4361ee; color:#fff; padding:8px 10px; text-align:center; border:1px solid #4361ee; white-space:nowrap; }
th.orange { background:#E67E22; border-color:#E67E22; }
td { padding:6px 10px; border:1px solid #ddd; text-align:center; white-space:nowrap; color:#000; }
td.orange-bg { background:#FFF3E0; }
tr:nth-child(even) td:not(.orange-bg) { background:#f8f9ff; }
.note { font-size:12px; color:#888; margin-bottom:10px; }
.chart-row { display:flex; flex-wrap:wrap; gap:16px; justify-content:center; margin:12px 0 20px; }
.chart-row img { max-width:100%; border-radius:8px; border:1px solid #eee; }
.section-wrap { margin-bottom:8px; }
"""


def _build_media_sections(data):
    from ReportExport.report_generator import (
        build_summary_table_data, build_workload_detail_data,
        build_quality_detail_data, build_cost_performance_data,
        build_rebate_analysis_data, build_level_analysis_data,
        build_cost_analysis_data,
    )
    html = '<h1>一、总体分析</h1>'

    # 1. 总结
    html += '<h2>1、总结</h2>'
    table_rows = build_summary_table_data(data)
    if table_rows:
        headers = ['所属小组', '媒介人数', '签框量(口头)', '签框量(书面)', '总提报量', '总定档量', '平均定档数', '过筛率中位数', '平均定档成本']
        html += '<table><thead><tr>' + ''.join(f'<th class="orange">{h}</th>' for h in headers) + '</tr></thead><tbody>'
        for r in table_rows:
            cost = f"{r['avg_cost']:.2f}" if isinstance(r['avg_cost'], (int, float)) else str(r['avg_cost'])
            html += '<tr>' + ''.join(f'<td class="orange-bg">{r[k]}</td>' for k in ['group','media_count','kou','shu','tibao','dingdang','avg_dingdang','guoshuai']) + f'<td class="orange-bg">{cost}</td></tr>'
        html += '</tbody></table>'

    # 2. 工作量
    html += '<h2>2、工作量</h2><p class="note">注：离职人员已去除</p>'
    workload = build_workload_detail_data(data)
    if workload:
        group_hdr = {
            '耐消媒介组': '#F9A825',
            '快消媒介组': '#2d6a4f',
            'AI媒介组': '#4361ee',
        }
        group_bg = {
            '耐消媒介组': '#FFF8E1',
            '快消媒介组': '#e8f5e9',
            'AI媒介组': '#e3f2fd',
        }
        for g in workload:
            hc = group_hdr.get(g['group'], '#4361ee')
            bc = group_bg.get(g['group'], '#f8f9ff')
            html += f'<h3 style="color:{hc};">{g["group"]}</h3>'
            html += f'<table><thead><tr><th style="background:{hc};">姓名</th><th style="background:{hc};">提报数</th><th style="background:{hc};">定档数</th></tr></thead><tbody>'
            for p in g['people']:
                html += f'<tr><td style="background:{bc};">{p["name"]}</td><td style="background:{bc};">{p["tibao"]}</td><td style="background:{bc};">{p["dingdang"]}</td></tr>'
            html += '</tbody></table>'

    # 3. 工作质量
    html += '<h2>3、工作质量</h2><p class="note">注：由于各组的表头字段不统一，且与数据库字段不匹配，因此过筛滤以最终通过的过筛为准。</p>'
    premium = build_quality_detail_data(data, 'premium')
    if premium:
        html += '<h3>（1）优质达人</h3>'
        html += '<table><thead><tr><th style="background:#EF5350;color:#fff;font-weight:bold;">对应名字</th><th style="background:#EF5350;color:#fff;font-weight:bold;">所属小组</th><th style="background:#EF5350;color:#fff;font-weight:bold;">总提报达人数</th><th style="background:#EF5350;color:#fff;font-weight:bold;">过筛人数</th><th style="background:#EF5350;color:#fff;font-weight:bold;">过筛率(%)</th><th style="background:#EF5350;color:#fff;font-weight:bold;">质量评估</th></tr></thead><tbody>'
        for p in premium:
            html += f'<tr><td style="background:#FFEBEE;">{p["name"]}</td><td>{p["group"]}</td><td>{p["total"]}</td><td>{p["passed"]}</td><td>{p["rate_str"]}</td><td>{p["evaluation"]}</td></tr>'
        html += '</tbody></table>'
    high_read = build_quality_detail_data(data, 'high_read')
    if high_read:
        html += '<h3>（2）高阅读达人</h3>'
        html += '<table><thead><tr><th style="background:#EF5350;color:#fff;font-weight:bold;">对应名字</th><th style="background:#EF5350;color:#fff;font-weight:bold;">所属小组</th><th style="background:#EF5350;color:#fff;font-weight:bold;">总提报达人数</th><th style="background:#EF5350;color:#fff;font-weight:bold;">过筛人数</th><th style="background:#EF5350;color:#fff;font-weight:bold;">过筛率</th><th style="background:#EF5350;color:#fff;font-weight:bold;">过筛率(%)</th><th style="background:#EF5350;color:#fff;font-weight:bold;">质量评估</th></tr></thead><tbody>'
        for p in high_read:
            html += f'<tr><td style="background:#FFEBEE;">{p["name"]}</td><td>{p["group"]}</td><td>{p["total"]}</td><td>{p["passed"]}</td><td>{p["rate_decimal"]:.2f}</td><td>{p["rate_str"]}</td><td>{p["evaluation"]}</td></tr>'
        html += '</tbody></table>'

    # 4. 成本发挥
    html += '<h2>4、成本发挥</h2>'
    cost_perf = build_cost_performance_data(data)
    if cost_perf:
        html += '<table><thead><tr><th style="background:#42A5F5;color:#fff;font-weight:bold;">媒介组</th><th style="background:#42A5F5;color:#fff;font-weight:bold;">定档达人数</th><th style="background:#42A5F5;color:#fff;font-weight:bold;">平均返点比例(%)</th><th style="background:#42A5F5;color:#fff;font-weight:bold;">返点比例最高</th><th style="background:#42A5F5;color:#fff;font-weight:bold;">返点比例最低</th></tr></thead><tbody>'
        for r in cost_perf:
            html += f'<tr><td style="background:#E3F2FD;">{r["group"]}</td><td>{r["dingdang"]}</td><td>{r["avg_rebate"]}</td><td>{r["high"]}</td><td>{r["low"]}</td></tr>'
        html += '</tbody></table><p class="note">注：不含高返项目</p>'

        # 返点分析
        html += '<h3>（1）返点分析</h3><p class="note">①返点整体效益分析</p>'
        rebate_rows = build_rebate_analysis_data(data)
        if rebate_rows:
            headers = ['定档媒介', '定档达人数', '所属小组', '平均返点比例(%)', '返点比例最大值(%)', '返点比例最小值(%)', '返点比例中位数(%)',
                       '总返点金额(元)', '平均返点金额(元)', '返点金额最大值(元)', '返点金额最小值(元)', '返点金额中位数(元)', '返点表现评估', '返点优化建议']
            html += '<table style="font-size:12px;"><thead><tr>' + ''.join(f'<th style="background:#42A5F5;color:#fff;font-weight:bold;">{h}</th>' for h in headers) + '</tr></thead><tbody>'
            for r in rebate_rows:
                html += '<tr>'
                html += f'<td style="background:#E3F2FD">{r["name"]}</td>'
                html += ''.join(f'<td>{r[k]}</td>' for k in ['dingdang','group','avg_rebate','max_rebate','min_rebate','median_rebate'])
                html += ''.join(f'<td>{r[k]:.2f}</td>' for k in ['total_rebate_amt','avg_rebate_amt','max_rebate_amt','min_rebate_amt','median_rebate_amt'])
                html += f'<td>{r["evaluation"]}</td><td>{r["suggestion"]}</td></tr>'
            html += '</tbody></table>'

        # 达人量级分析
        html += '<p class="note">②基于达人量级分析</p>'
        lvl_rows = build_level_analysis_data(data)
        if lvl_rows:
            headers = ['定档媒介', '达人量级', '达人数', '所属小组', '总成本(元)', '平均成本(元)', '总返点金额(元)', '平均返点金额(元)',
                       '平均返点比例(%)', '总互动量', '平均互动量', '总阅读量', '平均阅读量', '平均CPE', '平均CPM']
            html += '<table style="font-size:12px;"><thead><tr>' + ''.join(f'<th style="background:#42A5F5;color:#fff;font-weight:bold;">{h}</th>' for h in headers) + '</tr></thead><tbody>'
            for r in lvl_rows:
                html += '<tr>'
                html += f'<td style="background:#E3F2FD">{r["name"]}</td>'
                html += f'<td>{r["level"]}</td><td>{r["count"]}</td><td>{r["group"]}</td>'
                html += f'<td>{r["total_cost"]:.2f}</td><td>{r["avg_cost"]:.2f}</td>'
                html += f'<td>{r["total_rebate"]:.2f}</td><td>{r["avg_rebate"]:.2f}</td><td>{r["avg_rebate_pct"]}</td>'
                html += f'<td>{r["total_interact"]:.0f}</td><td>{r["avg_interact"]:.2f}</td>'
                html += f'<td>{r["total_read"]:.0f}</td><td>{r["avg_read"]:.2f}</td>'
                html += f'<td>{r["avg_cpe"]:.2f}</td><td>{r["avg_cpm"]:.2f}</td></tr>'
            html += '</tbody></table>'

        # 成本分析
        html += '<h3>（2）成本分析</h3><p class="note">定档媒介成本分析</p>'
        cost_rows = build_cost_analysis_data(data)
        if cost_rows:
            headers = ['定档媒介', '定档达人数', '所属小组', '总成本(元)', '平均成本(元)', '成本最大值(元)', '成本最小值(元)', '成本中位数(元)',
                       '总报价(元)', '平均报价(元)', '报价最大值(元)', '报价最小值(元)', '总下单价(元)', '平均下单价(元)',
                       '总节约金额(元)', '平均节约金额(元)', '成本占比(%)', '总返点金额(元)', '平均返点金额(元)']
            html += '<table style="font-size:12px;"><thead><tr>' + ''.join(f'<th style="background:#42A5F5;color:#fff;font-weight:bold;">{h}</th>' for h in headers) + '</tr></thead><tbody>'
            for r in cost_rows:
                html += '<tr>'
                html += f'<td style="background:#E3F2FD">{r["name"]}</td>'
                html += f'<td>{r["count"]}</td><td>{r["group"]}</td>'
                html += f'<td>{r["total_cost"]:.2f}</td><td>{r["avg_cost"]:.2f}</td>'
                html += f'<td>{r["max_cost"]:.2f}</td><td>{r["min_cost"]:.2f}</td><td>{r["median_cost"]:.2f}</td>'
                html += f'<td>{r["total_quote"]:.2f}</td><td>{r["avg_quote"]:.2f}</td><td>{r["max_quote"]:.2f}</td><td>{r["min_quote"]:.2f}</td>'
                html += f'<td>{r["total_order"]:.2f}</td><td>{r["avg_order"]:.2f}</td>'
                html += f'<td>{r["total_save"]:.2f}</td><td>{r["avg_save"]:.2f}</td>'
                html += f'<td>{r["cost_pct"]}</td><td>{r["total_rebate"]:.2f}</td><td>{r["avg_rebate"]:.2f}</td></tr>'
            html += '</tbody></table>'
    return html


def _build_note_sections(note_data):
    from ReportExport.report_generator import (
        build_note_interaction_trend_data, build_note_viral_data,
        build_note_high_value_data, build_note_project_comparison_data,
    )
    analysis_types = note_data.get('analysis_types', [])
    has_content = 'content' in analysis_types
    has_value = 'value' in analysis_types
    has_review = 'review' in analysis_types

    if not (has_content or has_value or has_review):
        return ''

    html = '<h1>二、笔记分析</h1>'

    if has_content:
        trend_data = build_note_interaction_trend_data(note_data)
        stats = trend_data.get('stats', {})
        if stats:
            html += '<h2>内容表现分析</h2>'
            headers = ['总互动量', '平均互动量', '中位数互动量', '最大互动量', '平均互动率(%)', '中位数互动率(%)']
            keys = ['total_interaction', 'avg_interaction', 'median_interaction', 'max_interaction',
                    'avg_interaction_rate', 'median_interaction_rate']
            html += '<table><thead><tr>' + ''.join(f'<th style="background:#66BB6A;color:#fff;font-weight:bold;">{h}</th>' for h in headers) + '</tr></thead><tbody><tr>'
            for k in keys:
                html += f'<td style="background:#E8F5E9;">{stats.get(k, "-")}</td>'
            html += '</tr></tbody></table>'

        viral_data = build_note_viral_data(note_data)
        if viral_data:
            html += '<h2>爆款笔记分析</h2>'
            headers = ['达人昵称', '项目名称', '达人量级', '笔记类型', '互动量', '阅读量', '曝光量', '互动率(%)', 'cpm', 'cpe', '发布时间']
            for ti, tier in enumerate(['KOC', 'KOL', '十万KOL']):
                if tier not in viral_data:
                    continue
                html += f'<h3>1.{ti + 1} 爆款笔记 TOP（{tier}）</h3>'
                html += '<table><thead><tr>' + ''.join(f'<th style="background:#66BB6A;color:#fff;font-weight:bold;">{h}</th>' for h in headers) + '</tr></thead><tbody>'
                for n in viral_data[tier]:
                    html += '<tr>' + f'<td style="background:#E8F5E9;">{n["name"]}</td>' + ''.join(f'<td>{v}</td>' for v in [
                        n['project'], n['tier'], n['note_type'], str(n['interaction']),
                        str(n['read_count']), str(n['exposure']), n['interaction_rate'],
                        n['cpm'], n['cpe'], n['publish_time'][:10] if n['publish_time'] else '']) + '</tr>'
                html += '</tbody></table>'

    if has_value:
        hv_data = build_note_high_value_data(note_data)
        if hv_data:
            html += '<h2>高价值达人分析</h2>'
            headers = ['达人昵称', '达人量级', '互动量', '成本', 'CPE', '互动率(%)']
            for hti, tier in enumerate(['KOC', 'KOL', '十万KOL']):
                if tier not in hv_data:
                    continue
                html += f'<h3>2.{hti + 1} 高价值达人（{tier}）</h3>'
                html += '<table><thead><tr>' + ''.join(f'<th style="background:#66BB6A;color:#fff;font-weight:bold;">{h}</th>' for h in headers) + '</tr></thead><tbody>'
                for n in hv_data[tier]:
                    cost = f"{n['cost']:.2f}" if n['cost'] else '0'
                    html += f'<tr><td style="background:#E8F5E9;">{n["name"]}</td><td>{n["tier"]}</td><td>{n["interaction"]}</td><td>{cost}</td><td>{n["cpe"]}</td><td>{n["interaction_rate"]}</td></tr>'
                html += '</tbody></table>'

    if has_review:
        pc_rows = build_note_project_comparison_data(note_data)
        if pc_rows:
            html += '<h2>项目效果对比</h2>'
            headers = ['项目名称', '达人量级', '平均互动量', '平均阅读量', '平均成本', '平均CPM', '平均CPE', '平均互动率(%)', '综合得分', '效果评级']
            html += '<table><thead><tr>' + ''.join(f'<th style="background:#66BB6A;color:#fff;font-weight:bold;">{h}</th>' for h in headers) + '</tr></thead><tbody>'
            for r in pc_rows:
                vals = [r['project'], r['tier'], f"{r['avg_interaction']:.0f}", f"{r['avg_read']:.0f}",
                        f"{r['avg_cost']:.2f}", f"{r['avg_cpm']:.2f}", f"{r['avg_cpe']:.2f}",
                        f"{r['avg_rate']:.2f}", f"{r['score']:.2f}", r['rating']]
                html += '<tr><td style="background:#E8F5E9;">' + r['project'] + '</td>' + ''.join(f'<td>{v}</td>' for v in vals[1:]) + '</tr>'
            html += '</tbody></table>'
    return html


def build_html(data, note_data, week_label='', is_monthly=False):
    type_name = '月报' if is_monthly else '周报'
    title = f'媒介-审计报告（{week_label}）'

    body_html = ''
    if data:
        body_html += _build_media_sections(data)
    if note_data:
        body_html += '<hr style="margin:30px 0;border:none;border-top:2px dashed #4361ee;">'
        body_html += _build_note_sections(note_data)

    full_html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>{title}</title><style>{STYLE}</style></head>
<body>
<div class="container">
<div class="title">{title}</div>
<div class="info">生成日期: {datetime.now().strftime("%Y-%m-%d %H:%M")}</div>
{body_html}
<div style="text-align:center;margin-top:40px;padding-top:20px;border-top:1px solid #eee;color:#aaa;font-size:12px;">
    媒介-审计报告 · 由 LG-DBM 系统自动生成
</div>
</div>
</body>
</html>'''

    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'outputs', 'reports')
    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d%H%M%S')
    filename = f'审计报告_{week_label}_{ts}.html'
    filepath = os.path.join(output_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(full_html)
    logger.info(f"HTML导出成功: {filepath}")
    return filepath, filename
