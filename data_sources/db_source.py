"""
数据库数据源 - 封装数据库查询功能
"""
import pandas as pd
import pymysql
import decimal
from typing import Optional, Dict, Any
from config import DB_CONFIG
from analyzers.utils import logger


def convert_decimal_to_float(value):
    """将Decimal类型转换为float"""
    if isinstance(value, (decimal.Decimal,)):
        return float(value)
    elif pd.isna(value):
        return 0.0
    else:
        return value


def clean_and_prepare_data(df):
    """基础数据清理（仅处理空值和类型转换）"""
    if df.empty:
        return df

    df = df.copy()

    # 处理空值
    str_fields = ['schedule_user_name', 'submit_media_user_name',
                  'influencer_nickname', 'project_name', 'state',
                  'kol_koc_type', 'note_type', 'influencer_purpose']

    for field in str_fields:
        if field in df.columns:
            df[field] = df[field].fillna('')
            df[field] = df[field].astype(str).str.strip()

    # 处理数值字段
    numeric_fields = ['follower_count', 'cooperation_quote', 'order_amount',
                      'rebate_amount', 'cost_amount', 'note_like_count',
                      'note_favorite_count', 'note_comment_count', 'interaction_count',
                      'read_count', 'exposure_count', 'read_uv_count']

    for field in numeric_fields:
        if field in df.columns:
            df[field] = pd.to_numeric(df[field], errors='coerce')
            df[field] = df[field].fillna(0)

    # 时间字段处理（保留原始字符串格式）
    logger.info("时间字段处理完成（保留原始字符串格式）")

    return df


