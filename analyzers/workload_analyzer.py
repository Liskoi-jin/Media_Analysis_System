# analyzers/workload_analyzer.py
"""
工作量分析器 - 完全对齐Media_Analysis.py的工作量分析逻辑
输出表格字段：排名,媒介姓名,所属小组,定档量,已发布,未发布,综合评估
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Any
from analyzers.utils import (
    logger, normalize_media_name, get_media_group,
    ID_TO_NAME_MAPPING
)


class WorkloadAnalyzer:
    def __init__(self, df: pd.DataFrame, known_id_name_mapping: Dict = None, config: Dict = None):
        """
        初始化工作量分析器（Media_Analysis工作量分析逻辑）
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
            "top_media_ranking": None,  # TOP排名
        }

        logger.info("工作量分析器初始化完成（Media_Analysis逻辑）")

    def analyze(self, top_n: int = 10) -> Dict[str, Any]:
        """
        执行完整工作量分析（Media_Analysis逻辑）
        :param top_n: TOP媒介排名数量
        :return: 分析结果
        """
        logger.info("开始执行Media_Analysis工作量分析")
        try:
            # 1. 验证数据
            self._validate_data()

            # 2. 提取定档数据（工作量分析只处理定档数据）
            scheduling_df = self._extract_scheduling_data()

            if scheduling_df.empty:
                logger.warning("无定档数据可供工作量分析")
                self.result["summary"] = {"提示": "无有效定档数据进行工作量分析"}
                return self.result

            # 3. 处理媒介信息（Media_Analysis逻辑）
            media_info_df = self._process_media_info(scheduling_df)

            # 4. 计算媒介工作量明细（核心逻辑）
            media_workload_detail = self._calculate_media_workload(media_info_df)

            # 5. 计算汇总信息
            self.result["summary"] = self._calculate_workload_summary(media_workload_detail)

            # 6. 存储明细数据（格式化输出）- 只保留所需字段
            self.result["detail"] = self._format_workload_detail(media_workload_detail)

            # 7. 计算小组汇总
            self.result["group_summary"] = self._calculate_group_summary(media_workload_detail)

            # 8. 生成TOP排名 - 只保留所需字段
            self.result["top_media_ranking"] = self._generate_top_ranking(media_workload_detail, top_n)

            logger.info("工作量分析执行完成")
            return self.result

        except Exception as e:
            logger.error(f"工作量分析执行失败: {e}", exc_info=True)
            raise

    def _validate_data(self) -> None:
        """验证数据是否包含必要字段"""
        # 兼容字段名映射
        self._standardize_column_names()

        required_fields = ['定档媒介', '状态', '数据类型']
        missing_fields = [f for f in required_fields if f not in self.df.columns]

        if missing_fields:
            # 尝试使用替代字段
            field_alternatives = {
                '定档媒介': ['schedule_user_name', 'submit_media_user_name'],
                '状态': ['state', 'system_status', 'status'],
                '数据类型': []
            }

            for field in required_fields:
                if field not in self.df.columns:
                    for alt in field_alternatives.get(field, []):
                        if alt in self.df.columns:
                            self.df[field] = self.df[alt]
                            break

            # 重新检查缺失字段
            missing_fields = [f for f in required_fields if f not in self.df.columns]
            if missing_fields:
                raise ValueError(f"数据缺少必要字段: {missing_fields}")

        # 检查是否有定档数据
        if '数据类型' in self.df.columns:
            scheduling_count = (self.df['数据类型'] == '定档').sum()
            if scheduling_count == 0:
                logger.warning("数据中无'定档'类型数据")

    def _standardize_column_names(self):
        """标准化列名，确保后续逻辑能够正常运行"""
        # 状态字段映射
        if 'state' in self.df.columns and '状态' not in self.df.columns:
            self.df['状态'] = self.df['state']
            logger.info("已将'state'字段映射为'状态'")

        # 系统状态字段映射
        if 'system_status' in self.df.columns and '状态' not in self.df.columns:
            self.df['状态'] = self.df['system_status']
            logger.info("已将'system_status'字段映射为'状态'")

        # 定档媒介字段映射
        if 'schedule_user_name' in self.df.columns and '定档媒介' not in self.df.columns:
            self.df['定档媒介'] = self.df['schedule_user_name']
            logger.info("已将'schedule_user_name'字段映射为'定档媒介'")

        # 确保数据类型字段存在
        if '数据类型' not in self.df.columns:
            # 根据状态判断数据类型
            def determine_data_type(status):
                if pd.isna(status):
                    return '其他'
                status_str = str(status).upper()
                if 'CHAIN_RETURNED' in status_str or 'SCHEDULED' in status_str:
                    return '定档'
                else:
                    return '其他'

            status_col = self.df['状态'] if '状态' in self.df.columns else self.df.get('state', '')
            self.df['数据类型'] = status_col.apply(determine_data_type)
            logger.info(f"已根据状态字段创建'数据类型'字段，定档数据: {(self.df['数据类型'] == '定档').sum()}条")

    def _extract_scheduling_data(self) -> pd.DataFrame:
        """提取定档数据"""
        logger.info("提取定档数据")

        if '数据类型' in self.df.columns:
            scheduling_df = self.df[self.df['数据类型'] == '定档'].copy()
            logger.info(f"通过'数据类型'提取到 {len(scheduling_df)} 条定档数据")
        else:
            # 如果没有数据类型标记，根据状态判断
            def is_scheduling_status(status):
                if pd.isna(status):
                    return False
                status_str = str(status).upper()
                return ('CHAIN_RETURNED' in status_str or 'SCHEDULED' in status_str)

            status_col_names = ['状态', 'state', 'system_status', 'status']
            status_col = None

            for col in status_col_names:
                if col in self.df.columns:
                    status_col = self.df[col]
                    break

            if status_col is None:
                logger.error("未找到状态字段，无法提取定档数据")
                return pd.DataFrame()

            scheduling_mask = status_col.apply(is_scheduling_status)
            scheduling_df = self.df[scheduling_mask].copy()
            scheduling_df['数据类型'] = '定档'
            logger.info(f"通过状态判断提取到 {len(scheduling_df)} 条定档数据")

        return scheduling_df

    def _process_media_info(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        处理媒介信息
        """
        logger.info("处理媒介信息")
        df_processed = df.copy()

        # 确定媒介姓名
        df_processed['媒介姓名'] = '未知'

        has_schedule_name = 'schedule_user_name' in df_processed.columns
        has_submit_id = 'submit_media_user_id' in df_processed.columns

        if not has_schedule_name and not has_submit_id:
            if 'submit_media_user_name' in df_processed.columns:
                df_processed['媒介姓名'] = df_processed['submit_media_user_name'].apply(normalize_media_name)
            if 'schedule_user_name' in df_processed.columns:
                df_processed['媒介姓名'] = df_processed['schedule_user_name'].apply(normalize_media_name)
        else:
            for idx, row in df_processed.iterrows():
                real_name = '未知'

                if has_schedule_name:
                    schedule_name = str(row.get('schedule_user_name', '')).strip()
                    if schedule_name and schedule_name.lower() not in ['', 'nan', 'none', 'null', '未知']:
                        real_name = normalize_media_name(schedule_name)

                if real_name == '未知' and has_submit_id:
                    submit_id = str(row.get('submit_media_user_id', '')).strip()
                    if submit_id and submit_id.lower() not in ['', 'nan', 'none', 'null', '未知']:
                        submit_id = submit_id.replace('.0', '')
                        if submit_id in ID_TO_NAME_MAPPING:
                            real_name = ID_TO_NAME_MAPPING[submit_id]
                        elif submit_id in self.known_id_name_mapping:
                            real_name = self.known_id_name_mapping[submit_id]

                if real_name == '未知' and 'submit_media_user_name' in df_processed.columns:
                    submit_name = str(row.get('submit_media_user_name', '')).strip()
                    if submit_name and submit_name.lower() not in ['', 'nan', 'none', 'null', '未知']:
                        real_name = normalize_media_name(submit_name)

                if real_name != '未知':
                    df_processed.at[idx, '媒介姓名'] = real_name

        df_processed['媒介姓名'] = df_processed['媒介姓名'].replace(['', 'nan', 'NaN', 'None', 'null'], '未知')

        # 确定所属小组
        df_processed['所属小组'] = df_processed['媒介姓名'].apply(get_media_group)

        logger.info(f"媒介信息处理完成，唯一媒介数: {df_processed['媒介姓名'].nunique()}")
        logger.info(f"小组分布: {df_processed['所属小组'].value_counts().to_dict()}")
        return df_processed

    def _calculate_media_workload(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        计算媒介工作量（核心逻辑）
        输出字段：媒介姓名,所属小组,定档量,已发布,未发布,综合评估
        """
        logger.info("计算媒介工作量明细")

        if '状态' not in df.columns:
            logger.error("无状态字段可用，无法计算工作量")
            return pd.DataFrame(columns=['媒介姓名', '所属小组', '定档量', '已发布', '未发布', '综合评估'])

        # 标准化状态字段
        df['状态'] = df['状态'].fillna('UNKNOWN').astype(str)

        # 定义状态分类
        def classify_status(status):
            status_str = str(status).upper()
            if 'CHAIN_RETURNED' in status_str or '已发布' in status_str:
                return '已发布'
            elif 'SCHEDULED' in status_str or '未发布' in status_str:
                return '未发布'
            else:
                return '其他'

        df['状态分类'] = df['状态'].apply(classify_status)

        # 按媒介分组统计
        required_group_cols = ['媒介姓名', '所属小组']
        for col in required_group_cols:
            if col not in df.columns:
                df[col] = '未知'

        try:
            media_stats = df.groupby(required_group_cols).agg(
                已发布=('状态分类', lambda x: (x == '已发布').sum()),
                未发布=('状态分类', lambda x: (x == '未发布').sum()),
                其他状态数=('状态分类', lambda x: (x == '其他').sum())
            ).reset_index()

        except Exception as e:
            logger.error(f"分组统计失败: {e}")
            return pd.DataFrame(columns=['媒介姓名', '所属小组', '定档量', '已发布', '未发布', '综合评估'])

        # 计算定档量（已发布 + 未发布）
        media_stats['定档量'] = media_stats['已发布'] + media_stats['未发布']

        # 计算定档率（用于综合评估）
        media_stats['总处理量'] = media_stats['已发布'] + media_stats['未发布'] + media_stats['其他状态数']
        media_stats['定档率'] = np.where(
            media_stats['总处理量'] > 0,
            (media_stats['定档量'] / media_stats['总处理量'] * 100).round(2),
            0.0
        )

        # 综合评估（结合定档量和定档率）
        def evaluate_comprehensive(volume, rate):
            if volume >= 50 and rate >= 80:
                return "S级"
            elif volume >= 30 and rate >= 70:
                return "A级"
            elif volume >= 15 and rate >= 60:
                return "B级"
            elif volume >= 5 and rate >= 50:
                return "C级"
            else:
                return "D级"

        media_stats['综合评估'] = media_stats.apply(
            lambda row: evaluate_comprehensive(row['定档量'], row['定档率']), axis=1
        )

        # 按综合评估和定档量排序
        eval_order = {'S级': 1, 'A级': 2, 'B级': 3, 'C级': 4, 'D级': 5}
        media_stats['评估排序'] = media_stats['综合评估'].map(eval_order)
        media_stats = media_stats.sort_values(['评估排序', '定档量'], ascending=[True, False])
        media_stats = media_stats.drop(['评估排序', '总处理量', '定档率', '其他状态数'], axis=1)
        media_stats = media_stats.reset_index(drop=True)

        logger.info(f"媒介工作量计算完成，共 {len(media_stats)} 个媒介")
        return media_stats

    def _format_workload_detail(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        格式化工作量明细输出（只保留所需字段）
        """
        required_columns = [
            '媒介姓名', '所属小组', '定档量', '已发布', '未发布', '综合评估'
        ]

        # 确保所有列都存在
        for col in required_columns:
            if col not in df.columns:
                if col in ['定档量', '已发布', '未发布']:
                    df[col] = 0
                elif col == '综合评估':
                    df[col] = '未知'
                elif col == '媒介姓名':
                    df[col] = '未知'
                elif col == '所属小组':
                    df[col] = '其他组'

        # 按指定顺序排列
        df = df[required_columns].copy()

        return df

    def _calculate_workload_summary(self, detail_df: pd.DataFrame) -> Dict[str, Any]:
        """计算工作量分析汇总信息"""
        logger.info("计算工作量分析汇总信息")

        if detail_df.empty:
            return {"提示": "无工作量数据"}

        summary = {}

        # 基础统计
        summary['媒介总数'] = len(detail_df)
        summary['总定档量'] = int(detail_df['定档量'].sum())
        summary['总已发布'] = int(detail_df['已发布'].sum())
        summary['总未发布'] = int(detail_df['未发布'].sum())

        # 评级统计
        if '综合评估' in detail_df.columns:
            summary['S级媒介数'] = int((detail_df['综合评估'] == 'S级').sum())
            summary['A级媒介数'] = int((detail_df['综合评估'] == 'A级').sum())
            summary['B级媒介数'] = int((detail_df['综合评估'] == 'B级').sum())
            summary['C级媒介数'] = int((detail_df['综合评估'] == 'C级').sum())
            summary['D级媒介数'] = int((detail_df['综合评估'] == 'D级').sum())

        # 小组分布（按定档量总和）
        if '所属小组' in detail_df.columns and '定档量' in detail_df.columns:
            group_dist = detail_df.groupby('所属小组')['定档量'].sum().sort_values(ascending=False).head(5).to_dict()
            summary['主要小组分布'] = group_dist

        # 平均指标
        if summary['媒介总数'] > 0:
            summary['平均定档量'] = round(summary['总定档量'] / summary['媒介总数'], 1)

        logger.info(f"工作量汇总计算完成，总媒介数: {summary['媒介总数']}")
        return summary

    def _calculate_group_summary(self, detail_df: pd.DataFrame) -> pd.DataFrame:
        """计算小组工作量汇总"""
        logger.info("计算小组工作量汇总")

        if detail_df.empty or '所属小组' not in detail_df.columns:
            return pd.DataFrame()

        group_summary = detail_df.groupby('所属小组').agg(
            媒介数量=('媒介姓名', 'nunique'),
            总定档量=('定档量', 'sum'),
            总已发布=('已发布', 'sum'),
            总未发布=('未发布', 'sum')
        ).reset_index()

        # 计算占比
        total_scheduling = group_summary['总定档量'].sum()
        group_summary['定档量占比(%)'] = np.where(
            total_scheduling > 0,
            (group_summary['总定档量'] / total_scheduling * 100).round(2),
            0.0
        )
        group_summary['定档量占比(%)'] = group_summary['定档量占比(%)'].astype(str) + "%"

        # 排序 - 按指定的小组顺序排序
        group_order = {'耐消媒介组': 1, '家居媒介组': 2, '快消媒介组': 3}
        group_summary['小组排序'] = group_summary['所属小组'].apply(
            lambda x: group_order.get(x, 999)
        )
        group_summary = group_summary.sort_values('小组排序', ascending=True)
        group_summary = group_summary.drop('小组排序', axis=1)

        # 重新排列列顺序
        column_order = ['所属小组', '媒介数量', '总定档量', '定档量占比(%)', '总已发布', '总未发布']
        existing_columns = [col for col in column_order if col in group_summary.columns]
        group_summary = group_summary[existing_columns]

        logger.info(f"小组汇总计算完成，共 {len(group_summary)} 个小组")
        return group_summary

    def _generate_top_ranking(self, detail_df: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
        """生成TOP媒介排名"""
        logger.info(f"生成TOP{top_n}媒介排名")

        if detail_df.empty:
            return pd.DataFrame()

        ranking_df = detail_df.copy()

        # 按定档量降序排序
        top_media = ranking_df.sort_values('定档量', ascending=False).head(top_n).copy()

        # 添加排名列
        top_media['排名'] = range(1, len(top_media) + 1)

        # 重新排列列顺序 - 只保留所需字段
        column_order = ['排名', '媒介姓名', '所属小组', '定档量', '已发布', '未发布', '综合评估']

        existing_columns = [col for col in column_order if col in top_media.columns]
        top_media = top_media[existing_columns]

        logger.info(f"TOP{top_n}排名生成完成")
        return top_media.reset_index(drop=True)

    def get_workload_detail(self) -> pd.DataFrame:
        """获取工作量明细数据"""
        return self.result.get("detail", pd.DataFrame())

    def get_workload_summary(self) -> Dict[str, Any]:
        """获取工作量汇总信息"""
        return self.result.get("summary", {})

    def get_group_summary(self) -> pd.DataFrame:
        """获取小组汇总数据"""
        return self.result.get("group_summary", pd.DataFrame())

    def get_top_ranking(self) -> pd.DataFrame:
        """获取TOP媒介排名"""
        return self.result.get("top_media_ranking", pd.DataFrame())