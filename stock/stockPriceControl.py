'''
股票价格更新控制模块
1.每6分钟更新一次股票市场价格
2.股票有 负权重 和 正权重，股票波动范围为 ±(基础价格 * 权重百分比)
3.股票价格低于标准价格时，线性增加正权重 (标准价格 - 当前价格 * 0.01)
4.储备权重用于平滑价格波动，每次买卖会增加储备权重，储备权重会逐渐释放到正负权重中
5.价格波动最大转移值用于限制每次储备权重释放的幅度，防止价格剧烈波动
'''

import random
from datetime import datetime
from typing import Optional
from ..core import logCore
from ..core import timeCore
from . import stock_data


@timeCore.TaskScheduler.interval_task(minutes=6)
def update_stock_prices():
    """每6分钟更新一次股票市场价格"""
    if not stock_data.stock_data:
        logCore.log_write('股票数据为空，跳过价格更新', logCore.LogLevel.WARNING)
        return
    
    logCore.log_write('开始更新股票市场价格...', logCore.LogLevel.INFO)
    updated_count = 0
    
    for stock_id, stock_info in stock_data.stock_data.items():
        try:
            # 构造 Stock 对象
            stock = stock_data.Stock(
                stock_id=stock_info['stock_id'],
                stock_name=stock_info['stock_name'],
                stock_price=stock_info['stock_price'],
                stock_type=stock_info['stock_type'],
                stock_owner=stock_info['stock_owner'],
                stock_base_price=stock_info['stock_base_price'],
                price_fluctuation_positive=stock_info.get('price_fluctuation_positive', 0.05),
                price_fluctuation_negative=stock_info.get('price_fluctuation_negative', 0.05),
                price_fluctuation_reserve=stock_info.get('price_fluctuation_reserve', 0.00),
                price_fluctuation_max=stock_info.get('price_fluctuation_max', 0.20),
                price_history=stock_info.get('price_history', [])
            )
            
            old_price = stock.stock_price
            
            # 更新股票价格
            new_price = calculate_new_price(stock)
            
            # 更新到内存
            stock_info['stock_price'] = new_price
            stock_info['price_fluctuation_positive'] = stock.price_fluctuation_positive
            stock_info['price_fluctuation_negative'] = stock.price_fluctuation_negative
            stock_info['price_fluctuation_reserve'] = stock.price_fluctuation_reserve
            
            # 记录价格历史
            from datetime import datetime
            timestamp = datetime.now().strftime('%m月%d日%H:%M')
            price_record = f"{timestamp} {int(new_price)}$"
            if 'price_history' not in stock_info:
                stock_info['price_history'] = []
            stock_info['price_history'].append(price_record)
            # 只保留最近10条记录
            if len(stock_info['price_history']) > 10:
                stock_info['price_history'] = stock_info['price_history'][-10:]
            
            updated_count += 1
            logCore.log_write(f'股票 {stock_id} {stock.stock_name}: {int(old_price)}$ → {int(new_price)}$')
            
        except Exception as e:
            logCore.log_write(f'更新股票 {stock_id} 价格失败: {str(e)}', logCore.LogLevel.ERROR)
    
    # 保存更新后的数据
    stock_data.save_stock_data()
    logCore.log_write(f'股票价格更新完成，共更新 {updated_count} 支股票')


def get_next_update_time() -> Optional[str]:
    """获取下次股票价格更新时间
    
    Returns:
        格式化的下次更新时间字符串（相对时间），如果无法获取则返回None
    """
    scheduler = timeCore.TaskScheduler._global_instance
    if scheduler is None:
        return None
    
    next_run = scheduler.get_task_next_run(update_stock_prices)
    if next_run is None:
        return None
    
    # 计算时间差
    now = datetime.now()
    time_diff = next_run - now
    
    # 转换为分钟和秒
    total_seconds = int(time_diff.total_seconds())
    if total_seconds < 0:
        return "即将更新"
    
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    
    return f"{minutes}分钟{seconds}秒后"


