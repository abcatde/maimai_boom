'''
stockCommands.py主要负责股票命令的处理
在commdands后缀的文件中，只需要处理信息的输入，初步处理后交由core中的模块处理具体逻辑

'''

from typing import Optional, Tuple
from ..core import logCore
from src.plugin_system.apis import person_api
from src.plugin_system.base.base_command import BaseCommand
from . import stockCore
from . import stockPriceControl

# .市场 命令查看市场信息，显示所有股票的当前价格和涨跌情况
class MarketCommand(BaseCommand):
    command_name = "Market"
    command_description = "查看股票市场信息"
    command_pattern = r"^.市场$"
    
    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """处理查看市场信息命令"""
        # 获取所有股票信息
        stock_list = stockCore.get_all_stocks()
        if not stock_list:
            await self.send_text("当前没有股票信息。")
            return False, "无股票信息", False
        
        # 构建市场信息文本
        market_info = "股票市场信息:\n"
        for stock in stock_list:
            market_info += f"[{stock.stock_type}]  {stock.stock_id}{stock.stock_name}   {int(stock.stock_price)}$\n"
        
        # 获取下次更新时间
        next_update = stockPriceControl.get_next_update_time()
        if next_update:
            market_info += f"\n下次股票更新时间: {next_update}"
        else:
            market_info += "\n下次股票更新时间: 未知"
        
        await self.send_text(market_info)
        return True, "市场信息发送成功", True
    

# .历史价格 <股票ID> 命令查看指定股票的历史价格记录，
class StockPriceHistoryCommand(BaseCommand):
    command_name = "Stock_Price_History"
    command_description = "查看股票历史价格"
    command_pattern = r"^.历史价格 (?P<stock_id>\w+)$"
    
    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """处理查看股票历史价格命令"""
        stock_id = self.matched_groups.get('stock_id')
        if not stock_id:
            await self.send_text("命令格式错误，请使用 .历史价格 <股票ID>")
            return False, "命令格式错误", False
        # 获取股票历史价格
        price_history = stockCore.get_stock_price_history(stock_id)
        if not price_history:
            await self.send_text(f"未找到股票ID {stock_id} 的历史价格记录。")
            return False, "无历史价格记录", False
        # 构建历史价格信息文本
        history_info = f"{stock_id}的历史价格记录:\n"
        for record in price_history:
            history_info += f"{record}"
        
        await self.send_text(history_info)
        return True, "历史价格信息发送成功", True
    
# .购买股票 <股票id> <数量> 命令
class BuyStockCommand(BaseCommand):
    command_name = "Buy_Stock"
    command_description = "购买股票"
    command_pattern = r"^.购买股票 (?P<stock_id>\w+) (?P<quantity>\d+)$"
    
    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """处理购买股票命令"""
        # 获取平台和用户ID
        platform = self.message.message_info.platform
        user_id = str(self.message.message_info.user_info.user_id)
        
        # 获取 person_id
        person_id = person_api.get_person_id(platform, user_id)
        
        stock_id = self.matched_groups.get('stock_id')
        quantity_str = self.matched_groups.get('quantity')
        if not stock_id or not quantity_str:
            return False, "命令格式错误", False
        quantity = int(quantity_str)
        if quantity <= 0:
            return False, "购买数量错误", False
        
        # 处理购买逻辑（调用stockCore中的函数）
        success, message = stockCore.buy_stock(person_id, stock_id, quantity)
        await self.send_text(message)
        return success, message, success

# .卖出股票 <股票id> <数量> 命令
class SellStockCommand(BaseCommand):
    command_name = "Sell_Stock"
    command_description = "卖出股票"
    command_pattern = r"^.卖出股票 (?P<stock_id>\w+) (?P<quantity>\d+)$"
    
    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """处理卖出股票命令""" 
        # 获取平台和用户ID
        platform = self.message.message_info.platform
        user_id = str(self.message.message_info.user_info.user_id)
        
        # 获取 person_id
        person_id = person_api.get_person_id(platform, user_id)
        
        stock_id = self.matched_groups.get('stock_id')
        quantity_str = self.matched_groups.get('quantity')
        if not stock_id or not quantity_str:
            return False, "命令格式错误", False
        quantity = int(quantity_str)
        if quantity <= 0:
            return False, "卖出数量错误", False
        
        # 处理卖出逻辑（调用stockCore中的函数）
        success, message = stockCore.sell_stock(person_id, stock_id, quantity)
        await self.send_text(message)
        return success, message, success