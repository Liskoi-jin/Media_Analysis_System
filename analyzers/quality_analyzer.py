# analyzers/quality_analyzer.py
"""
工作质量分析器 - 完全对齐Media_Analysis.py的工作质量分析逻辑
输出表格字段：定档媒介ID,对应名字,所属小组,总提报达人数,过筛人数,过筛率(%),质量评估,主要状态分布
【重要】所有工作质量数据始终按小组排序（数码→家居→快消→其他）
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Any
from analyzers.utils import (
    logger, normalize_media_name, get_media_group,
    ID_TO_NAME_MAPPING
)


class QualityAnalyzer:
    def __init__(self, df: pd.DataFrame, known_id_name_mapping: Dict = None, config: Dict = None):
        """
        初始化工作质量分析器
        :param df: 处理后的DataFrame（必须包含'数据类型'标记）
        :param known_id_name_mapping: ID-真名映射表
        :param config: 配置字典
        """
        self.df = df.copy()
        self.known_id_name_mapping = known_id_name_mapping or {}
        self.config = config or {}

        # 存储分析结果
        self.result = {
            "summary": {},  # 汇总信息
            "detail": None,  # 详细数据
            "group_summary": None,  # 小组汇总
            "quality_distribution": None,  # 质量分布
            "premium_detail": None,  # 优质达人质量明细
            "high_read_detail": None,  # 高阅读达人质量明细
        }

        logger.info("工作质量分析器初始化完成")

    def analyze(self, use_original_state: bool = True) -> Dict[str, Any]:
        """
        执行完整工作质量分析
        :param use_original_state: 是否使用原始状态计算过筛率
        :return: 分析结果
        """
        logger.info("开始执行工作质量分析")
        try:
            # 1. 验证数据
            self._validate_data()

            # 2. 提取提报数据（工作质量分析只处理提报数据）
            reporting_df = self._extract_reporting_data()

            if reporting_df.empty:
                logger.warning("无提报数据可供工作质量分析")
                self.result["summary"] = {"提示": "无有效提报数据进行工作质量分析"}
                return self.result

            # 3. 处理媒介信息
            media_info_df = self._process_media_info(reporting_df)

            # 4. 计算媒介质量明细（核心逻辑）
            media_quality_detail = self._calculate_media_quality(media_info_df, use_original_state)

            # 5. 计算汇总信息
            self.result["summary"] = self._calculate_quality_summary(media_quality_detail)

            # 6. 存储明细数据（格式化输出）- 只保留所需字段
            self.result["detail"] = self._format_quality_detail(media_quality_detail)

            # 7. 计算小组汇总
            self.result["group_summary"] = self._calculate_group_summary(media_quality_detail)

            # 8. 计算质量分布
            self.result["quality_distribution"] = self._calculate_quality_distribution(media_quality_detail)

            # 9. 按influencer_purpose分类分析
            self.result["premium_detail"] = self._calculate_purpose_specific_quality(
                media_info_df, use_original_state, purpose_filter='优质达人'
            )
            self.result["high_read_detail"] = self._calculate_purpose_specific_quality(
                media_info_df, use_original_state, purpose_filter='高阅读达人'
            )

            logger.info("工作质量分析执行完成")
            return self.result

        except Exception as e:
            logger.error(f"工作质量分析执行失败: {e}", exc_info=True)
            raise

    def _validate_data(self) -> None:
        """验证数据是否包含必要字段"""
        required_fields = ['定档媒介', '状态', '数据类型']
        missing_fields = [f for f in required_fields if f not in self.df.columns]

        if missing_fields:
            raise ValueError(f"数据缺少必要字段: {missing_fields}")

        # 检查是否有提报数据
        if '数据类型' in self.df.columns:
            reporting_count = (self.df['数据类型'] == '提报').sum()
            if reporting_count == 0:
                logger.warning("数据中无'提报'类型数据")

    def _extract_reporting_data(self) -> pd.DataFrame:
        """提取提报数据"""
        logger.info("提取提报数据")

        if '数据类型' in self.df.columns:
            reporting_df = self.df[self.df['数据类型'] == '提报'].copy()
        else:
            # 如果没有数据类型标记，根据状态判断
            def is_reporting_status(status):
                if pd.isna(status):
                    return False
                status_str = str(status).upper()
                # 非定档状态视为提报
                return 'CHAIN_RETURNED' not in status_str and 'SCHEDULED' not in status_str

            status_col = self.df['状态'] if '状态' in self.df.columns else self.df.get('原始状态', '')
            reporting_mask = status_col.apply(is_reporting_status)
            reporting_df = self.df[reporting_mask].copy()
            reporting_df['数据类型'] = '提报'

        logger.info(f"提取到 {len(reporting_df)} 条提报数据")
        return reporting_df

    def _process_media_info(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        处理媒介信息（工作质量分析专用）
        """
        logger.info("处理媒介信息（工作质量分析）")
        df_processed = df.copy()

        # 1. 确定定档媒介ID
        if 'submit_media_user_id' in df_processed.columns:
            df_processed['submit_media_user_id'] = df_processed['submit_media_user_id'].astype(str).str.replace('.0', '', regex=False)
            df_processed['定档媒介ID'] = df_processed['submit_media_user_id']
        else:
            df_processed['定档媒介ID'] = ''

        # 2. 确定对应名字（真实姓名）
        df_processed['对应名字'] = '未知'

        # 优先使用submit_media_user_id映射真实姓名
        if 'submit_media_user_id' in df_processed.columns:
            for idx, row in df_processed.iterrows():
                submit_id = str(row.get('submit_media_user_id', '')).strip()
                if submit_id and submit_id.lower() not in ['', 'nan', 'none', 'null', '未知']:
                    submit_id = submit_id.replace('.0', '')
                    # 先从全局映射表查找
                    if submit_id in ID_TO_NAME_MAPPING:
                        real_name = ID_TO_NAME_MAPPING[submit_id]
                    elif submit_id in self.known_id_name_mapping:
                        real_name = self.known_id_name_mapping[submit_id]
                    else:
                        real_name = '未知'

                    if real_name != '未知':
                        df_processed.at[idx, '对应名字'] = real_name

        # 对于未知的，尝试submit_media_user_name
        mask_unknown = df_processed['对应名字'] == '未知'
        if mask_unknown.any() and 'submit_media_user_name' in df_processed.columns:
            for idx in df_processed[mask_unknown].index:
                submit_name = str(df_processed.at[idx, 'submit_media_user_name']).strip()
                if submit_name and submit_name.lower() not in ['', 'nan', 'none', 'null', '未知']:
                    real_name = normalize_media_name(submit_name)
                    if real_name != '未知':
                        df_processed.at[idx, '对应名字'] = real_name

        # 对于仍然未知的，尝试schedule_user_name
        mask_unknown = df_processed['对应名字'] == '未知'
        if mask_unknown.any() and 'schedule_user_name' in df_processed.columns:
            for idx in df_processed[mask_unknown].index:
                schedule_name = str(df_processed.at[idx, 'schedule_user_name']).strip()
                if schedule_name and schedule_name.lower() not in ['', 'nan', 'none', 'null', '未知']:
                    real_name = normalize_media_name(schedule_name)
                    if real_name != '未知':
                        df_processed.at[idx, '对应名字'] = real_name

        # 最后清理
        df_processed['对应名字'] = df_processed['对应名字'].replace(['', 'nan', 'NaN', 'None', 'null'], '未知')

        # 3. 确定所属小组（使用真实姓名查小组）
        df_processed['所属小组'] = df_processed['对应名字'].apply(get_media_group)

        # 4. 确保定档媒介字段
        if '定档媒介' not in df_processed.columns:
            df_processed['定档媒介'] = df_processed['对应名字']

        logger.info(f"媒介信息处理完成，唯一媒介数: {df_processed['对应名字'].nunique()}")
        logger.info(f"小组分布: {df_processed['所属小组'].value_counts().to_dict()}")
        return df_processed

    def _compute_quality_stats(self, df: pd.DataFrame, use_original_state: bool) -> pd.DataFrame:
        """计算媒介质量统计（核心逻辑提取，供两个入口方法复用）"""
        if use_original_state and '原始状态' in df.columns:
            status_col = '原始状态'
        else:
            status_col = '状态'

        df = df.copy()
        df['分析状态'] = df[status_col].fillna('UNKNOWN').astype(str).str.upper()

        df['是否过筛'] = df['分析状态'].apply(
            lambda s: any(kw in str(s).upper() for kw in ['SCREENING_PASSED', 'CHAIN_RETURNED', 'SCHEDULED'])
        )

        media_stats = df.groupby(['定档媒介ID', '对应名字', '所属小组']).agg(
            总提报达人数=('是否过筛', 'count'),
            过筛人数=('是否过筛', 'sum')
        ).reset_index()

        media_stats['过筛率'] = np.where(
            media_stats['总提报达人数'] > 0,
            (media_stats['过筛人数'] / media_stats['总提报达人数'] * 100).round(2), 0.0
        )
        media_stats['过筛率(%)'] = media_stats['过筛率'].astype(str) + "%"

        def evaluate_quality(rate):
            if rate >= 80: return "优秀"
            if rate >= 65: return "良好"
            if rate >= 50: return "一般"
            if rate >= 40: return "待改进"
            return "较差"

        media_stats['质量评估'] = media_stats['过筛率'].apply(evaluate_quality)

        def get_main_status_distribution(statuses):
            if not statuses:
                return "无状态数据"
            status_counts = {}
            for status in statuses:
                s = str(status).upper()
                key = ('过筛通过' if 'SCREENING_PASSED' in s else
                       '已发布' if 'CHAIN_RETURNED' in s else
                       '已排期' if 'SCHEDULED' in s else
                       '过筛失败' if 'SCREENING_FAILED' in s else
                       '已拒绝' if 'REJECTED' in s else '其他')
                status_counts[key] = status_counts.get(key, 0) + 1
            items = [f"{s}:{c}({c/len(statuses)*100:.1f}%)"
                     for s, c in sorted(status_counts.items(), key=lambda x: x[1], reverse=True)]
            return "; ".join(items[:3])

        media_stats['主要状态分布'] = df.groupby(['定档媒介ID', '对应名字', '所属小组'])['分析状态'].apply(
            lambda x: get_main_status_distribution(x.tolist())
        ).reset_index(drop=True)

        group_order = {'耐消媒介组': 1, '家居媒介组': 2, '快消媒介组': 3}
        eval_order = {'优秀': 1, '良好': 2, '一般': 3, '待改进': 4, '较差': 5}

        media_stats['小组排序'] = media_stats['所属小组'].map(lambda x: group_order.get(x, 99))
        media_stats['质量评估排序'] = media_stats['质量评估'].map(eval_order)

        media_stats = media_stats.sort_values(
            ['小组排序', '质量评估排序', '过筛率', '总提报达人数'],
            ascending=[True, True, False, False]
        ).drop(['小组排序', '质量评估排序'], axis=1).reset_index(drop=True)

        return media_stats

    def _calculate_media_quality(self, df: pd.DataFrame, use_original_state: bool) -> pd.DataFrame:
        logger.info("计算媒介工作质量明细（始终按小组排序）")
        result = self._compute_quality_stats(df, use_original_state)
        logger.info(f"媒介工作质量计算完成，共 {len(result)} 个媒介，按小组排序")
        return result

    def _calculate_purpose_specific_quality(self, df: pd.DataFrame, use_original_state: bool,
                                            purpose_filter: str) -> pd.DataFrame:
        logger.info(f"计算 {purpose_filter} 工作质量明细")
        if 'influencer_purpose' not in df.columns:
            logger.warning(f"数据中无'influencer_purpose'列，无法进行{purpose_filter}分析")
            return pd.DataFrame()

        purpose_df = df[df['influencer_purpose'] == purpose_filter].copy()
        if purpose_df.empty:
            logger.warning(f"无{purpose_filter}数据")
            return pd.DataFrame()

        result = self._compute_quality_stats(purpose_df, use_original_state)
        if not result.empty:
            result['达人类型'] = purpose_filter
        logger.info(f"{purpose_filter} 工作质量计算完成，共 {len(result)} 个媒介")
        return result

    def _format_quality_detail(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        格式化工作质量明细输出（只保留所需字段）
        """
        required_columns = [
            '定档媒介ID', '对应名字', '所属小组', '总提报达人数',
            '过筛人数', '过筛率(%)', '质量评估', '主要状态分布'
        ]

        # 确保所有列都存在
        for col in required_columns:
            if col not in df.columns:
                if col == '过筛率(%)':
                    df[col] = '0.00%'
                elif col == '质量评估':
                    df[col] = '未知'
                elif col == '主要状态分布':
                    df[col] = '无数据'
                else:
                    df[col] = 0

        # 按指定顺序排列
        df = df[required_columns].copy()

        return df

    def _format_purpose_detail(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        格式化分类工作质量明细输出
        """
        if df.empty:
            return df

        required_columns = [
            '定档媒介ID', '对应名字', '所属小组', '达人类型', '总提报达人数',
            '过筛人数', '过筛率(%)', '质量评估', '主要状态分布'
        ]

        for col in required_columns:
            if col not in df.columns:
                if col == '过筛率(%)':
                    df[col] = '0.00%'
                elif col in ['质量评估', '达人类型']:
                    df[col] = '未知'
                elif col == '主要状态分布':
                    df[col] = '无数据'
                else:
                    df[col] = 0

        df = df[required_columns].copy()
        return df

    def _calculate_quality_summary(self, detail_df: pd.DataFrame) -> Dict[str, Any]:
        """计算工作质量分析汇总信息"""
        logger.info("计算工作质量分析汇总信息")

        if detail_df.empty:
            return {"提示": "无工作质量数据"}

        summary = {}

        # 基础统计
        summary['媒介总数'] = len(detail_df)
        summary['总提报达人数'] = int(detail_df['总提报达人数'].sum())
        summary['总过筛人数'] = int(detail_df['过筛人数'].sum())

        # 整体过筛率
        if summary['总提报达人数'] > 0:
            overall_rate = (summary['总过筛人数'] / summary['总提报达人数'] * 100)
            summary['总体过筛率(%)'] = round(overall_rate, 2)
        else:
            summary['总体过筛率(%)'] = 0.0

        # 质量评估统计
        if '质量评估' in detail_df.columns:
            quality_counts = detail_df['质量评估'].value_counts().to_dict()
            summary['质量评估分布'] = quality_counts

            summary['优秀质量媒介数'] = int(quality_counts.get('优秀', 0))
            summary['良好质量媒介数'] = int(quality_counts.get('良好', 0))
            summary['一般质量媒介数'] = int(quality_counts.get('一般', 0))
            summary['待改进质量媒介数'] = int(quality_counts.get('待改进', 0))
            summary['较差质量媒介数'] = int(quality_counts.get('较差', 0))

        # 平均指标
        if summary['媒介总数'] > 0:
            summary['平均提报达人数'] = round(summary['总提报达人数'] / summary['媒介总数'], 1)
            summary['平均过筛人数'] = round(summary['总过筛人数'] / summary['媒介总数'], 1)

        # 小组分布
        if '所属小组' in detail_df.columns:
            group_dist = detail_df.groupby('所属小组')['总提报达人数'].sum().sort_values(ascending=False).head(5).to_dict()
            summary['主要小组提报分布'] = group_dist

        logger.info(f"工作质量汇总计算完成，总媒介数: {summary['媒介总数']}")
        return summary

    def _calculate_group_summary(self, detail_df: pd.DataFrame) -> pd.DataFrame:
        """计算小组工作质量汇总"""
        logger.info("计算小组工作质量汇总")

        if detail_df.empty or '所属小组' not in detail_df.columns:
            return pd.DataFrame()

        # 确保过筛率数值字段存在
        df_for_calc = detail_df.copy()
        if '过筛率' not in df_for_calc.columns and '过筛率(%)' in df_for_calc.columns:
            # 从字符串格式提取数值
            df_for_calc['过筛率'] = df_for_calc['过筛率(%)'].apply(
                lambda x: float(str(x).replace('%', '')) if pd.notna(x) else 0.0
            )
        elif '过筛率' not in df_for_calc.columns:
            df_for_calc['过筛率'] = 0.0

        group_summary = df_for_calc.groupby('所属小组').agg(
            媒介数量=('对应名字', 'nunique'),
            总提报达人数=('总提报达人数', 'sum'),
            总过筛人数=('过筛人数', 'sum'),
            优秀媒介数=('质量评估', lambda x: (x == '优秀').sum()),
            良好媒介数=('质量评估', lambda x: (x == '良好').sum()),
            过筛率中位数=('过筛率', lambda x: np.median([v for v in x if pd.notna(v)]))
        ).reset_index()

        # 计算小组过筛率
        group_summary['小组过筛率'] = np.where(
            group_summary['总提报达人数'] > 0,
            (group_summary['总过筛人数'] / group_summary['总提报达人数'] * 100).round(2),
            0.0
        )
        group_summary['小组过筛率(%)'] = group_summary['小组过筛率'].astype(str) + "%"

        # 格式化过筛率中位数（处理可能的NaN值）
        group_summary['过筛率中位数'] = group_summary['过筛率中位数'].fillna(0.0)
        group_summary['过筛率中位数(%)'] = group_summary['过筛率中位数'].round(2).astype(str) + "%"

        # 计算优秀良好占比
        group_summary['优秀良好媒介数'] = group_summary['优秀媒介数'] + group_summary['良好媒介数']
        group_summary['优秀良好占比(%)'] = np.where(
            group_summary['媒介数量'] > 0,
            (group_summary['优秀良好媒介数'] / group_summary['媒介数量'] * 100).round(2),
            0.0
        )
        group_summary['优秀良好占比(%)'] = group_summary['优秀良好占比(%)'].astype(str) + "%"

        # 计算占比
        total_reporting = group_summary['总提报达人数'].sum()
        group_summary['提报量占比(%)'] = np.where(
            total_reporting > 0,
            (group_summary['总提报达人数'] / total_reporting * 100).round(2),
            0.0
        )
        group_summary['提报量占比(%)'] = group_summary['提报量占比(%)'].astype(str) + "%"

        # 按小组顺序排序
        group_order_mapping = {
            '耐消媒介组': 1,
            '家居媒介组': 2,
            '快消媒介组': 3
        }
        group_summary['小组排序'] = group_summary['所属小组'].map(
            lambda x: group_order_mapping.get(x, 99)
        )
        group_summary = group_summary.sort_values('小组排序', ascending=True)
        group_summary = group_summary.drop('小组排序', axis=1)

        # 重新排列列顺序
        column_order = [
            '所属小组', '媒介数量', '总提报达人数', '提报量占比(%)',
            '总过筛人数', '小组过筛率(%)', '过筛率中位数(%)', '优秀媒介数', '良好媒介数', '优秀良好占比(%)'
        ]

        existing_columns = [col for col in column_order if col in group_summary.columns]
        group_summary = group_summary[existing_columns]

        logger.info(f"小组汇总计算完成，共 {len(group_summary)} 个小组")
        return group_summary

    def _calculate_quality_distribution(self, detail_df: pd.DataFrame) -> pd.DataFrame:
        """计算质量评估分布"""
        logger.info("计算质量评估分布")

        if detail_df.empty or '质量评估' not in detail_df.columns:
            return pd.DataFrame()

        quality_dist = detail_df['质量评估'].value_counts().reset_index()
        quality_dist.columns = ['质量等级', '媒介数量']

        # 计算占比
        total_media = quality_dist['媒介数量'].sum()
        quality_dist['占比'] = np.where(
            total_media > 0,
            (quality_dist['媒介数量'] / total_media * 100).round(2),
            0.0
        )
        quality_dist['占比(%)'] = quality_dist['占比'].astype(str) + "%"

        # 按等级排序
        order = {'优秀': 1, '良好': 2, '一般': 3, '待改进': 4, '较差': 5}
        quality_dist['排序'] = quality_dist['质量等级'].map(order)
        quality_dist = quality_dist.sort_values('排序')
        quality_dist = quality_dist.drop('排序', axis=1)

        quality_dist = quality_dist[['质量等级', '媒介数量', '占比(%)']]

        logger.info(f"质量分布计算完成，共 {len(quality_dist)} 个等级")
        return quality_dist