def calculate_new_price(stock: stock_data.Stock) -> int:
    """
    计算股票的新价格
    
    算法：
    1. 如果当前价格低于基准价格，线性增加正权重
    2. 从储备权重中释放一部分到正负权重（受最大转移值限制）
    3. 根据正负权重计算价格波动范围
    4. 在波动范围内随机选择新价格
    
    Returns:
        int: 新的股票价格（整数）
    """
    # 第一步：价格修正机制 - 价格低于基准时增加正权重
    if stock.stock_price < stock.stock_base_price:
        price_diff = stock.stock_base_price - stock.stock_price
        # 线性增加正权重，每低于1单位基准价格增加0.01正权重
        correction_weight = price_diff * 0.01
        stock.price_fluctuation_positive += correction_weight
        # 限制正权重最大值
        stock.price_fluctuation_positive = min(stock.price_fluctuation_positive, 0.30)
    
    # 第二步：储备权重释放机制
    if abs(stock.price_fluctuation_reserve) > 0.001:  # 储备权重大于0.001时才释放
        # 计算本次可以释放的最大值
        release_amount = min(abs(stock.price_fluctuation_reserve), stock.price_fluctuation_max)
        
        # 根据储备权重的正负决定释放方向
        if stock.price_fluctuation_reserve > 0:
            # 正储备权重释放到正权重
            stock.price_fluctuation_positive += release_amount
            stock.price_fluctuation_reserve -= release_amount
        else:
            # 负储备权重释放到负权重
            stock.price_fluctuation_negative += release_amount
            stock.price_fluctuation_reserve += release_amount
        
        # 限制权重在合理范围内
        stock.price_fluctuation_positive = min(stock.price_fluctuation_positive, 0.30)
        stock.price_fluctuation_negative = min(stock.price_fluctuation_negative, 0.30)
    
    # 第三步：计算价格波动范围
    # 正权重影响上涨幅度，负权重影响下跌幅度
    max_increase = stock.stock_base_price * stock.price_fluctuation_positive
    max_decrease = stock.stock_base_price * stock.price_fluctuation_negative
    
    # 第四步：随机选择价格变动
    # 使用正态分布，让价格变动更接近中间值（小幅波动更常见）
    # random.gauss(mu, sigma): mu=0表示中心点，sigma控制波动幅度
    change_factor = random.gauss(0, 0.3)  # 68%的概率在±0.3sigma内，即小幅波动
    change_factor = max(-1, min(1, change_factor))  # 限制在[-1, 1]范围内
    
    if change_factor > 0:
        # 价格上涨
        price_change = max_increase * change_factor
    else:
        # 价格下跌
        price_change = max_decrease * change_factor
    
    new_price = stock.stock_price + price_change
    
    # 确保价格不低于基准价格的10%（防止崩盘）
    min_price = int(stock.stock_base_price * 0.1)
    new_price = max(min_price, new_price)
    
    # 第五步：价格变动后，权重衰减
    # 每次价格更新后，正负权重都会略微衰减，防止无限累积
    stock.price_fluctuation_positive *= 0.95
    stock.price_fluctuation_negative *= 0.95
    
    # 保持最小权重，防止市场过于稳定
    stock.price_fluctuation_positive = max(stock.price_fluctuation_positive, 0.02)
    stock.price_fluctuation_negative = max(stock.price_fluctuation_negative, 0.02)
    
    # 返回整数价格（与金币系统保持一致）
    return int(round(new_price))


def adjust_stock_weight_on_trade(stock_id: str, quantity: int, is_buy: bool):
    """
    交易时调整股票权重
    
    Args:
        stock_id: 股票ID
        quantity: 交易数量
        is_buy: True表示买入，False表示卖出
    """
    stock_info = stock_data.stock_data.get(str(stock_id))
    if not stock_info:
        return
    
    # 根据交易量计算权重变化
    # 每交易1单位增加0.001的储备权重
    weight_change = quantity * 0.001
    
    if is_buy:
        # 买入增加正储备权重（未来倾向于上涨）
        current_reserve = stock_info.get('price_fluctuation_reserve', 0.0)
        stock_info['price_fluctuation_reserve'] = current_reserve + weight_change
    else:
        # 卖出增加负储备权重（未来倾向于下跌）
        current_reserve = stock_info.get('price_fluctuation_reserve', 0.0)
        stock_info['price_fluctuation_reserve'] = current_reserve - weight_change
    
    logCore.log_write(f'股票 {stock_id} 交易调整: {"买入" if is_buy else "卖出"} {quantity}股, 储备权重变化: {weight_change if is_buy else -weight_change:.4f}')
