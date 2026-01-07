'''
user_data.py主要负责数据库任务

1.初始化用户数据user_data.json到内存
    -user_data.json存储用户的基本信息和金币数据、签到时间
    -复杂信息记录在专门的用户文件中
2.提供对用户数据的增删改查操作函数供调用
'''

import json
import os
from . import logCore
from .timeCore import TaskScheduler

# 获取插件根目录的绝对路径
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PLUGIN_DIR, 'data')
USER_DATA_FILE = os.path.join(DATA_DIR, 'user_data.json')

# 全局变量，存储用户数据
user_data = {}



'''
user结构体:
user_id: 用户ID
coins: 用户金币数量
last_sign_in: 上次签到时间
sign_day: 连续签到天数
data_url: 用户复杂数据文件路径
stock_list: 用户持有的股票列表
'''


class User:
    def __init__(self, user_id, user_name ,coins=0, last_sign_in=None, sign_day= int):
        self.user_id = user_id
        self.user_name = user_name
        self.coins = coins
        self.last_sign_in = last_sign_in
        self.sign_day = sign_day
        # 用户持有的股票列表，格式为{stock_id: 数量}
        self.stock_list = {}

        # 用户拥有的圣遗物洗词条道具数量
        self.artifact_re_roll_items = 0
        # 用户拥有的圣遗物升级道具数量
        self.artifact_upgrade_items = 0


def load_user_data(file_path=None):
    """加载用户数据到内存"""
    if file_path is None:
        file_path = USER_DATA_FILE
    
    # 确保data目录存在
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    #确保文件存在
    if not os.path.exists(file_path):
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump({}, f, ensure_ascii=False, indent=4)
            logCore.log_write(f'用户数据不存在，创建新的用户数据到 {file_path}')
    #加载用户数据到内存
    global user_data
    with open(file_path, 'r', encoding='utf-8') as f:
        user_data = json.load(f)
        logCore.log_write(f'用户数据从 {file_path} 加载到内存，当前用户数: {len(user_data)}')

@TaskScheduler.interval_task(minutes=30)  # 每30分钟执行一次
async def save_user_data(file_path=None):
    """保存内存中的用户数据到文件（异步版本，用于定时任务）"""
    _save_user_data_sync(file_path)

def _save_user_data_sync(file_path=None):
    """保存内存中的用户数据到文件（同步版本，用于立即保存）"""
    if file_path is None:
        file_path = USER_DATA_FILE
    
    global user_data
    
    # 如果user_data为空，说明数据还未加载，不执行保存
    # 注意：空字典 {} 是 falsy，但我们允许空用户列表，所以检查是否为 None
    if user_data is None:
        logCore.log_write(f'用户数据未初始化，跳过保存操作', logCore.LogLevel.WARNING)
        return
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(user_data, f, ensure_ascii=False, indent=4)
        logCore.log_write(f'用户数据保存到 {file_path}，当前用户数: {len(user_data)}')

def register_user(user_id, user_name):
    """注册新用户（不设置初始金币和签到数据，由首次签到完成）"""
    global user_data
    if str(user_id) not in user_data:
        user_data[str(user_id)] = {
            'user_name': user_name,
            'coins': 0,
            'last_sign_in': None,
            'sign_day': 0,
        }
        logCore.log_write(f'新用户注册: {user_name} (ID: {user_id})，等待首次签到')
        return True
    else:
        logCore.log_write(f'用户已存在: {user_name} (ID: {user_id})')
        return False

def update_user_coins(user_id, amount):
    """更新用户金币数量"""
    global user_data
    user_info = user_data.get(str(user_id))
    if user_info:
        user_info['coins'] += amount
        logCore.log_write(f'用户ID {user_id} 金币更新: {amount}, 新余额: {user_info["coins"]}')
        return True, user_info['coins']
    return False

def update_user_sign_day(user_id, sign_day):
    """更新用户连续签到天数"""
    global user_data
    user_info = user_data.get(str(user_id))
    if user_info:
        user_info['sign_day'] = sign_day
        logCore.log_write(f'用户ID {user_id} 连续签到天数更新: {sign_day}')
        return True
    return False

def update_user_last_sign_in(user_id, last_sign_in):
    """更新用户最后签到时间"""
    global user_data
    user_info = user_data.get(str(user_id))
    if user_info:
        user_info['last_sign_in'] = last_sign_in
        logCore.log_write(f'用户ID {user_id} 最后签到时间更新: {last_sign_in}')
        return True
    return False

def get_user_name_by_id(user_id):
    """通过用户ID获取用户名"""
    global user_data
    user_info = user_data.get(str(user_id))
    if user_info:
        return user_info.get('user_name')
    return None

