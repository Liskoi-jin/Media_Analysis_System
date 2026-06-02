"""
文件数据源 - 封装文件读取功能
"""
import os
import pandas as pd
from typing import List, Optional, Dict, Any
from analyzers.utils import logger, read_file_with_auto_encoding


class FileSource:
    """文件数据源 - 处理文件上传和读取"""

    def __init__(self, upload_folder: str = 'uploads'):
        """
        初始化文件数据源
        :param upload_folder: 上传文件夹路径
        """
        self.upload_folder = upload_folder
        os.makedirs(upload_folder, exist_ok=True)
        logger.info(f"文件数据源初始化，上传目录: {upload_folder}")

    def read_files(self, file_paths: List[str]) -> pd.DataFrame:
        """
        读取多个文件并合并
        :param file_paths: 文件路径列表
        :return: 合并后的DataFrame
        """
        dataframes = []
        for file_path in file_paths:
            df = read_file_with_auto_encoding(file_path)
            if df is not None and not df.empty:
                dataframes.append(df)
                logger.info(f"读取文件: {os.path.basename(file_path)}, 行数: {len(df)}")

        if not dataframes:
            logger.warning("未读取到有效数据")
            return pd.DataFrame()

        merged_df = pd.concat(dataframes, ignore_index=True)
        logger.info(f"合并后数据总行数: {len(merged_df)}")
        return merged_df

    def save_uploaded_file(self, file, filename: str) -> str:
        """
        保存上传的文件
        :param file: 文件对象
        :param filename: 文件名
        :return: 保存路径
        """
        save_path = os.path.join(self.upload_folder, filename)
        file.save(save_path)
        logger.info(f"文件保存成功: {filename}")
        return save_path

    def get_file_info(self, file_path: str) -> Dict[str, Any]:
        """
        获取文件信息
        :param file_path: 文件路径
        :return: 文件信息字典
        """
        if not os.path.exists(file_path):
            return {}

        stat = os.stat(file_path)
        return {
            'filename': os.path.basename(file_path),
            'size': stat.st_size,
            'size_mb': round(stat.st_size / (1024 * 1024), 2),
            'modified_time': stat.st_mtime
        }