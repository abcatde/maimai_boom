'''
logCore.py主要负责日志记录任务
1.初始化日志文件log-日期.txt到指定目录
2.提供日志写入函数供调用
3.每隔一定时间清理过期日志文件，最多不超过五天
4.增加日志级别，默认级别为INFO，支持DEBUG、WARNING、ERROR级别

'''

import os
import datetime
from .timeCore import TaskScheduler
from enum import Enum

# 获取插件根目录的绝对路径
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(PLUGIN_DIR, 'data', 'logs')

class LogLevel(Enum):
    """日志级别枚举"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"

def init_log_file():
    """初始化日志文件"""
    os.makedirs(LOG_DIR, exist_ok=True)
    today_str = datetime.datetime.now().strftime('%Y-%m-%d')
    log_file_path = os.path.join(LOG_DIR, f'log-{today_str}.txt')
    if not os.path.exists(log_file_path):
        with open(log_file_path, 'w', encoding='utf-8') as f:
            f.write(f'Log file created on {today_str}\n')
    return log_file_path


def log_write(message, level=LogLevel.INFO):
    """写入日志信息
    
    Args:
        message: 日志内容
        level: 日志级别，默认为INFO级别，可选DEBUG、INFO、WARNING、ERROR
    """
    log_file_path = init_log_file()
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # 如果传入的是字符串，转换为LogLevel
    if isinstance(level, str):
        try:
            level = LogLevel[level.upper()]
        except KeyError:
            level = LogLevel.INFO
    
    # 如果不是LogLevel类型，默认为INFO
    if not isinstance(level, LogLevel):
        level = LogLevel.INFO
    
    with open(log_file_path, 'a', encoding='utf-8') as f:
        f.write(f'[{timestamp}] [{level.value}] {message}\n')


@TaskScheduler.interval_task(hours=1)  # 每小时执行一次
def clean_old_logs():
    """清理过期日志文件，保留最近5天的日志"""
    now = datetime.datetime.now()
    if not os.path.exists(LOG_DIR):
        return
    for filename in os.listdir(LOG_DIR):
        if filename.startswith('log-') and filename.endswith('.txt'):
            date_str = filename[4:-4]
            try:
                file_date = datetime.datetime.strptime(date_str, '%Y-%m-%d')
                if (now - file_date).days > 5:
                    os.remove(os.path.join(LOG_DIR, filename))
            except ValueError:
                continue