"""
笔记分析文件数据源
"""
import os
import pandas as pd
from analyzers.utils import logger, read_file_with_auto_encoding


class NoteFileSource:
    """笔记分析文件数据源"""

    def __init__(self, upload_folder: str = 'uploads'):
        self.upload_folder = upload_folder
        os.makedirs(upload_folder, exist_ok=True)
        logger.info(f"笔记文件数据源初始化，上传目录: {upload_folder}")

    def read_file(self, file_path: str) -> pd.DataFrame:
        """读取文件"""
        df = read_file_with_auto_encoding(file_path)
        if df is not None and not df.empty:
            logger.info(f"读取文件: {os.path.basename(file_path)}, 行数: {len(df)}")
        return df if df is not None else pd.DataFrame()

    def save_uploaded_file(self, file, filename: str) -> str:
        """保存上传文件"""
        save_path = os.path.join(self.upload_folder, filename)
        file.save(save_path)
        logger.info(f"文件保存成功: {filename}")
        return save_path