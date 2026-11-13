#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
统一日志系统模块
提供全局日志配置、文件持久化、日志轮转等能力
"""

import logging
import logging.handlers
import os
import sys
from typing import Optional

from utils.app_paths import app_root


class LoggerManager:
    """日志管理器单例"""
    
    _instance: Optional["LoggerManager"] = None
    _logger: Optional[logging.Logger] = None
    
    def __new__(cls) -> "LoggerManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._setup_logging()
        return cls._instance
    
    def _setup_logging(self, level=logging.INFO):
        """配置日志系统（仅初始化一次）"""
        log_dir = os.path.join(app_root(), "logs")
        os.makedirs(log_dir, exist_ok=True)
        
        # 创建主 logger
        self._logger = logging.getLogger("netops")
        self._logger.setLevel(logging.DEBUG)  # 捕获所有级别
        
        # 清除已有的处理器（避免重复）
        self._logger.handlers.clear()
        
        # -------- 控制台处理器（用户可见）--------
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(level)
        console_formatter = logging.Formatter(
            "[%(asctime)s] %(name)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S"
        )
        console_handler.setFormatter(console_formatter)
        self._logger.addHandler(console_handler)
        
        # -------- 文件处理器（诊断用）--------
        log_file = os.path.join(log_dir, "netops.log")
        try:
            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=5,  # 保留 5 个备份
                encoding="utf-8"
            )
            file_handler.setLevel(logging.DEBUG)
            file_formatter = logging.Formatter(
                "[%(asctime)s] %(name)s [%(levelname)s] %(filename)s:%(lineno)d %(funcName)s() %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            file_handler.setFormatter(file_formatter)
            self._logger.addHandler(file_handler)
        except Exception as e:
            # 日志文件初始化失败不应该影响程序运行
            print(f"Warning: Failed to setup file logging: {e}", file=sys.stderr)
    
    @property
    def logger(self) -> logging.Logger:
        """获取主 logger"""
        if self._logger is None:
            self._setup_logging()
        return self._logger


def get_logger(name: str) -> logging.Logger:
    """获取指定名称的子 logger
    
    Args:
        name: logger 名称（通常为 __name__ 或模块名）
    
    Returns:
        logging.Logger 实例
    
    Examples:
        logger = get_logger(__name__)
        logger.info("Device connected: %s", ip)
    """
    manager = LoggerManager()
    return logging.getLogger(f"netops.{name}")


def setup_logging(level=logging.INFO):
    """初始化日志系统（应在程序启动时调用一次）
    
    Args:
        level: 日志级别 (DEBUG/INFO/WARNING/ERROR)
    """
    manager = LoggerManager()
    manager._setup_logging(level)