class DBSource:
    """数据库数据源 - 处理数据库查询"""

    def __init__(self, config: Dict = None):
        self.config = config or DB_CONFIG
        logger.info(f"数据库数据源初始化，主机: {self.config.get('host')}")

    def create_connection(self) -> Optional[pymysql.connections.Connection]:
        try:
            conn = pymysql.connect(
                host=self.config['host'],
                port=self.config['port'],
                user=self.config['user'],
                password=self.config['password'],
                database=self.config['database'],
                charset=self.config.get('charset', 'utf8mb4'),
                cursorclass=pymysql.cursors.DictCursor
            )
            logger.info("数据库连接成功")
            return conn
        except Exception as e:
            logger.error(f"数据库连接失败: {str(e)}")
            return None

    def query_workload_data(self, start_date: str, end_date: str) -> pd.DataFrame:
        """
        查询工作量分析数据 - 定档数据
        正确SQL：基于 schedule_time，且 state 为 CHAIN_RETURNED 或 SCHEDULED
        """
        conn = self.create_connection()
        if not conn:
            return pd.DataFrame()

        sql = """
        SELECT
            id,
            influencer_nickname,
            project_name,
            schedule_user_name,
            submit_media_user_name,
            submit_media_user_id,
            state,
            kol_koc_type,
            note_type,
            follower_count,
            cooperation_quote,
            order_amount,
            rebate_amount,
            cost_amount,
            influencer_source,
            influencer_purpose,
            note_like_count,
            note_favorite_count,
            note_comment_count,
            interaction_count,
            read_count,
            exposure_count,
            read_uv_count,
            system_status,
            schedule_time,
            submit_time
        FROM
            lgc_project_influencer
        WHERE
            schedule_time >= %s
            AND schedule_time < %s
            AND influencer_source = 'INSIDE'
            AND (state = "CHAIN_RETURNED" OR state = "SCHEDULED")
            AND project_name NOT IN ('快消组达人库', '家居组达人', '数码组达人库', '测试-250801')
        """
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(sql, [f"{start_date} 00:00:00", f"{end_date} 23:59:59"])
                results = cursor.fetchall()

                if not results:
                    logger.info(f"工作量数据查询返回空结果: {start_date} 到 {end_date}")
                    return pd.DataFrame()

                df = pd.DataFrame(results)
                logger.info(f"工作量数据原始查询结果: {len(df)} 条")

                # 转换Decimal类型
                decimal_fields = ['cost_amount', 'cooperation_quote', 'order_amount', 'rebate_amount',
                                  'note_like_count', 'note_favorite_count', 'note_comment_count',
                                  'interaction_count', 'read_count', 'exposure_count', 'read_uv_count',
                                  'follower_count']
                for field in decimal_fields:
                    if field in df.columns:
                        df[field] = df[field].apply(convert_decimal_to_float)

                # 基础清理
                df = clean_and_prepare_data(df)

                # 添加数据类型标记
                df['数据类型'] = '定档'

                logger.info(f"工作量数据最终处理完成: {len(df)} 条")
                return df

        except Exception as e:
            logger.error(f"工作量数据查询失败: {str(e)}", exc_info=True)
            return pd.DataFrame()
        finally:
            conn.close()

    def query_quality_data(self, start_date: str, end_date: str) -> pd.DataFrame:
        """
        查询工作质量分析数据 - 提报数据
        正确SQL：基于 submit_time，且 influencer_purpose 为 '高阅读达人' 或 '优质达人'
        """
        conn = self.create_connection()
        if not conn:
            return pd.DataFrame()

        sql = """
        SELECT
            id,
            influencer_nickname,
            project_name,
            schedule_user_name,
            submit_media_user_name,
            submit_media_user_id,
            state,
            kol_koc_type,
            note_type,
            follower_count,
            cooperation_quote,
            order_amount,
            rebate_amount,
            cost_amount,
            influencer_source,
            influencer_purpose,
            note_like_count,
            note_favorite_count,
            note_comment_count,
            interaction_count,
            read_count,
            exposure_count,
            read_uv_count,
            system_status,
            submit_time
        FROM
            lgc_project_influencer
        WHERE
            submit_time >= %s
            AND submit_time < %s
            AND (influencer_purpose = '高阅读达人' OR influencer_purpose = '优质达人')
            AND influencer_source = 'INSIDE'
            AND project_name NOT IN ('快消组达人库', '家居组达人', '数码组达人库', '测试-250801')
        """
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(sql, [f"{start_date} 00:00:00", f"{end_date} 23:59:59"])
                results = cursor.fetchall()

                if not results:
                    logger.info(f"质量数据查询返回空结果: {start_date} 到 {end_date}")
                    return pd.DataFrame()

                df = pd.DataFrame(results)
                logger.info(f"质量数据原始查询结果: {len(df)} 条")

                # 转换Decimal类型
                decimal_fields = ['cost_amount', 'cooperation_quote', 'order_amount', 'rebate_amount',
                                  'note_like_count', 'note_favorite_count', 'note_comment_count',
                                  'interaction_count', 'read_count', 'exposure_count', 'read_uv_count',
                                  'follower_count']
                for field in decimal_fields:
                    if field in df.columns:
                        df[field] = df[field].apply(convert_decimal_to_float)

                # 基础清理
                df = clean_and_prepare_data(df)

                # 添加数据类型标记
                df['数据类型'] = '提报'

                logger.info(f"质量数据最终处理完成: {len(df)} 条")
                return df

        except Exception as e:
            logger.error(f"工作质量数据查询失败: {str(e)}", exc_info=True)
            return pd.DataFrame()
        finally:
            conn.close()

    def query_cost_data(self, start_date: str, end_date: str) -> pd.DataFrame:
        """
        查询成本效益分析数据 - 包含所有数据（包括成本为0的数据）
        正确SQL：基于 schedule_time，且 state 为 CHAIN_RETURNED 或 SCHEDULED
        不限制成本字段，包含所有数据
        """
        conn = self.create_connection()
        if not conn:
            return pd.DataFrame()

        sql = """
        SELECT
            id,
            influencer_nickname,
            project_name,
            schedule_user_name,
            submit_media_user_name,
            submit_media_user_id,
            state,
            kol_koc_type,
            note_type,
            follower_count,
            cooperation_quote,
            order_amount,
            rebate_amount,
            cost_amount,
            influencer_source,
            influencer_purpose,
            note_like_count,
            note_favorite_count,
            note_comment_count,
            interaction_count,
            read_count,
            exposure_count,
            read_uv_count,
            system_status,
            schedule_time
        FROM
            lgc_project_influencer
        WHERE
            schedule_time >= %s
            AND schedule_time < %s
            AND (state = "CHAIN_RETURNED" OR state = "SCHEDULED")
            AND project_name NOT IN ('快消组达人库', '家居组达人', '数码组达人库', '测试-250801')
        """
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(sql, [f"{start_date} 00:00:00", f"{end_date} 23:59:59"])
                results = cursor.fetchall()

                if not results:
                    logger.info(f"成本数据查询返回空结果: {start_date} 到 {end_date}")
                    return pd.DataFrame()

                df = pd.DataFrame(results)
                logger.info(f"成本数据原始查询结果: {len(df)} 条")

                # 转换Decimal类型
                decimal_fields = ['cost_amount', 'cooperation_quote', 'order_amount', 'rebate_amount',
                                  'note_like_count', 'note_favorite_count', 'note_comment_count',
                                  'interaction_count', 'read_count', 'exposure_count', 'read_uv_count',
                                  'follower_count']
                for field in decimal_fields:
                    if field in df.columns:
                        df[field] = df[field].apply(convert_decimal_to_float)

                # 基础清理
                df = clean_and_prepare_data(df)

                # 统计成本字段情况
                cost_not_null = df['cost_amount'].notna().sum()
                cost_gt_zero = (df['cost_amount'] > 0).sum()
                cost_eq_zero = (df['cost_amount'] == 0).sum()
                logger.info(f"成本数据统计: 总条数 {len(df)}, 成本非空 {cost_not_null}, 成本>0 {cost_gt_zero}, 成本=0 {cost_eq_zero}")

                # 添加数据类型标记
                df['数据类型'] = '定档'

                return df

        except Exception as e:
            logger.error(f"成本效益数据查询失败: {str(e)}", exc_info=True)
            return pd.DataFrame()
        finally:
            conn.close()