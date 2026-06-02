# src/visualizations.py
"""
可视化模块 - 为三大独立分析模块生成交互式图表
支持Plotly图表，可直接嵌入HTML报告
"""
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from plotly.io import to_html


class VisualizationGenerator:
    """可视化生成器 - 为各独立模块生成专属图表"""

    def __init__(self):
        """初始化可视化生成器"""
        self.config = {
            "displayModeBar": True,
            "responsive": True,
            "toImageButtonOptions": {
                "format": "png",
                "filename": "chart",
                "height": 600,
                "width": 800,
            }
        }
        print("可视化生成器初始化完成")

    # ------------------------------ 工作量分析可视化 ------------------------------
    def workload_overview_chart(self, workload_df: pd.DataFrame) -> str:
        """工作量概览图表 - 各小组定档量对比"""
        if workload_df.empty:
            return self._empty_chart_html("无工作量数据")

        # 过滤非汇总数据
        non_summary_df = workload_df[~workload_df['媒介姓名'].str.endswith('_汇总') &
                                     (workload_df['媒介姓名'] != '总体汇总')]

        # 按小组聚合
        group_agg = non_summary_df.groupby('所属小组').agg({
            '定档量': 'sum',
            '总处理量': 'sum'
        }).reset_index()

        fig = px.bar(group_agg, x='所属小组', y=['定档量', '总处理量'],
                     barmode='group', title='各小组工作量对比',
                     labels={'value': '数量', 'variable': '指标'},
                     color_discrete_map={'定档量': '#2563EB', '总处理量': '#94A3B8'})
        fig.update_layout(height=400, width=800)
        return to_html(fig, full_html=False, config=self.config)

    def workload_ranking_chart(self, workload_df: pd.DataFrame, top_n: int = 15) -> str:
        """工作量排名图表 - 定档量TOP N媒介"""
        if workload_df.empty:
            return self._empty_chart_html("无工作量数据")

        # 过滤非汇总数据
        non_summary_df = workload_df[~workload_df['媒介姓名'].str.endswith('_汇总') &
                                     (workload_df['媒介姓名'] != '总体汇总')]
        top_media = non_summary_df.nlargest(top_n, '定档量')

        fig = px.bar(top_media, x='对应真名', y='定档量', color='所属小组',
                     title=f'定档量TOP {top_n}媒介',
                     labels={'定档量': '定档数量'},
                     color_discrete_sequence=px.colors.qualitative.Set3)
        fig.update_layout(height=400, width=800, xaxis_tickangle=-45)
        return to_html(fig, full_html=False, config=self.config)

    # ------------------------------ 工作质量分析可视化 ------------------------------
    def quality_overview_chart(self, quality_df: pd.DataFrame) -> str:
        """工作质量概览图表 - 各小组过筛率对比"""
        if quality_df.empty:
            return self._empty_chart_html("无工作质量数据")

        # 过滤小组汇总数据
        group_summary = quality_df[quality_df['定档媒介ID'].str.endswith('_汇总')]

        fig = px.bar(group_summary, x='所属小组', y='过筛率(%)',
                     title='各小组过筛率对比',
                     labels={'过筛率(%)': '过筛率'},
                     color='所属小组', color_discrete_sequence=px.colors.qualitative.Set2)
        fig.update_layout(height=400, width=800, yaxis_range=[0, 100])
        return to_html(fig, full_html=False, config=self.config)

    def quality_distribution_chart(self, quality_df: pd.DataFrame) -> str:
        """工作质量分布图表 - 质量评估分布"""
        if quality_df.empty:
            return self._empty_chart_html("无工作质量数据")

        # 过滤非汇总数据
        non_summary_df = quality_df[~quality_df['定档媒介ID'].str.endswith('_汇总') &
                                    (quality_df['定档媒介ID'] != '总体汇总')]

        quality_counts = non_summary_df['质量评估'].value_counts().reset_index()
        quality_counts.columns = ['质量等级', '媒介数量']

        fig = px.pie(quality_counts, values='媒介数量', names='质量等级',
                     title='媒介工作质量分布',
                     color_discrete_map={
                         '优秀': '#10B981', '良好': '#3B82F6',
                         '一般': '#F59E0B', '待改进': '#F97316', '较差': '#EF4444'
                     })
        fig.update_layout(height=400, width=600)
        return to_html(fig, full_html=False, config=self.config)

    # ------------------------------ 成本发挥分析可视化 ------------------------------
    def cost_efficiency_chart(self, cost_df: pd.DataFrame) -> str:
        """成本效益图表 - CPM/CPE对比"""
        if cost_df.empty:
            return self._empty_chart_html("无成本数据")

        # 过滤非汇总数据
        non_summary_df = cost_df[~cost_df['定档媒介ID'].str.endswith('_汇总') &
                                 (cost_df['定档媒介ID'] != '总体汇总')]
        non_summary_df = non_summary_df.dropna(subset=['平均CPM', '平均CPE'])

        fig = px.scatter(non_summary_df, x='平均CPM', y='平均CPE',
                         size='已发布达人数', color='所属小组',
                         hover_data=['对应名字', '已发布达人数'],
                         title='各媒介成本效益分布（气泡大小=已发布达人数）',
                         labels={'平均CPM': '平均CPM(元)', '平均CPE': '平均CPE(元)'},
                         color_discrete_sequence=px.colors.qualitative.Set1)
        fig.update_layout(height=500, width=800)
        return to_html(fig, full_html=False, config=self.config)

    def cost_group_chart(self, cost_df: pd.DataFrame) -> str:
        """成本小组对比图表 - 各小组成本指标"""
        if cost_df.empty:
            return self._empty_chart_html("无成本数据")

        # 过滤小组汇总数据
        group_summary = cost_df[cost_df['定档媒介ID'].str.endswith('_汇总')]

        fig = go.Figure()
        # 添加CPM柱状图
        fig.add_trace(go.Bar(x=group_summary['所属小组'], y=group_summary['平均CPM'],
                             name='平均CPM', marker_color='#EF4444'))
        # 添加CPE折线图
        fig.add_trace(go.Scatter(x=group_summary['所属小组'], y=group_summary['平均CPE'],
                                 name='平均CPE', mode='lines+markers', marker_color='#3B82F6'))

        fig.update_layout(height=400, width=800, title='各小组成本指标对比',
                          yaxis_title='金额(元)', xaxis_title='小组')
        return to_html(fig, full_html=False, config=self.config)

    def rebate_distribution_chart(self, cost_df: pd.DataFrame) -> str:
        """返点分布图表 - 各媒介返点比例"""
        if cost_df.empty:
            return self._empty_chart_html("无成本数据")

        # 过滤非汇总数据
        non_summary_df = cost_df[~cost_df['定档媒介ID'].str.endswith('_汇总') &
                                 (cost_df['定档媒介ID'] != '总体汇总')]
        non_summary_df = non_summary_df.dropna(subset=['平均返点比例(%)'])

        fig = px.histogram(non_summary_df, x='平均返点比例(%)', color='所属小组',
                           title='各媒介返点比例分布',
                           labels={'平均返点比例(%)': '平均返点比例(%)'},
                           color_discrete_sequence=px.colors.qualitative.Set3)
        fig.update_layout(height=400, width=800)
        return to_html(fig, full_html=False, config=self.config)

    def _empty_chart_html(self, message: str) -> str:
        """空数据时的占位图表"""
        return f"""
        <div class="empty-chart">
            <p>{message}</p>
        </div>
        """