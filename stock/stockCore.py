'''
tockCore模块负责管理股票的核心逻辑，包括股票的买卖、价格更新等功能。
1.处理股票买卖逻辑
2.处理股票价格更新逻辑



'''

from . import stock_data
from . import stockPriceControl
from ..core import user_data
from ..core import logCore


#获取所有股票信息
def get_all_stocks():
    """获取所有股票信息"""
    stocks = []
    for stock_id, stock_info in stock_data.stock_data.items():
        stock = stock_data.Stock(
            stock_id=stock_id,
            stock_name=stock_info['stock_name'],
            stock_price=int(stock_info['stock_price']),  # 强制转换为整数
            stock_type=stock_info['stock_type'],
            stock_owner=stock_info.get('stock_owner', '官方'),
            stock_base_price=stock_info.get('stock_base_price', int(stock_info['stock_price']))
        )
        stocks.append(stock)
    return stocks

#获取指定股票的历史价格记录
def get_stock_price_history(stock_id: str):
    """获取指定股票的历史价格记录"""
    return stock_data.get_stock_price_history(stock_id)
    
#购买股票
def buy_stock(user_id: str, stock_id: str, quantity: int) -> bool:
    """处理用户购买股票的逻辑"""
    logCore.log_write(f'buy_stock: 接收到 user_id={user_id}, stock_id={stock_id}, quantity={quantity}', logCore.LogLevel.DEBUG)
    logCore.log_write(f'buy_stock: user_data中的所有key: {list(user_data.user_data.keys())}', logCore.LogLevel.DEBUG)
    
    user = user_data.get_user_by_id(user_id)
    stock = stock_data.get_stock_by_id(stock_id)
    if not user:
        logCore.log_write(f'用户ID {user_id} 购买股票失败，用户不存在', logCore.LogLevel.ERROR)
        return False, "用户不存在"
    if not stock:
        logCore.log_write(f'stock ID {stock_id} 购买失败，股票不存在', logCore.LogLevel.ERROR)
        return False, "股票不存在"
    total_price = stock.stock_price * quantity
    if user.coins < total_price:
        logCore.log_write(f'购买股票失败，金币不足', logCore.LogLevel.INFO)
        return False, "金币不足"
    
    #根据交易费率计算总价
    transaction_fee = int(total_price * stock.transaction_fee_rate)
    total_price += transaction_fee
    #如果手续费小于1金币，至少收取1金币交易费，向上取整
    if transaction_fee < 1:
        transaction_fee = 1
        total_price += (1 - int(total_price * stock.transaction_fee_rate))
    #如果用户金币不足以支付总价，购买失败
    if user.coins < total_price:
        logCore.log_write(f'购买股票失败，金币不足支付交易费', logCore.LogLevel.INFO)
        return False, "剩余金币不足支付交易费"

    # 扣除用户金币
    user.coins -= total_price
    user_data.update_user_coins(user_id, -total_price)
    # 增加用户持有的股票数量
    user_data.add_user_stock(user_id, stock_id, stock.stock_name, quantity, stock.stock_type)
    
    # 调整股票权重（买入会增加正储备权重）
    stockPriceControl.adjust_stock_weight_on_trade(stock_id, quantity, is_buy=True)
    
    logCore.log_write(f'成功购买 {quantity} 股 {stock_id}{stock.stock_name} ，总价 {total_price} 金币')
    return True, f"@{user_data.get_user_name_by_id(user_id)}成功购买 {quantity}股[{stock_id}{stock.stock_name}]，手续费{transaction_fee},总价{total_price}金币\n当前金币余额{user.coins}个"

#卖出股票
def sell_stock(user_id: str, stock_id: str, quantity: int) -> bool:
    """处理用户卖出股票的逻辑"""
    user = user_data.get_user_by_id(user_id)
    stock = stock_data.get_stock_by_id(stock_id)
    if not user:
        logCore.log_write(f'用户ID {user_id} 卖出股票失败，用户不存在', logCore.LogLevel.ERROR)
        return False, "用户不存在"
    if not stock:
        logCore.log_write(f'stock ID {stock_id} 卖出失败，股票不存在', logCore.LogLevel.ERROR)
        return False, "股票不存在"
    
    user_stock = user_data.get_user_stock(user_id, stock_id)
    if not user_stock or user_stock['quantity'] < quantity:
        logCore.log_write(f'卖出股票失败，持有数量不足', logCore.LogLevel.INFO)
        return False, "持有数量不足"
    
    total_price = stock.stock_price * quantity
    #根据交易费率计算总价
    transaction_fee = int(total_price * stock.transaction_fee_rate)
    total_price -= transaction_fee
    #如果手续费小于1金币，至少收取1金币交易费，向上取整
    if transaction_fee < 1:
        transaction_fee = 1
        total_price -= (1 - int(total_price * stock.transaction_fee_rate))
    if total_price < 0:
        total_price = 0

    # 增加用户金币
    user.coins += total_price
    user_data.update_user_coins(user_id, total_price)
    # 减少用户持有的股票数量
    user_data.remove_user_stock(user_id, stock_id, quantity)    
    # 调整股票权重（卖出会增加负储备权重）
    stockPriceControl.adjust_stock_weight_on_trade(stock_id, quantity, is_buy=False)
    logCore.log_write(f'成功卖出 {quantity}股{stock_id}{stock.stock_name} ，总价 {total_price} 金币')
    return True, f"@{user_data.get_user_name_by_id(user_id)}成功卖出{quantity}股[{stock_id}{stock.stock_name}]，手续费{transaction_fee}，总价 {total_price} 金币\n当前金币余额{user.coins}个"

