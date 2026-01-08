'''
userCore.py主要负责提供用户操作的功能接口
1.提供用户注册功能
2.提供用户信息查询功能
3.提供用户金币增减功能
'''

from . import user_data
from . import logCore
from datetime import datetime

def is_user_registered(user_id: str) -> bool:
    """检查用户是否注册"""
    return str(user_id) in user_data.user_data

def register_user(user_id: str, user_name: str) -> None:
    """注册新用户"""
    user_data.register_user(user_id, user_name)

def get_user_info(user_id: str) -> user_data.User:
    """获取用户信息"""
    return user_data.get_user_by_id(user_id)

def get_user_stock_list(user_id: str) -> dict:
    """获取用户持有的股票列表"""
    return user_data.get_user_stock_list(user_id)

def is_user_signed_in_today(user_id: str) -> bool:
    """检查用户今天是否已经签到"""
    user = get_user_info(user_id)
    if not user or not user.last_sign_in:
        return False
    now = datetime.now()
    last_sign_date = datetime.fromisoformat(user.last_sign_in)
    return last_sign_date.date() == now.date()

def update_coins_to_user(user_id: str, amount: int) -> None:
    """更新用户金币"""
    user_data.update_user_coins(user_id, amount)

#签到，增加连续签到天数个金币+10-100随机金币，如果是连续签到增加连续签到天数，否则重置连续签到天数
def sign_in_user(user_id: str, reward_coins: int) -> tuple:
    """用户签到
    
    Returns:
        tuple: (是否成功, 是否首次签到, 连续签到天数, 总奖励金币, 当前金币余额)
    """
    
    user = get_user_info(user_id)
    if not user:
        logCore.log_write(f'用户ID {user_id} 签到失败，用户不存在', logCore.LogLevel.ERROR)
        return False, False, 0, 0, 0
    
    now = datetime.now()
    is_first_sign = (user.last_sign_in is None)
    
    # 计算新的连续签到天数
    new_sign_day = 1
    if user.last_sign_in:
        last_sign_date = datetime.fromisoformat(user.last_sign_in)
        if (now.date() - last_sign_date.date()).days == 1:
            new_sign_day = user.sign_day + 1
    
    # 计算总奖励金币
    # 首次签到：1000（新人礼包） + 随机金币 + 1（连续签到天数）
    # 正常签到：随机金币 + 连续签到天数
    first_sign_bonus = 1000 if is_first_sign else 0
    total_reward = first_sign_bonus + reward_coins + new_sign_day
    
    # 更新用户数据
    user_data.update_user_coins(user_id, total_reward)
    user_data.update_user_sign_day(user_id, new_sign_day)
    user_data.update_user_last_sign_in(user_id, now.isoformat())
    
    # 获取更新后的金币余额
    updated_user = get_user_info(user_id)
    final_coins = updated_user.coins if updated_user else 0
    
    log_msg = f'用户 {user.user_name} 签到成功！'
    if is_first_sign:
        log_msg += f'首次签到获得新人礼包1000金币 + 随机{reward_coins}金币 + 签到{new_sign_day}金币'
    else:
        log_msg += f'连续签到{new_sign_day}天，获得{new_sign_day}+{reward_coins}金币'
    log_msg += f'，当前余额: {final_coins}'
    logCore.log_write(log_msg)
    
    return True, is_first_sign, new_sign_day, total_reward, final_coins

#保存用户数据
def save_user_data():
    """保存用户数据到文件"""
    user_data.save_user_data()
