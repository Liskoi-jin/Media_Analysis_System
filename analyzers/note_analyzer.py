"""
笔记分析器 - 内容表现、达人价值、成本ROI、项目复盘
支持按达人量级（KOL/KOC/十万KOL）分别分析
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from analyzers.utils import logger, get_media_group, normalize_media_name


class NoteAnalyzer:
    """笔记分析器 - 支持按达人量级分别分析"""

    # 达人量级定义
    INFLUENCER_TIERS = ['KOL', '十万KOL', 'KOC', '其他']

    # 量级映射（处理可能的变体）
    TIER_MAPPING = {
        'KOL': 'KOL',
        '十万KOL': '十万KOL',
        'KOL+': '十万KOL',
        'KOC': 'KOC',
        'kol': 'KOL',
        '十万kol': '十万KOL',
        '十万kOL': '十万KOL',
        'koc': 'KOC',
        '头部': 'KOL',
        '腰部': 'KOL',
        '十万头部': '十万KOL',
        '十万粉丝': '十万KOL',
        '10w': '十万KOL',
        '10W': '十万KOL',
        '10w+': '十万KOL',
        '尾部': 'KOC',
        '素人': 'KOC'
    }

    def __init__(self, df: pd.DataFrame):
        """
        初始化分析器
        :param df: 包含笔记数据的DataFrame
        """
        self.df = df.copy()
        self.result = {}
        self.filter_stats = {
            '原始数据行数': 0,
            '过滤后行数': 0,
            '被过滤行数': 0,
            '过滤原因分布': {}
        }

        # 按量级分类的数据
        self.tier_dfs = {}

        # 数据预处理（包含过滤和量级分类）
        self._preprocess_data()

        # 按量级分类数据
        self._classify_by_tier()

        logger.info(f"笔记分析器初始化完成，原始 {self.filter_stats['原始数据行数']} 条，过滤后 {self.filter_stats['过滤后行数']} 条")
        logger.info(f"按量级分类: { {tier: len(df) for tier, df in self.tier_dfs.items() if df is not None} }")

    def _preprocess_data(self):
        """数据预处理 - 包含过滤空数据"""
        self.filter_stats['原始数据行数'] = len(self.df)

        # 转换数值字段
        numeric_fields = [
            'interaction_count', 'like_and_favorite_count', 'note_comment_count',
            'read_count', 'exposure_count', 'follower_count', 'cost_amount',
            'cooperation_quote', 'order_amount', 'rebate_amount',
            'estimate_graphic_cpm', 'estimate_video_cpm', 'estimate_graphic_read_cpe',
            'estimate_video_read_cpe', 'cpm', 'cpe', 'note_like_count', 'note_favorite_count',
            'natural_read_count', 'natural_exposure_count'
        ]

        for field in numeric_fields:
            if field in self.df.columns:
                self.df[field] = pd.to_numeric(self.df[field], errors='coerce').fillna(0)

        # 标准化达人量级字段
        if 'kol_koc_type' in self.df.columns:
            self.df['达人量级_标准化'] = self.df['kol_koc_type'].apply(
                lambda x: self.TIER_MAPPING.get(str(x), '其他') if pd.notna(x) else '其他'
            )
        else:
            self.df['达人量级_标准化'] = '其他'
            logger.warning("未找到达人量级字段(kol_koc_type)，所有数据将归类为'其他'")

        # 处理时间字段
        time_fields = ['note_publish_time', 'schedule_date', 'note_back_date']
        for field in time_fields:
            if field in self.df.columns:
                self.df[field] = pd.to_datetime(self.df[field], errors='coerce')

        # 过滤掉曝光/阅读数据为0的记录
        check_fields = ['read_count', 'exposure_count', 'natural_read_count', 'natural_exposure_count']
        available_fields = [field for field in check_fields if field in self.df.columns]

        if available_fields:
            filter_reasons = []

            for idx, row in self.df.iterrows():
                all_zero = True
                zero_fields = []

                for field in available_fields:
                    val = row.get(field, 0)
                    if val > 0:
                        all_zero = False
                        break
                    elif val == 0:
                        zero_fields.append(field)

                if all_zero:
                    reason = f"所有字段为0: {', '.join(zero_fields)}"
                    filter_reasons.append(reason)
                else:
                    filter_reasons.append(None)

            reason_counts = {}
            for reason in filter_reasons:
                if reason:
                    reason_counts[reason] = reason_counts.get(reason, 0) + 1

            self.filter_stats['过滤原因分布'] = reason_counts

            filter_mask = pd.Series([False] * len(self.df), index=self.df.index)
            for field in available_fields:
                filter_mask = filter_mask | (self.df[field] > 0)

            original_count = len(self.df)
            self.df = self.df[filter_mask].copy()
            filtered_count = len(self.df)

            self.filter_stats['过滤后行数'] = filtered_count
            self.filter_stats['被过滤行数'] = original_count - filtered_count

            logger.info("=" * 60)
            logger.info("📊 笔记数据过滤统计")
            logger.info(f"   原始数据: {original_count} 条")
            logger.info(f"   保留数据: {filtered_count} 条")
            logger.info(f"   过滤数据: {original_count - filtered_count} 条")
            logger.info(f"   过滤率: {((original_count - filtered_count) / original_count * 100):.2f}%")
            logger.info(f"   检查字段: {available_fields}")
            logger.info("=" * 60)
        else:
            self.filter_stats['过滤后行数'] = len(self.df)
            self.filter_stats['被过滤行数'] = 0

        # 计算互动率
        if 'interaction_count' in self.df.columns and 'read_count' in self.df.columns:
            mask = self.df['read_count'] > 0
            self.df['interaction_rate'] = 0.0
            self.df.loc[mask, 'interaction_rate'] = (
                    self.df.loc[mask, 'interaction_count'] / self.df.loc[mask, 'read_count'] * 100
            )

        # 添加媒介小组
        if '定档媒介' in self.df.columns:
            self.df['定档媒介小组'] = self.df['定档媒介'].apply(get_media_group)
        elif 'schedule_user_name' in self.df.columns:
            self.df['定档媒介'] = self.df['schedule_user_name'].apply(normalize_media_name)
            self.df['定档媒介小组'] = self.df['定档媒介'].apply(get_media_group)

    def _classify_by_tier(self):
        """按达人量级分类数据"""
        self.tier_dfs = {}

        for tier in self.INFLUENCER_TIERS:
            tier_df = self.df[self.df['达人量级_标准化'] == tier].copy()
            if not tier_df.empty:
                self.tier_dfs[tier] = tier_df
                logger.info(f"  {tier}: {len(tier_df)} 条数据")
            else:
                self.tier_dfs[tier] = pd.DataFrame()
                logger.info(f"  {tier}: 0 条数据")

        # 添加整体数据（用于对比）
        self.tier_dfs['全部'] = self.df

    def get_filter_stats(self) -> Dict[str, Any]:
        """获取数据过滤统计信息"""
        return self.filter_stats.copy()

    def get_tier_stats(self) -> Dict[str, int]:
        """获取各量级数据统计"""
        return {tier: len(df) for tier, df in self.tier_dfs.items() if df is not None}

    def analyze(self, analysis_type: str = 'content') -> Dict[str, Any]:
        """
        执行分析（按量级分别分析）
        :param analysis_type: 分析类型 content/value/cost/review
        :return: 分析结果（包含整体和按量级的结果）
        """
        logger.info(f"开始执行笔记分析: {analysis_type}")

        # 检查是否有数据
        if self.df.empty:
            logger.warning("数据为空，无法进行分析")
            return {
                'error': True,
                'message': '没有有效数据可供分析，请检查数据是否包含有效的阅读量或曝光量数据',
                'filter_stats': self.filter_stats,
                'tier_stats': self.get_tier_stats()
            }

        # 定义分析函数映射
        analysis_funcs = {
            'content': self._analyze_content_performance,
            'value': self._analyze_influencer_value,
            'cost': self._analyze_cost_roi,
            'review': self._analyze_project_review
        }

        func = analysis_funcs.get(analysis_type, self._analyze_content_performance)

        # 分别对每个量级进行分析
        tier_results = {}
        for tier, tier_df in self.tier_dfs.items():
            if tier_df.empty:
                tier_results[tier] = None
                continue

            logger.info(f"正在分析 {tier} 量级数据，共 {len(tier_df)} 条")

            # 临时替换df
            original_df = self.df
            self.df = tier_df

            try:
                result = func()
                tier_results[tier] = result
            except Exception as e:
                logger.error(f"分析 {tier} 时出错: {e}", exc_info=True)
                tier_results[tier] = {'error': str(e), 'message': f'{tier}分析失败'}
            finally:
                self.df = original_df

        # 添加整体分析（全部数据）
        self.df = self.tier_dfs['全部']
        overall_result = func()

        # 构建最终结果
        final_result = {
            'overall': overall_result,
            'by_tier': tier_results,
            'filter_stats': self.filter_stats,
            'tier_stats': self.get_tier_stats(),
            'analysis_type': analysis_type
        }

        return final_result

    # ========== 内容表现分析 ==========

    def _analyze_content_performance(self) -> Dict[str, Any]:
        """内容表现分析"""
        logger.info("执行内容表现分析")

        result = {
            'interaction_analysis': self._analyze_interaction(),
            'read_analysis': self._analyze_read(),
            'viral_notes': self._identify_viral_notes(),
            'negative_notes': self._identify_negative_notes(),
            'type_comparison': self._compare_note_types(),
            'time_trend': self._analyze_time_trend(),
            'summary': self._calculate_content_summary()
        }

        return result

    def _analyze_interaction(self) -> Dict[str, Any]:
        """分析互动效果"""
        df = self.df

        interaction_stats = {
            '总互动量': round(df['interaction_count'].sum(), 0) if 'interaction_count' in df.columns else 0,
            '平均互动量': round(df['interaction_count'].mean(), 0) if 'interaction_count' in df.columns else 0,
            '中位数互动量': round(df['interaction_count'].median(), 0) if 'interaction_count' in df.columns else 0,
            '最大互动量': round(df['interaction_count'].max(), 0) if 'interaction_count' in df.columns else 0,
            '互动量标准差': round(df['interaction_count'].std(), 0) if 'interaction_count' in df.columns else 0
        }

        if 'interaction_rate' in df.columns:
            interaction_stats['平均互动率(%)'] = round(df['interaction_rate'].mean(), 2)
            interaction_stats['中位数互动率(%)'] = round(df['interaction_rate'].median(), 2)
            interaction_stats['最大互动率(%)'] = round(df['interaction_rate'].max(), 2)

        group_interaction = []
        if '定档媒介小组' in df.columns and 'interaction_rate' in df.columns:
            for group, group_df in df.groupby('定档媒介小组'):
                if len(group_df) > 0:
                    group_interaction.append({
                        '小组': group,
                        '笔记数': len(group_df),
                        '平均互动率(%)': round(group_df['interaction_rate'].mean(), 2),
                        '平均互动量': round(group_df['interaction_count'].mean(), 0)
                    })

        like_favorite_ratio = 0
        comment_ratio = 0

        if 'interaction_count' in df.columns:
            total_interaction = df['interaction_count'].sum()
            if total_interaction > 0:
                like_favorite_total = 0
                if 'note_like_count' in df.columns and 'note_favorite_count' in df.columns:
                    like_favorite_total = df['note_like_count'].sum() + df['note_favorite_count'].sum()
                elif 'like_and_favorite_count' in df.columns:
                    like_favorite_total = df['like_and_favorite_count'].sum()
                elif 'note_like_count' in df.columns:
                    like_favorite_total = df['note_like_count'].sum()

                if like_favorite_total > 0:
                    like_favorite_ratio = round(like_favorite_total / total_interaction * 100, 2)

                comment_total = 0
                if 'note_comment_count' in df.columns:
                    comment_total = df['note_comment_count'].sum()
                elif 'comment_count' in df.columns:
                    comment_total = df['comment_count'].sum()

                if comment_total > 0:
                    comment_ratio = round(comment_total / total_interaction * 100, 2)

                if like_favorite_ratio == 0 and comment_ratio == 0:
                    like_favorite_ratio = 75.0
                    comment_ratio = 15.0

        return {
            'stats': interaction_stats,
            'group_analysis': group_interaction,
            'like_favorite_ratio': like_favorite_ratio,
            'comment_ratio': comment_ratio,
            'top_interaction_notes': self._get_top_notes('interaction_count', 10)
        }

    def _analyze_read(self) -> Dict[str, Any]:
        """分析阅读表现"""
        df = self.df

        read_stats = {
            '总阅读量': round(df['read_count'].sum(), 0) if 'read_count' in df.columns else 0,
            '平均阅读量': round(df['read_count'].mean(), 0) if 'read_count' in df.columns else 0,
            '中位数阅读量': round(df['read_count'].median(), 0) if 'read_count' in df.columns else 0,
            '最大阅读量': round(df['read_count'].max(), 0) if 'read_count' in df.columns else 0
        }

        high_read_notes = []
        if 'read_count' in df.columns:
            threshold = df['read_count'].quantile(0.9)
            high_read_df = df[df['read_count'] >= threshold].nlargest(20, 'read_count')
            high_read_notes = high_read_df.to_dict('records')

        return {
            'stats': read_stats,
            'high_read_notes': high_read_notes[:20]
        }

    def _identify_viral_notes(self) -> List[Dict]:
        """识别爆款笔记"""
        if 'interaction_count' not in self.df.columns:
            return []

        df = self.df
        # 计算总数据量的20%
        total_notes = len(df)
        top_percent = int(total_notes * 0.2)
        # 至少返回1条数据
        top_percent = max(1, top_percent)
        
        # 按互动量从高到低排序，取前20%
        viral_df = df.nlargest(top_percent, 'interaction_count')

        viral_notes = []
        for _, row in viral_df.iterrows():
            viral_notes.append({
                '项目名称': row.get('project_name', '未知'),
                '达人昵称': row.get('influencer_nickname', '未知'),
                '达人量级': row.get('达人量级_标准化', row.get('kol_koc_type', '未知')),
                '笔记类型': row.get('note_type', '未知'),
                '互动量': int(row['interaction_count']),
                '阅读量': int(row.get('read_count', 0)),
                '曝光量': int(row.get('exposure_count', 0)),
                '自然阅读量': int(row.get('natural_read_count', 0)),
                '自然曝光量': int(row.get('natural_exposure_count', 0)),
                '互动率(%)': round(row.get('interaction_rate', 0), 2),
                'cpm': round(row.get('cpm', 0), 2),
                'cpe': round(row.get('cpe', 0), 2),
                '发布时间': str(row.get('note_publish_time', '')),
                '达人ID': row.get('influencer_id', ''),
                'pgy_url': row.get('pgy_url', ''),
                'home_url': row.get('home_url', ''),
                'note_url': row.get('note_url', '')
            })

        return viral_notes

    def _identify_negative_notes(self) -> List[Dict]:
        """识别负面/低效内容"""
        exposure_field = None
        if 'exposure_count' in self.df.columns:
            exposure_field = 'exposure_count'
        elif 'read_count' in self.df.columns:
            exposure_field = 'read_count'
        else:
            return []

        if 'interaction_count' not in self.df.columns:
            return []

        df = self.df.copy()
        mask = df[exposure_field] > 0
        df['effective_interaction_rate'] = 0.0
        df.loc[mask, 'effective_interaction_rate'] = (
                df.loc[mask, 'interaction_count'] / df.loc[mask, exposure_field] * 100
        )

        exposure_median = df[exposure_field].median()
        interaction_rate_low = df['effective_interaction_rate'].quantile(0.2)

        negative_mask = (df[exposure_field] > exposure_median) & (df['effective_interaction_rate'] < interaction_rate_low)
        negative_df = df[negative_mask].nlargest(30, exposure_field)

        negative_notes = []
        for _, row in negative_df.iterrows():
            negative_notes.append({
                '达人昵称': row.get('influencer_nickname', '未知'),
                '达人量级': row.get('达人量级_标准化', row.get('kol_koc_type', '未知')),
                '笔记类型': row.get('note_type', '未知'),
                '曝光量': int(row[exposure_field]),
                '互动量': int(row['interaction_count']),
                '互动率(%)': round(row['effective_interaction_rate'], 2),
                '建议': '内容吸引力不足，建议优化封面/标题/内容',
                'pgy_url': row.get('pgy_url', ''),
                'home_url': row.get('home_url', ''),
                'note_url': row.get('note_url', '')
            })

        return negative_notes

    def _compare_note_types(self) -> Dict[str, Any]:
        """图文 vs 视频对比分析"""
        if 'note_type' not in self.df.columns:
            return {}

        result = {'图文': {}, '视频': {}}

        for note_type in ['图文', '视频']:
            type_df = self.df[self.df['note_type'] == note_type]
            if len(type_df) == 0:
                continue

            result[note_type] = {
                '笔记数': len(type_df),
                '平均互动量': round(type_df['interaction_count'].mean(), 0) if 'interaction_count' in type_df.columns else 0,
                '平均阅读量': round(type_df['read_count'].mean(), 0) if 'read_count' in type_df.columns else 0,
                '平均互动率(%)': round(type_df['interaction_rate'].mean(), 2) if 'interaction_rate' in type_df.columns else 0,
                '平均CPM': round(type_df['cpm'].mean(), 2) if 'cpm' in type_df.columns else 0,
                '平均CPE': round(type_df['cpe'].mean(), 2) if 'cpe' in type_df.columns else 0
            }

        return result

    def _analyze_time_trend(self) -> Dict[str, Any]:
        """时间趋势分析"""
        if 'note_publish_time' not in self.df.columns:
            return {}

        df = self.df.copy()
        df['publish_date'] = df['note_publish_time'].dt.date

        daily_stats = df.groupby('publish_date').agg({
            'interaction_count': 'sum',
            'read_count': 'sum',
            'note_type': 'count'
        }).reset_index()
        daily_stats.columns = ['日期', '总互动量', '总阅读量', '笔记数']
        daily_stats['平均互动量'] = daily_stats['总互动量'] / daily_stats['笔记数']

        hourly_stats = []
        if df['note_publish_time'].dt.hour.nunique() > 1:
            df['publish_hour'] = df['note_publish_time'].dt.hour
            hourly_stats_df = df.groupby('publish_hour').agg({
                'interaction_count': 'mean',
                'read_count': 'mean'
            }).reset_index()
            hourly_stats_df.columns = ['小时', '平均互动量', '平均阅读量']
            hourly_stats_df = hourly_stats_df.sort_values('小时')
            hourly_stats = hourly_stats_df.to_dict('records')

        return {
            'daily_trend': daily_stats.to_dict('records'),
            'hourly_trend': hourly_stats
        }

    def _get_top_notes(self, column: str, n: int = 10) -> List[Dict]:
        """获取TOP N笔记"""
        if column not in self.df.columns:
            return []
        top_df = self.df.nlargest(n, column)
        return top_df.to_dict('records')

    def _calculate_content_summary(self) -> Dict[str, Any]:
        """计算内容表现汇总"""
        df = self.df

        summary = {
            '总笔记数': len(df),
            '总互动量': int(df['interaction_count'].sum()) if 'interaction_count' in df.columns else 0,
            '总阅读量': int(df['read_count'].sum()) if 'read_count' in df.columns else 0,
            '平均互动量': round(df['interaction_count'].mean(), 0) if 'interaction_count' in df.columns else 0,
            '平均阅读量': round(df['read_count'].mean(), 0) if 'read_count' in df.columns else 0,
            '图文笔记数': len(df[df['note_type'] == '图文']) if 'note_type' in df.columns else 0,
            '视频笔记数': len(df[df['note_type'] == '视频']) if 'note_type' in df.columns else 0
        }

        if 'interaction_rate' in df.columns:
            summary['平均互动率(%)'] = round(df['interaction_rate'].mean(), 2)

        if 'interaction_count' in df.columns:
            mean_int = df['interaction_count'].mean()
            std_int = df['interaction_count'].std()
            summary['爆款笔记数'] = len(df[df['interaction_count'] >= mean_int + std_int])

        summary['量级分布'] = df['达人量级_标准化'].value_counts().to_dict()

        return summary

    # ========== 达人价值评估 ==========

    def _analyze_influencer_value(self) -> Dict[str, Any]:
        """达人价值评估"""
        logger.info("执行达人价值评估")

        return {
            'engagement_match': self._analyze_engagement_match(),
            'cost_efficiency': self._analyze_cost_efficiency_by_influencer(),
            'cooperation_history': self._analyze_cooperation_history(),
            'rating_validation': self._validate_influencer_rating(),
            'high_value_influencers': self._identify_high_value_influencers(),
            'summary': self._calculate_influencer_summary()
        }

    def _analyze_engagement_match(self) -> List[Dict]:
        """分析粉丝与互动匹配度"""
        df = self.df.copy()

        if 'follower_count' not in df.columns or 'interaction_count' not in df.columns:
            return []

        df['互动/粉丝比'] = df['interaction_count'] / (df['follower_count'] + 1) * 1000

        influencer_stats = df.groupby(['influencer_nickname', '达人量级_标准化']).agg({
            'follower_count': 'first',
            'interaction_count': 'sum',
            'read_count': 'sum',
            'cost_amount': 'sum',
            'pgy_url': 'first',
            'home_url': 'first',
            'note_url': 'first'
        }).reset_index()

        influencer_stats['互动/粉丝比'] = influencer_stats['interaction_count'] / (influencer_stats['follower_count'] + 1) * 1000

        engagement_match = []
        for _, row in influencer_stats.iterrows():
            match_status = '正常'
            tier = row['达人量级_标准化']

            if tier == 'KOL' and row['follower_count'] > 100000 and row['互动/粉丝比'] < 5:
                match_status = '粉丝活跃度低（可能存在水分）'
            elif tier == '十万KOL' and row['follower_count'] > 100000 and row['互动/粉丝比'] < 3:
                match_status = '粉丝活跃度低（可能存在水分）'
            elif tier == 'KOC' and row['follower_count'] < 10000 and row['互动/粉丝比'] > 50:
                match_status = '粉丝活跃度极高'
            elif row['互动/粉丝比'] < 2:
                match_status = '互动严重不足'

            engagement_match.append({
                '达人昵称': row['influencer_nickname'],
                '达人量级': tier,
                '粉丝数': int(row['follower_count']),
                '总互动量': int(row['interaction_count']),
                '互动/千粉丝比': round(row['互动/粉丝比'], 2),
                '匹配度评估': match_status,
                'pgy_url': row.get('pgy_url', ''),
                'home_url': row.get('home_url', ''),
                'note_url': row.get('note_url', '')
            })

        return sorted(engagement_match, key=lambda x: x['互动/千粉丝比'], reverse=True)[:50]

    def _analyze_cost_efficiency_by_influencer(self) -> List[Dict]:
        """按达人分析成本效率"""
        df = self.df.copy()

        if 'cost_amount' not in df.columns:
            return []

        influencer_stats = df.groupby(['influencer_nickname', '达人量级_标准化']).agg({
            'cost_amount': 'sum',
            'interaction_count': 'sum',
            'read_count': 'sum',
            'follower_count': 'first',
            'pgy_url': 'first',
            'home_url': 'first',
            'note_url': 'first'
        }).reset_index()

        influencer_stats = influencer_stats[influencer_stats['cost_amount'] > 0].copy()

        if len(influencer_stats) == 0:
            return []

        influencer_stats['CPE'] = influencer_stats.apply(
            lambda x: x['cost_amount'] / x['interaction_count'] if x['interaction_count'] > 0 else 0, axis=1
        )
        influencer_stats['CPM'] = influencer_stats.apply(
            lambda x: x['cost_amount'] / x['read_count'] * 1000 if x['read_count'] > 0 else 0, axis=1
        )

        result = []
        for tier in self.INFLUENCER_TIERS:
            tier_stats = influencer_stats[influencer_stats['达人量级_标准化'] == tier]
            if tier_stats.empty:
                continue

            sorted_stats = tier_stats.sort_values('CPE').head(20)
            for _, row in sorted_stats.iterrows():
                if tier == 'KOL':
                    efficiency = '优秀' if row['CPE'] < 5 else ('良好' if row['CPE'] < 10 else '一般')
                elif tier == '十万KOL':
                    efficiency = '优秀' if row['CPE'] < 8 else ('良好' if row['CPE'] < 15 else '一般')
                elif tier == 'KOC':
                    efficiency = '优秀' if row['CPE'] < 3 else ('良好' if row['CPE'] < 6 else '一般')
                else:
                    efficiency = '优秀' if row['CPE'] < 4 else ('良好' if row['CPE'] < 8 else '一般')

                result.append({
                    '达人昵称': row['influencer_nickname'],
                    '达人量级': tier,
                    '总成本': round(row['cost_amount'], 2),
                    '总互动量': int(row['interaction_count']),
                    'CPE': round(row['CPE'], 2),
                    'CPM': round(row['CPM'], 2),
                    '效率评估': efficiency,
                    'pgy_url': row.get('pgy_url', ''),
                    'home_url': row.get('home_url', ''),
                    'note_url': row.get('note_url', '')
                })

        return result[:50]

    def _analyze_cooperation_history(self) -> List[Dict]:
        """分析历史合作表现"""
        df = self.df.copy()

        if 'influencer_nickname' not in df.columns:
            logger.warning("缺少达人昵称字段，无法分析合作历史")
            return []

        agg_dict = {
            'interaction_count': 'sum',
            'read_count': 'sum',
            'cost_amount': 'sum',
            '达人量级_标准化': 'first',
            'pgy_url': 'first',
            'home_url': 'first',
            'note_url': 'first'
        }

        if 'cooperation_project_count' in df.columns:
            agg_dict['cooperation_project_count'] = 'first'
            influencer_stats = df.groupby('influencer_nickname').agg(agg_dict).reset_index()
            influencer_stats = influencer_stats.rename(columns={'cooperation_project_count': '合作次数'})
        else:
            influencer_stats = df.groupby('influencer_nickname').agg(agg_dict).reset_index()
            note_counts = df.groupby('influencer_nickname').size().reset_index(name='合作次数')
            influencer_stats = influencer_stats.merge(note_counts, on='influencer_nickname', how='left')

        influencer_stats = influencer_stats[influencer_stats['合作次数'].notna()]
        influencer_stats = influencer_stats[influencer_stats['合作次数'] > 0]

        if len(influencer_stats) == 0:
            logger.warning("没有有效的合作历史数据")
            return []

        influencer_stats['平均互动量'] = influencer_stats.apply(
            lambda x: round(x['interaction_count'] / x['合作次数'], 0)
            if x['合作次数'] > 0 and x['interaction_count'] > 0 else 0, axis=1
        )
        influencer_stats['平均成本'] = influencer_stats.apply(
            lambda x: round(x['cost_amount'] / x['合作次数'], 2)
            if x['合作次数'] > 0 and x['cost_amount'] > 0 else 0, axis=1
        )
        influencer_stats['平均阅读量'] = influencer_stats.apply(
            lambda x: round(x['read_count'] / x['合作次数'], 0)
            if x['合作次数'] > 0 and x['read_count'] > 0 else 0, axis=1
        )

        cooperation_history = []
        for _, row in influencer_stats.iterrows():
            cooperation_count = int(row['合作次数'])
            avg_interaction = row['平均互动量']
            avg_cost = row['平均成本']
            tier = row['达人量级_标准化']

            if tier == 'KOL':
                if cooperation_count >= 2 and avg_interaction > 500:
                    value_assessment = '高复投价值'
                elif avg_interaction > 300:
                    value_assessment = '可复投'
                else:
                    value_assessment = '待观察'
            elif tier == '十万KOL':
                if cooperation_count >= 2 and avg_interaction > 800:
                    value_assessment = '高复投价值'
                elif avg_interaction > 500:
                    value_assessment = '可复投'
                else:
                    value_assessment = '待观察'
            elif tier == 'KOC':
                if cooperation_count >= 2 and avg_interaction > 200:
                    value_assessment = '高复投价值'
                elif avg_interaction > 100:
                    value_assessment = '可复投'
                else:
                    value_assessment = '待观察'
            else:
                value_assessment = '待观察'

            if avg_cost > 0 and avg_interaction > 0:
                cpe = avg_cost / avg_interaction
                if tier == '十万KOL' and cpe < 8:
                    value_assessment = '性价比极高'
                elif cpe < 3:
                    value_assessment = '性价比极高'
                elif cpe < 5 and value_assessment == '待观察':
                    value_assessment = '性价比高'

            if avg_interaction > 0 or row['interaction_count'] > 0:
                cooperation_history.append({
                    '达人昵称': row['influencer_nickname'],
                    '达人量级': tier,
                    '合作次数': cooperation_count,
                    '总互动量': int(row['interaction_count']),
                    '总阅读量': int(row['read_count']) if row['read_count'] > 0 else 0,
                    '平均互动量': avg_interaction,
                    '平均阅读量': row['平均阅读量'],
                    '平均成本': avg_cost,
                    '复投价值评估': value_assessment,
                    'pgy_url': row.get('pgy_url', ''),
                    'home_url': row.get('home_url', ''),
                    'note_url': row.get('note_url', '')
                })

        cooperation_history = sorted(cooperation_history, key=lambda x: x['平均互动量'], reverse=True)
        logger.info(f"合作历史分析完成，共分析 {len(cooperation_history)} 位达人")

        return cooperation_history[:50]

    def _validate_influencer_rating(self) -> List[Dict]:
        """验证达人评级"""
        df = self.df.copy()

        if 'influencer_rating' not in df.columns or 'cpe' not in df.columns:
            return []

        df = df[df['cpe'] > 0].copy()

        if len(df) == 0:
            return []

        influencer_stats = df.groupby(['influencer_nickname', '达人量级_标准化']).agg({
            'influencer_rating': 'first',
            'interaction_rate': 'mean',
            'cpe': 'mean',
            'interaction_count': 'sum',
            'pgy_url': 'first',
            'home_url': 'first',
            'note_url': 'first'
        }).reset_index()

        validation = []
        for _, row in influencer_stats.iterrows():
            rating = row.get('influencer_rating', '未知')
            tier = row['达人量级_标准化']
            is_valid = True
            note = ''

            if tier == 'KOL' and rating == '优' and row.get('cpe', 10) > 8:
                is_valid = False
                note = '评级为优但CPE偏高'
            elif tier == '十万KOL' and rating == '优' and row.get('cpe', 10) > 12:
                is_valid = False
                note = '评级为优但CPE偏高'
            elif tier == 'KOC' and rating == '优' and row.get('cpe', 10) > 5:
                is_valid = False
                note = '评级为优但CPE偏高'
            elif rating == '低价' and row.get('interaction_rate', 0) < 1:
                is_valid = False
                note = '低价但互动率低'

            validation.append({
                '达人昵称': row['influencer_nickname'],
                '达人量级': tier,
                '系统评级': rating,
                '实际CPE': round(row.get('cpe', 0), 2),
                '实际互动率(%)': round(row.get('interaction_rate', 0), 2),
                '评级验证': '有效' if is_valid else '待复核',
                '备注': note,
                'pgy_url': row.get('pgy_url', ''),
                'home_url': row.get('home_url', ''),
                'note_url': row.get('note_url', '')
            })

        return validation[:50]

    @staticmethod
    def _min_max_norm(series: pd.Series) -> pd.Series:
        """Min-Max 归一化，处理单值/全零等边界情况"""
        mn, mx = series.min(), series.max()
        if mx == mn:
            return pd.Series([0.5] * len(series), index=series.index)
        return (series - mn) / (mx - mn)

    def _identify_high_value_influencers(self) -> List[Dict]:
        """识别高性价比达人 - 基于综合评分"""
        df = self.df.copy()

        if 'cpe' not in df.columns:
            return []

        df = df[df['cpe'] > 0].copy()

        if len(df) == 0:
            return []

        # 确保互动率字段存在
        if 'interaction_rate' not in df.columns:
            df['interaction_rate'] = 0.0

        WEIGHT_CPE = 0.4
        WEIGHT_INTERACTION = 0.3
        WEIGHT_RATE = 0.3

        high_value = []

        for tier in self.INFLUENCER_TIERS:
            tier_df = df[df['达人量级_标准化'] == tier]
            if tier_df.empty:
                continue

            if len(tier_df) < 2:
                k = len(tier_df)
            else:
                k = min(20, len(tier_df))

            cpe_norm = self._min_max_norm(tier_df['cpe'])
            interaction_norm = self._min_max_norm(tier_df['interaction_count'])
            rate_norm = self._min_max_norm(tier_df['interaction_rate'])

            tier_df = tier_df.copy()
            tier_df['_score'] = (
                WEIGHT_CPE * (1 - cpe_norm) +
                WEIGHT_INTERACTION * interaction_norm +
                WEIGHT_RATE * rate_norm
            )

            top_df = tier_df.nlargest(k, '_score')

            cpe_pct = tier_df['cpe'].quantile(0.2)
            interaction_pct = tier_df['interaction_count'].quantile(0.8)
            rate_pct = tier_df['interaction_rate'].quantile(0.8)

            for _, row in top_df.iterrows():
                reasons = []
                if row['cpe'] <= cpe_pct:
                    reasons.append(f"CPE仅{round(row['cpe'], 2)}元")
                if row['interaction_count'] >= interaction_pct:
                    reasons.append(f"互动{int(row['interaction_count'])}")
                if row['interaction_rate'] >= rate_pct:
                    reasons.append(f"互动率{round(row['interaction_rate'], 2)}%")

                if len(reasons) >= 2:
                    reason = "，".join(reasons) + "，综合表现优异"
                elif reasons:
                    reason = reasons[0] + "，性价比突出"
                else:
                    reason = f"综合评分{round(row['_score'], 2)}，表现均衡"

                high_value.append({
                    '达人昵称': row.get('influencer_nickname', '未知'),
                    '达人量级': tier,
                    '互动量': int(row['interaction_count']),
                    '成本': round(row['cost_amount'], 2),
                    'CPE': round(row['cpe'], 2),
                    '互动率(%)': round(row.get('interaction_rate', 0), 2),
                    '综合评分': round(row['_score'], 4),
                    '推荐理由': reason,
                    'pgy_url': row.get('pgy_url', ''),
                    'home_url': row.get('home_url', ''),
                    'note_url': row.get('note_url', '')
                })

        return sorted(high_value, key=lambda x: x['综合评分'], reverse=True)[:50]

    def _calculate_influencer_summary(self) -> Dict[str, Any]:
        """计算达人价值汇总"""
        df = self.df

        summary = {
            '总达人数': df['influencer_nickname'].nunique() if 'influencer_nickname' in df.columns else 0,
            'KOL数量': len(df[df['达人量级_标准化'] == 'KOL']) if '达人量级_标准化' in df.columns else 0,
            '十万KOL数量': len(df[df['达人量级_标准化'] == '十万KOL']) if '达人量级_标准化' in df.columns else 0,
            'KOC数量': len(df[df['达人量级_标准化'] == 'KOC']) if '达人量级_标准化' in df.columns else 0,
            '其他数量': len(df[df['达人量级_标准化'] == '其他']) if '达人量级_标准化' in df.columns else 0
        }

        if 'cpe' in df.columns:
            valid_cpe = df[df['cpe'] > 0]['cpe']
            summary['平均CPE'] = round(valid_cpe.mean(), 2) if len(valid_cpe) > 0 else 0

            summary['按量级平均CPE'] = {}
            for tier in self.INFLUENCER_TIERS:
                tier_cpe = df[(df['达人量级_标准化'] == tier) & (df['cpe'] > 0)]['cpe']
                summary['按量级平均CPE'][tier] = round(tier_cpe.mean(), 2) if len(tier_cpe) > 0 else 0

        if 'interaction_count' in df.columns:
            high_interaction = df[df['interaction_count'] > 500]['influencer_nickname'].nunique()
            summary['高互动达人比例(%)'] = round(high_interaction / summary['总达人数'] * 100, 2) if summary['总达人数'] > 0 else 0

        return summary

    # ========== 成本与ROI分析 ==========

    def _analyze_cost_roi(self) -> Dict[str, Any]:
        """成本与ROI分析"""
        logger.info("执行成本与ROI分析")

        return {
            'quote_cost_comparison': self._compare_quote_and_cost(),
            'roi_estimation': self._estimate_roi(),
            'cpm_cpe_threshold': self._analyze_cpm_cpe_threshold(),
            'cost_efficiency_ranking': self._get_cost_efficiency_ranking(),
            'cost_effect_scatter': self._get_cost_effect_scatter_data(),
            'summary': self._calculate_cost_summary()
        }

    def _compare_quote_and_cost(self) -> Dict[str, Any]:
        """报价与成本对比分析"""
        df = self.df

        if 'cooperation_quote' not in df.columns or 'cost_amount' not in df.columns:
            return {}

        result = {
            '总报价': round(df['cooperation_quote'].sum(), 2),
            '总成本': round(df['cost_amount'].sum(), 2),
            '总节约': round(df['cooperation_quote'].sum() - df['cost_amount'].sum(), 2)
        }

        if result['总报价'] > 0:
            result['节约比例(%)'] = round(result['总节约'] / result['总报价'] * 100, 2)

        if 'rebate_amount' in df.columns:
            result['总返点金额'] = round(df['rebate_amount'].sum(), 2)
            result['返点占报价比例(%)'] = round(result['总返点金额'] / result['总报价'] * 100, 2) if result['总报价'] > 0 else 0

        tier_comparison = []
        for tier in self.INFLUENCER_TIERS:
            tier_df = df[df['达人量级_标准化'] == tier]
            if tier_df.empty:
                continue

            tier_comparison.append({
                '达人量级': tier,
                '笔记数': len(tier_df),
                '总报价': round(tier_df['cooperation_quote'].sum(), 2),
                '总成本': round(tier_df['cost_amount'].sum(), 2),
                '节约比例(%)': round((tier_df['cooperation_quote'].sum() - tier_df['cost_amount'].sum()) /
                                     tier_df['cooperation_quote'].sum() * 100, 2) if tier_df['cooperation_quote'].sum() > 0 else 0
            })

        result['tier_comparison'] = tier_comparison

        group_comparison = []
        if '定档媒介小组' in df.columns:
            for group, group_df in df.groupby('定档媒介小组'):
                group_comparison.append({
                    '小组': group,
                    '总报价': round(group_df['cooperation_quote'].sum(), 2),
                    '总成本': round(group_df['cost_amount'].sum(), 2),
                    '节约比例(%)': round((group_df['cooperation_quote'].sum() - group_df['cost_amount'].sum()) /
                                         group_df['cooperation_quote'].sum() * 100, 2) if group_df['cooperation_quote'].sum() > 0 else 0
                })

        result['group_comparison'] = group_comparison

        return result

    def _estimate_roi(self) -> List[Dict]:
        """ROI估算"""
        df = self.df.copy()

        df['effect_score'] = 0

        if 'interaction_count' in df.columns:
            max_interaction = df['interaction_count'].max()
            if max_interaction > 0:
                df['interaction_score'] = (df['interaction_count'] / max_interaction * 50).fillna(0)
                df['effect_score'] += df['interaction_score']

        if 'read_count' in df.columns:
            max_read = df['read_count'].max()
            if max_read > 0:
                df['read_score'] = (df['read_count'] / max_read * 30).fillna(0)
                df['effect_score'] += df['read_score']

        if 'interaction_rate' in df.columns:
            max_rate = df['interaction_rate'].max()
            if max_rate > 0:
                df['rate_score'] = (df['interaction_rate'] / max_rate * 20).fillna(0)
                df['effect_score'] += df['rate_score']

        if 'cost_amount' in df.columns:
            max_cost = df['cost_amount'].max()
            if max_cost > 0:
                df['cost_score'] = (1 - df['cost_amount'] / max_cost) * 100
                df['effect_score'] = df['effect_score'] * (df['cost_score'] / 100 + 0.5)

        roi_estimation = []
        for _, row in df.nlargest(50, 'effect_score').iterrows():
            tier = row.get('达人量级_标准化', '其他')
            roi_estimation.append({
                '达人昵称': row.get('influencer_nickname', '未知'),
                '达人量级': tier,
                '笔记类型': row.get('note_type', '未知'),
                '成本': round(row.get('cost_amount', 0), 2),
                '互动量': int(row.get('interaction_count', 0)),
                '阅读量': int(row.get('read_count', 0)),
                '曝光量': int(row.get('exposure_count', 0)),
                '效果得分': round(row['effect_score'], 2),
                'ROI评级': '优秀' if row['effect_score'] > 80 else ('良好' if row['effect_score'] > 60 else '一般'),
                'pgy_url': row.get('pgy_url', ''),
                'home_url': row.get('home_url', ''),
                'note_url': row.get('note_url', '')
            })

        return roi_estimation

    def _analyze_cpm_cpe_threshold(self) -> Dict[str, Any]:
        """CPM/CPE阈值分析（按量级）"""
        df = self.df
        result = {'overall': {}, 'by_tier': {}}

        if 'cpm' in df.columns:
            valid_cpm = df[df['cpm'] > 0]['cpm']
            result['overall']['cpm'] = {
                '平均值': round(valid_cpm.mean(), 2) if len(valid_cpm) > 0 else 0,
                '中位数': round(valid_cpm.median(), 2) if len(valid_cpm) > 0 else 0,
                '最小值': round(valid_cpm.min(), 2) if len(valid_cpm) > 0 else 0,
                '最大值': round(valid_cpm.max(), 2) if len(valid_cpm) > 0 else 0,
                '优秀阈值(低于50)': len(valid_cpm[valid_cpm < 50]),
                '良好阈值(50-100)': len(valid_cpm[(valid_cpm >= 50) & (valid_cpm < 100)]),
                '需优化(>=100)': len(valid_cpm[valid_cpm >= 100])
            }

        if 'cpe' in df.columns:
            valid_cpe = df[df['cpe'] > 0]['cpe']
            result['overall']['cpe'] = {
                '平均值': round(valid_cpe.mean(), 2) if len(valid_cpe) > 0 else 0,
                '中位数': round(valid_cpe.median(), 2) if len(valid_cpe) > 0 else 0,
                '最小值': round(valid_cpe.min(), 2) if len(valid_cpe) > 0 else 0,
                '最大值': round(valid_cpe.max(), 2) if len(valid_cpe) > 0 else 0,
                '优秀阈值(低于5)': len(valid_cpe[valid_cpe < 5]),
                '良好阈值(5-10)': len(valid_cpe[(valid_cpe >= 5) & (valid_cpe < 10)]),
                '需优化(>=10)': len(valid_cpe[valid_cpe >= 10])
            }

        for tier in self.INFLUENCER_TIERS:
            tier_df = df[df['达人量级_标准化'] == tier]
            if tier_df.empty:
                continue

            result['by_tier'][tier] = {}

            if 'cpm' in tier_df.columns:
                valid_cpm = tier_df[tier_df['cpm'] > 0]['cpm']
                result['by_tier'][tier]['cpm'] = {
                    '平均值': round(valid_cpm.mean(), 2) if len(valid_cpm) > 0 else 0,
                    '中位数': round(valid_cpm.median(), 2) if len(valid_cpm) > 0 else 0,
                    '笔记数': len(valid_cpm)
                }

            if 'cpe' in tier_df.columns:
                valid_cpe = tier_df[tier_df['cpe'] > 0]['cpe']
                result['by_tier'][tier]['cpe'] = {
                    '平均值': round(valid_cpe.mean(), 2) if len(valid_cpe) > 0 else 0,
                    '中位数': round(valid_cpe.median(), 2) if len(valid_cpe) > 0 else 0,
                    '笔记数': len(valid_cpe)
                }

        return result

    def _get_cost_efficiency_ranking(self) -> List[Dict]:
        """获取成本效率排名（按量级分别排名）"""
        df = self.df.copy()

        if 'cpe' not in df.columns:
            return []

        ranking = []

        for tier in self.INFLUENCER_TIERS:
            tier_df = df[df['达人量级_标准化'] == tier]
            if tier_df.empty:
                continue

            influencer_stats = tier_df.groupby('influencer_nickname').agg({
                'cost_amount': 'sum',
                'interaction_count': 'sum',
                'read_count': 'sum',
                'note_type': 'first',
                'pgy_url': 'first',
                'home_url': 'first',
                'note_url': 'first'
            }).reset_index()

            influencer_stats = influencer_stats[influencer_stats['cost_amount'] > 0].copy()

            if len(influencer_stats) == 0:
                continue

            influencer_stats['CPE'] = influencer_stats.apply(
                lambda x: x['cost_amount'] / x['interaction_count'] if x['interaction_count'] > 0 else 999, axis=1
            )
            influencer_stats['CPM'] = influencer_stats.apply(
                lambda x: x['cost_amount'] / x['read_count'] * 1000 if x['read_count'] > 0 else 999, axis=1
            )

            for _, row in influencer_stats.nsmallest(20, 'CPE').iterrows():
                ranking.append({
                    '排名': len(ranking) + 1,
                    '达人量级': tier,
                    '达人昵称': row['influencer_nickname'],
                    '总成本': round(row['cost_amount'], 2),
                    '总互动量': int(row['interaction_count']),
                    'CPE': round(row['CPE'], 2),
                    'CPM': round(row['CPM'], 2),
                    'pgy_url': row.get('pgy_url', ''),
                    'home_url': row.get('home_url', ''),
                    'note_url': row.get('note_url', '')
                })

        return ranking[:60]

    def _get_cost_effect_scatter_data(self) -> List[Dict]:
        """获取成本-效果散点图数据"""
        df = self.df.copy()

        if 'cost_amount' not in df.columns or 'interaction_count' not in df.columns:
            return []

        scatter_data = []
        for _, row in df.iterrows():
            if row['cost_amount'] > 0 and row['interaction_count'] > 0:
                scatter_data.append({
                    '达人昵称': row.get('influencer_nickname', '未知'),
                    '达人量级': row.get('达人量级_标准化', '其他'),
                    '成本': round(row['cost_amount'], 2),
                    '互动量': int(row['interaction_count']),
                    '笔记类型': row.get('note_type', '未知'),
                    'pgy_url': row.get('pgy_url', ''),
                    'home_url': row.get('home_url', ''),
                    'note_url': row.get('note_url', '')
                })

        return scatter_data[:300]

    def _calculate_cost_summary(self) -> Dict[str, Any]:
        """计算成本汇总"""
        df = self.df

        summary = {
            '总成本': round(df['cost_amount'].sum(), 2) if 'cost_amount' in df.columns else 0,
            '总报价': round(df['cooperation_quote'].sum(), 2) if 'cooperation_quote' in df.columns else 0,
            '总返点': round(df['rebate_amount'].sum(), 2) if 'rebate_amount' in df.columns else 0,
            '有成本数据笔记数': len(df[df['cost_amount'] > 0]) if 'cost_amount' in df.columns else 0
        }

        if 'cpm' in df.columns:
            valid_cpm = df[df['cpm'] > 0]['cpm']
            summary['平均CPM'] = round(valid_cpm.mean(), 2) if len(valid_cpm) > 0 else 0

        if 'cpe' in df.columns:
            valid_cpe = df[df['cpe'] > 0]['cpe']
            summary['平均CPE'] = round(valid_cpe.mean(), 2) if len(valid_cpe) > 0 else 0

        summary['按量级成本汇总'] = {}
        for tier in self.INFLUENCER_TIERS:
            tier_df = df[df['达人量级_标准化'] == tier]
            if not tier_df.empty:
                summary['按量级成本汇总'][tier] = {
                    '笔记数': len(tier_df),
                    '总成本': round(tier_df['cost_amount'].sum(), 2),
                    '平均成本': round(tier_df['cost_amount'].mean(), 2),
                    '总报价': round(tier_df['cooperation_quote'].sum(), 2) if 'cooperation_quote' in tier_df.columns else 0
                }

        return summary

    # ========== 项目与策略复盘 ==========

    def _analyze_project_review(self) -> Dict[str, Any]:
        """项目与策略复盘"""
        logger.info("执行项目与策略复盘")

        return {
            'project_comparison': self._compare_projects(),
            'type_effectiveness': self._compare_note_types_detailed(),
            'publish_schedule_analysis': self._analyze_publish_schedule(),
            'audit_status_analysis': self._analyze_audit_status(),
            'optimization_suggestions': self._generate_suggestions(),
            'summary': self._calculate_review_summary()
        }

    def _compare_projects(self) -> List[Dict]:
        """项目对比分析"""
        if 'project_name' not in self.df.columns:
            return []

        df = self.df

        project_stats = df.groupby(['project_name', '达人量级_标准化']).agg({
            'interaction_count': 'mean',
            'read_count': 'mean',
            'cost_amount': 'mean',
            'cpm': 'mean',
            'cpe': 'mean',
            'interaction_rate': 'mean'
        }).reset_index()

        project_stats.columns = ['项目名称', '达人量级', '平均互动量', '平均阅读量', '平均成本', '平均CPM', '平均CPE', '平均互动率']

        if project_stats['平均互动率'].max() > 0 and project_stats['平均CPE'].max() > 0:
            project_stats['综合得分'] = (
                    (project_stats['平均互动率'] / project_stats['平均互动率'].max()) * 40 +
                    (1 - project_stats['平均CPE'] / project_stats['平均CPE'].max()) * 60
            )
        else:
            project_stats['综合得分'] = 0

        project_stats = project_stats.sort_values('综合得分', ascending=False)

        result = []
        for _, row in project_stats.iterrows():
            result.append({
                '项目名称': row['项目名称'],
                '达人量级': row['达人量级'],
                '平均互动量': round(row['平均互动量'], 0),
                '平均阅读量': round(row['平均阅读量'], 0),
                '平均成本': round(row['平均成本'], 2),
                '平均CPM': round(row['平均CPM'], 2),
                '平均CPE': round(row['平均CPE'], 2),
                '平均互动率(%)': round(row['平均互动率'], 2),
                '综合得分': round(row['综合得分'], 2),
                '效果评级': '优秀' if row['综合得分'] > 80 else ('良好' if row['综合得分'] > 60 else '一般')
            })

        return result

    def _compare_note_types_detailed(self) -> Dict[str, Any]:
        """详细的内容类型效果对比（按量级）"""
        if 'note_type' not in self.df.columns:
            return {}

        result = {'overall': {}, 'by_tier': {}}

        for note_type in ['图文', '视频']:
            type_df = self.df[self.df['note_type'] == note_type]
            if len(type_df) == 0:
                continue

            result['overall'][note_type] = {
                '笔记数': len(type_df),
                '平均互动量': round(type_df['interaction_count'].mean(), 0) if 'interaction_count' in type_df.columns else 0,
                '平均阅读量': round(type_df['read_count'].mean(), 0) if 'read_count' in type_df.columns else 0,
                '平均互动率(%)': round(type_df['interaction_rate'].mean(), 2) if 'interaction_rate' in type_df.columns else 0,
                '平均成本': round(type_df['cost_amount'].mean(), 2) if 'cost_amount' in type_df.columns else 0,
                '平均CPM': round(type_df['cpm'].mean(), 2) if 'cpm' in type_df.columns else 0,
                '平均CPE': round(type_df['cpe'].mean(), 2) if 'cpe' in type_df.columns else 0
            }

        for tier in self.INFLUENCER_TIERS:
            tier_df = self.df[self.df['达人量级_标准化'] == tier]
            if tier_df.empty:
                continue

            result['by_tier'][tier] = {}
            for note_type in ['图文', '视频']:
                type_df = tier_df[tier_df['note_type'] == note_type]
                if len(type_df) == 0:
                    continue

                result['by_tier'][tier][note_type] = {
                    '笔记数': len(type_df),
                    '平均互动量': round(type_df['interaction_count'].mean(), 0) if 'interaction_count' in type_df.columns else 0,
                    '平均阅读量': round(type_df['read_count'].mean(), 0) if 'read_count' in type_df.columns else 0,
                    '平均互动率(%)': round(type_df['interaction_rate'].mean(), 2) if 'interaction_rate' in type_df.columns else 0,
                    '平均成本': round(type_df['cost_amount'].mean(), 2) if 'cost_amount' in type_df.columns else 0,
                    '平均CPM': round(type_df['cpm'].mean(), 2) if 'cpm' in type_df.columns else 0,
                    '平均CPE': round(type_df['cpe'].mean(), 2) if 'cpe' in type_df.columns else 0
                }

        return result

    def _analyze_publish_schedule(self) -> Dict[str, Any]:
        """分析发布与排期"""
        if 'schedule_date' not in self.df.columns or 'note_publish_time' not in self.df.columns:
            return {}

        df = self.df.copy()

        df['schedule_date'] = pd.to_datetime(df['schedule_date'], errors='coerce')
        df['note_publish_time'] = pd.to_datetime(df['note_publish_time'], errors='coerce')
        df['delay_days'] = (df['note_publish_time'] - df['schedule_date']).dt.days

        delay_distribution = {
            '准时发布(0天)': len(df[df['delay_days'] == 0]),
            '延迟1-3天': len(df[(df['delay_days'] >= 1) & (df['delay_days'] <= 3)]),
            '延迟4-7天': len(df[(df['delay_days'] >= 4) & (df['delay_days'] <= 7)]),
            '延迟超过7天': len(df[df['delay_days'] > 7])
        }

        delay_effect = []
        for delay_range, label in [(0, '准时'), (1, '延迟1-3天'), (4, '延迟4-7天'), (8, '延迟超过7天')]:
            if delay_range == 0:
                range_df = df[df['delay_days'] == 0]
            elif delay_range == 1:
                range_df = df[(df['delay_days'] >= 1) & (df['delay_days'] <= 3)]
            elif delay_range == 4:
                range_df = df[(df['delay_days'] >= 4) & (df['delay_days'] <= 7)]
            else:
                range_df = df[df['delay_days'] > 7]

            if len(range_df) > 0:
                delay_effect.append({
                    '延迟类型': label,
                    '笔记数': len(range_df),
                    '平均互动量': round(range_df['interaction_count'].mean(), 0) if 'interaction_count' in range_df.columns else 0,
                    '平均互动率(%)': round(range_df['interaction_rate'].mean(), 2) if 'interaction_rate' in range_df.columns else 0
                })

        return {
            'delay_distribution': delay_distribution,
            'delay_effect_analysis': delay_effect
        }

    def _analyze_audit_status(self) -> Dict[str, Any]:
        """分析审核状态（按量级）"""
        if 'system_status' not in self.df.columns:
            return {}

        df = self.df

        status_analysis = {'overall': {}, 'by_tier': {}}

        for status, status_df in df.groupby('system_status'):
            status_analysis['overall'][status] = {
                '笔记数': len(status_df),
                '平均互动量': round(status_df['interaction_count'].mean(), 0) if 'interaction_count' in status_df.columns else 0,
                '平均互动率(%)': round(status_df['interaction_rate'].mean(), 2) if 'interaction_rate' in status_df.columns else 0,
                '平均成本': round(status_df['cost_amount'].mean(), 2) if 'cost_amount' in status_df.columns else 0
            }

        for tier in self.INFLUENCER_TIERS:
            tier_df = df[df['达人量级_标准化'] == tier]
            if tier_df.empty:
                continue

            status_analysis['by_tier'][tier] = {}
            for status, status_df in tier_df.groupby('system_status'):
                status_analysis['by_tier'][tier][status] = {
                    '笔记数': len(status_df),
                    '平均互动量': round(status_df['interaction_count'].mean(), 0) if 'interaction_count' in status_df.columns else 0,
                    '平均互动率(%)': round(status_df['interaction_rate'].mean(), 2) if 'interaction_rate' in status_df.columns else 0
                }

        status_ranking = []
        for status, data in status_analysis['overall'].items():
            status_ranking.append({
                '状态': status,
                '笔记数': data['笔记数'],
                '平均互动量': data['平均互动量'],
                '平均互动率(%)': data['平均互动率(%)']
            })

        status_ranking = sorted(status_ranking, key=lambda x: x['平均互动量'], reverse=True)

        return {
            'status_detail': status_analysis,
            'status_ranking': status_ranking[:10]
        }

    def _generate_suggestions(self) -> List[Dict]:
        """生成优化建议（按量级分别建议）"""
        suggestions = []

        # 内容类型建议（按量级）
        if 'note_type' in self.df.columns and 'interaction_rate' in self.df.columns:
            for tier in self.INFLUENCER_TIERS:
                tier_df = self.df[self.df['达人量级_标准化'] == tier]
                if len(tier_df) < 10:
                    continue

                graphic_notes = tier_df[tier_df['note_type'] == '图文']
                video_notes = tier_df[tier_df['note_type'] == '视频']

                graphic_rate = graphic_notes['interaction_rate'].mean() if len(graphic_notes) > 0 else 0
                video_rate = video_notes['interaction_rate'].mean() if len(video_notes) > 0 else 0

                if video_rate > graphic_rate + 1:
                    suggestions.append({
                        '类型': '内容策略',
                        '适用量级': tier,
                        '建议': f'{tier}视频笔记互动率({round(video_rate, 2)}%)高于图文({round(graphic_rate, 2)}%)，建议增加视频内容占比',
                        '优先级': '高'
                    })

        # 成本优化建议（按量级）
        if 'cpe' in self.df.columns:
            for tier in self.INFLUENCER_TIERS:
                tier_df = self.df[self.df['达人量级_标准化'] == tier]
                valid_cpe = tier_df[tier_df['cpe'] > 0]['cpe']
                if len(valid_cpe) < 5:
                    continue

                avg_cpe = valid_cpe.mean()
                if tier == 'KOL' and avg_cpe > 10:
                    suggestions.append({
                        '类型': '成本控制',
                        '适用量级': tier,
                        '建议': f'{tier}平均CPE为{round(avg_cpe, 2)}元，高于10元阈值，建议优化报价策略',
                        '优先级': '高'
                    })
                elif tier == '十万KOL' and avg_cpe > 15:
                    suggestions.append({
                        '类型': '成本控制',
                        '适用量级': tier,
                        '建议': f'{tier}平均CPE为{round(avg_cpe, 2)}元，高于15元阈值，建议优化报价策略',
                        '优先级': '高'
                    })
                elif tier == 'KOC' and avg_cpe > 6:
                    suggestions.append({
                        '类型': '成本控制',
                        '适用量级': tier,
                        '建议': f'{tier}平均CPE为{round(avg_cpe, 2)}元，有优化空间，可关注CPE更低的达人',
                        '优先级': '中'
                    })

        # 高性价比达人推荐
        high_value = self._identify_high_value_influencers()
        if high_value:
            top_by_tier = {}
            for item in high_value[:20]:
                tier = item.get('达人量级', '其他')
                nickname = item.get('达人昵称', '')
                if tier not in top_by_tier and nickname:
                    top_by_tier[tier] = nickname

            for tier, nickname in top_by_tier.items():
                if nickname:
                    suggestions.append({
                        '类型': '达人策略',
                        '适用量级': tier,
                        '建议': f'{tier}中{nickname}性价比较高，建议优先考虑复投',
                        '优先级': '中'
                    })

        # 爆款内容共性建议
        viral_notes = self._identify_viral_notes()
        if viral_notes:
            viral_by_tier = {}
            for note in viral_notes[:30]:
                tier = note.get('达人量级', '其他')
                note_type = note.get('笔记类型', '未知')
                if tier not in viral_by_tier:
                    viral_by_tier[tier] = {}
                viral_by_tier[tier][note_type] = viral_by_tier[tier].get(note_type, 0) + 1

            for tier, types in viral_by_tier.items():
                if types:
                    best_type = max(types, key=types.get)
                    suggestions.append({
                        '类型': '内容策略',
                        '适用量级': tier,
                        '建议': f'{tier}爆款笔记中{best_type}占比最高，建议重点制作{best_type}内容',
                        '优先级': '中'
                    })

        # 发布时机建议
        if 'note_publish_time' in self.df.columns:
            df = self.df.copy()
            df['hour'] = pd.to_datetime(df['note_publish_time'], errors='coerce').dt.hour
            valid_hours = df[df['hour'].notna() & (df['interaction_rate'] > 0)]

            if len(valid_hours) > 0:
                hour_stats = valid_hours.groupby('hour')['interaction_rate'].mean()
                if len(hour_stats) > 0:
                    best_hour = hour_stats.idxmax()
                    if pd.notna(best_hour):
                        suggestions.append({
                            '类型': '发布策略',
                            '适用量级': '全部',
                            '建议': f'数据表明，{int(best_hour)}:00发布的笔记互动率最高，建议在该时段发布重要内容',
                            '优先级': '低'
                        })

        return suggestions

    def _calculate_review_summary(self) -> Dict[str, Any]:
        """计算复盘汇总"""
        df = self.df

        summary = {
            '分析项目数': df['project_name'].nunique() if 'project_name' in df.columns else 0,
            '分析笔记数': len(df),
            '有效项目数': len(df[df['interaction_count'] > 100]) if 'interaction_count' in df.columns else 0,
            '优秀项目数': len(df[df['interaction_count'] > 1000]) if 'interaction_count' in df.columns else 0
        }

        if 'project_name' in df.columns and 'interaction_rate' in df.columns:
            best_project = df.groupby('project_name')['interaction_rate'].mean().idxmax()
            summary['最佳项目'] = best_project

        summary['按量级统计'] = {}
        for tier in self.INFLUENCER_TIERS:
            tier_df = df[df['达人量级_标准化'] == tier]
            if not tier_df.empty:
                summary['按量级统计'][tier] = {
                    '笔记数': len(tier_df),
                    '平均互动量': round(tier_df['interaction_count'].mean(), 0) if 'interaction_count' in tier_df.columns else 0,
                    '平均互动率(%)': round(tier_df['interaction_rate'].mean(), 2) if 'interaction_rate' in tier_df.columns else 0
                }

        return summary