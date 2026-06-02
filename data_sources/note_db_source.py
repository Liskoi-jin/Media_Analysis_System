"""
笔记分析数据库数据源
"""
import pandas as pd
import pymysql
from config import DB_CONFIG
from analyzers.utils import logger


class NoteDBSource:
    """笔记分析数据库数据源"""

    def __init__(self):
        self.config = DB_CONFIG
        logger.info("笔记数据库数据源初始化完成")

    def create_connection(self):
        """创建数据库连接"""
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
            return conn
        except Exception as e:
            logger.error(f"数据库连接失败: {e}")
            return None

    def query_note_data(self, start_date: str, end_date: str) -> pd.DataFrame:
        """查询笔记数据"""
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
            system_status,
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
            cpm,
            cpe,
            note_publish_time,
            schedule_time,
            cooperation_project_count,
            influencer_rating,
            pgy_url,
            home_url,
            note_url
        FROM
            lgc_project_influencer
        WHERE
            note_publish_time >= %s
            AND note_publish_time < %s
            AND influencer_source = 'INSIDE'
            AND (state = "CHAIN_RETURNED" OR state = "SCHEDULED")
            AND project_name NOT IN ('快消组达人库', '家居组达人', '数码组达人库', '测试-250801')
        """

        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, [f"{start_date} 00:00:00", f"{end_date} 23:59:59"])
                results = cursor.fetchall()

                if not results:
                    logger.info(f"笔记数据查询返回空结果: {start_date} 到 {end_date}")
                    return pd.DataFrame()

                df = pd.DataFrame(results)

                # 转换数值字段
                numeric_fields = [
                    'cost_amount', 'cooperation_quote', 'order_amount', 'rebate_amount',
                    'interaction_count', 'read_count', 'exposure_count', 'follower_count',
                    'cpm', 'cpe', 'note_like_count', 'note_favorite_count', 'note_comment_count'
                ]
                for field in numeric_fields:
                    if field in df.columns:
                        df[field] = pd.to_numeric(df[field], errors='coerce').fillna(0)

                # 处理链接字段的空值
                link_fields = ['pgy_url', 'home_url', 'note_url']
                for field in link_fields:
                    if field in df.columns:
                        df[field] = df[field].fillna('').astype(str)
                        df[field] = df[field].apply(lambda x: '' if x in ['nan', 'None', 'null', ''] else x)

                # 转换时间字段
                if 'note_publish_time' in df.columns:
                    df['note_publish_time'] = pd.to_datetime(df['note_publish_time'], errors='coerce')

                logger.info(f"笔记数据查询完成，共 {len(df)} 条")
                logger.info(f"链接字段统计: pgy_url非空={df['pgy_url'].astype(bool).sum()}, home_url非空={df['home_url'].astype(bool).sum()}, note_url非空={df['note_url'].astype(bool).sum()}")

                return df

        except Exception as e:
            logger.error(f"笔记数据查询失败: {e}", exc_info=True)
            return pd.DataFrame()
        finally:
            conn.close()