def get_user_by_id(user_id):
    """通过用户ID获取用户数据"""
    global user_data
    logCore.log_write(f'get_user_by_id: 查询 user_id={user_id}, type={type(user_id)}', logCore.LogLevel.DEBUG)
    logCore.log_write(f'get_user_by_id: user_data keys={list(user_data.keys())}', logCore.LogLevel.DEBUG)
    user_info = user_data.get(str(user_id))
    if user_info:
        return User(
            user_id=user_id,
            user_name=user_info.get('user_name'),
            coins=user_info.get('coins', 0),
            last_sign_in=user_info.get('last_sign_in'),
            sign_day=user_info.get('sign_day', 0)
        )
    return None

def get_user_stock_list(user_id):
    """获取用户持有的股票列表"""
    global user_data
    logCore.log_write(f'get_user_stock_list: 查询 user_id={user_id}', logCore.LogLevel.DEBUG)
    logCore.log_write(f'get_user_stock_list: user_data中的所有key: {list(user_data.keys())}', logCore.LogLevel.DEBUG)
    user_info = user_data.get(str(user_id))
    if user_info:
        stock_list = user_info.get('stock_list', {})
        # 将字典格式转换为列表格式，方便显示
        if isinstance(stock_list, dict):
            result = []
            for stock_id, stock_data in stock_list.items():
                result.append({
                    'stock_id': stock_id,
                    'stock_name': stock_data.get('stock_name', ''),
                    'stock_type': stock_data.get('stock_type', '官方'),
                    'quantity': stock_data.get('quantity', 0)
                })
            return result
        return []
    return []

def get_user_stock(user_id, stock_id):
    """获取用户持有的指定股票信息"""
    global user_data
    user_info = user_data.get(str(user_id))
    if user_info:
        stock_list = user_info.get('stock_list', {})
        return stock_list.get(str(stock_id))
    return None

def add_user_stock(user_id, stock_id, stock_name, quantity, stock_type='官方'):
    """增加用户持有的股票数量"""
    global user_data
    user_info = user_data.get(str(user_id))
    if user_info:
        if 'stock_list' not in user_info:
            user_info['stock_list'] = {}
        
        stock_id_str = str(stock_id)
        if stock_id_str in user_info['stock_list']:
            # 如果已经持有该股票，增加数量
            user_info['stock_list'][stock_id_str]['quantity'] += quantity
        else:
            # 如果没有持有该股票，新增记录
            user_info['stock_list'][stock_id_str] = {
                'stock_name': stock_name,
                'stock_type': stock_type,
                'quantity': quantity
            }
        logCore.log_write(f'用户ID {user_id} 增加股票 {stock_id}{stock_name} {quantity}股')
        return True
    return False

def remove_user_stock(user_id, stock_id, quantity):
    """减少用户持有的股票数量"""
    global user_data
    user_info = user_data.get(str(user_id))
    if user_info:
        if 'stock_list' not in user_info:
            user_info['stock_list'] = {}
            return False
        
        stock_id_str = str(stock_id)
        if stock_id_str not in user_info['stock_list']:
            return False
        
        current_quantity = user_info['stock_list'][stock_id_str].get('quantity', 0)
        if current_quantity < quantity:
            return False
        
        # 减少数量
        user_info['stock_list'][stock_id_str]['quantity'] -= quantity
        
        # 如果数量为0，删除该股票记录
        if user_info['stock_list'][stock_id_str]['quantity'] <= 0:
            del user_info['stock_list'][stock_id_str]
        
        logCore.log_write(f'用户ID {user_id} 减少股票 {stock_id} {quantity}股')
        return True
    return False

def add_artifact_re_roll_items(user_id, amount):
    """更新用户洗词条道具数量"""
    global user_data
    user_info = user_data.get(str(user_id))
    if user_info:
        if 'artifact_re_roll_items' not in user_info:
            user_info['artifact_re_roll_items'] = 0
        user_info['artifact_re_roll_items'] += amount
        logCore.log_write(f'用户ID {user_id} 洗词条道具数量更新: {amount}, 新数量: {user_info["artifact_re_roll_items"]}')
        return True
    return False

def add_artifact_upgrade_items(user_id, amount):
    """更新用户升级道具数量"""
    global user_data
    user_info = user_data.get(str(user_id))
    if user_info:
        if 'artifact_upgrade_items' not in user_info:
            user_info['artifact_upgrade_items'] = 0
        user_info['artifact_upgrade_items'] += amount
        logCore.log_write(f'用户ID {user_id} 升级道具数量更新: {amount}, 新数量: {user_info["artifact_upgrade_items"]}')
        return True
    return False

def get_artifact_re_roll_items(user_id):
    """获取用户洗词条道具数量"""
    global user_data
    user_info = user_data.get(str(user_id))
    if user_info:
        return user_info.get('artifact_re_roll_items', 0)
    return 0

def get_artifact_upgrade_items(user_id):
    """获取用户升级道具数量"""
    global user_data
    user_info = user_data.get(str(user_id))
    if user_info:
        return user_info.get('artifact_upgrade_items', 0)
    return 0