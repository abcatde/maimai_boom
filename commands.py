import datetime
import asyncio
import random
import math
import json
from typing import Optional, Tuple

from . import stock
from .data import BoomDataManager
from src.plugin_system.apis import person_api
from src.common.logger import get_logger
from src.plugin_system.base.base_command import BaseCommand

logger = get_logger("boom_plugin.commands")


class BoomCommand(BaseCommand):
    command_name = "boom"
    command_description = "产生一次爆炸"
    command_pattern = r"^.金币炸弹 (?P<gold>\w+)$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        gold_str = self.matched_groups.get("gold")
        if not gold_str.isdigit() or int(gold_str) <= 0:
            return False, "金币数量错误！", False
        if int(gold_str) < 5:
            await self.send_text("金币数量太少了炸不起来，不能小于5个！")
            return False, "金币数量不能少于5！", False
        try:
            platform = getattr(self.message.message_info, "platform", "")
            user_info = getattr(self.message.message_info, "user_info", None)
            if not user_info:
                return False, "无法获取用户信息！", False
            uid = person_api.get_person_id(platform, user_info.user_id)
        except Exception as e:
            logger.error(f"获取 person_id 失败: {e}")
            return False, "无法获取用户信息！", False

        if not BoomDataManager.read_id(uid):
            BoomDataManager.register_id(uid)
            await self.send_text(f"你是第一次使用金币炸弹，请使用签到进行注册。")
            return False, f"你是第一次使用金币炸弹，请使用签到进行注册。", False

        gold = int(gold_str)
        current_gold = BoomDataManager.get_gold(uid)
        if current_gold < gold:
            await self.send_text(f"你的金币不足！你只有{current_gold}金币，无法爆炸{gold}金币。")
            return False, f"你的金币不足！你只有{current_gold}金币，无法爆炸{gold}金币。", False

        BoomDataManager.add_gold(uid, -gold)
        new_gold = int(random.randint(0, gold * 2))
        BoomDataManager.add_gold(uid, new_gold)

        await self.send_text(f"你爆炸了{gold}金币！从废墟中获得了{new_gold}金币！目前你有{BoomDataManager.get_gold(uid)}金币。")
        return True, f"你爆炸了{gold}金币！你获得了{new_gold}金币！", False


class CheckInCommand(BaseCommand):
    command_name = "checkin"
    command_description = "每日签到领取金币"
    command_pattern = r"^.签到$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        try:
            platform = getattr(self.message.message_info, "platform", "")
            user_info = getattr(self.message.message_info, "user_info", None)
            if not user_info:
                return False, "无法获取用户信息！", False
            uid = person_api.get_person_id(platform, user_info.user_id)
        except Exception as e:
            logger.error(f"获取 person_id 失败: {e}")
            return False, "无法获取用户信息！", False

        if not BoomDataManager.read_id(uid):
            await self.send_text(f"你是第一次使用签到功能，已为你注册！当前你有10金币。")
            BoomDataManager.register_id(uid)
            return False, f"你是第一次使用签到功能，已为你注册！", False

        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        try:
            with open(BoomDataManager.DATA_FILE, "r", encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = {}
        uid_str = str(uid)
        if uid_str in data and "last_checkin" in data[uid_str]:
            if data[uid_str]["last_checkin"] == today_str:
                await self.send_text("你今天已经签到过了，明天再来吧！")
                return False, "你今天已经签到过了，明天再来吧！", False

        last_checkin = data.get(uid_str, {}).get("last_checkin", "")
        if last_checkin == (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d"):
            streak = data.get(uid_str, {}).get("streak", 0) + 1
        else:
            streak = 1

        reward_gold = random.randint(0, 20)
        uid_str = str(uid)
        if uid_str not in data:
            data[uid_str] = {}
        if "gold" not in data[uid_str] or not isinstance(data[uid_str]["gold"], int):
            data[uid_str]["gold"] = 0

        total_reward = streak + reward_gold
        data[uid_str]["gold"] = max(0, int(data[uid_str]["gold"]) + int(total_reward))
        data[uid_str]["last_checkin"] = today_str
        data[uid_str]["streak"] = streak

        with open(BoomDataManager.DATA_FILE, "w", encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        await self.send_text(f"签到成功！你连续签到了{streak}天，你获得了{streak}（连续）+{reward_gold}（随机）共{total_reward}金币！目前你有{data[uid_str]['gold']}金币。")
        return True, "签到成功！你获得了金币！", False


class MarketCommand(BaseCommand):
    command_name = "market"
    command_description = "查看股票市场信息"
    command_pattern = r"^.市场$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        stock_symbols = ["01", "02", "03", "04", "05"]
        market_info = "当前股票市场信息：\n"
        for symbol in stock_symbols:
            stock_info = stock.get_stock_info(symbol)
            if stock_info:
                market_info += f"{stock_info.name} ({stock_info.symbol}): ${stock_info.price}\n"
            else:
                market_info += f"{symbol}: 无法获取信息\n"
        next_update_time = stock.get_next_update_time(getattr(self, 'scheduler', None))
        market_info += f"距离下次更新时间: {next_update_time}\n"
        await self.send_text(market_info)
        return True, "查看市场信息成功！", False


class BuyStockCommand(BaseCommand):
    command_name = "buystock"
    command_description = "购买股票"
    command_pattern = r"^.购买(?P<symbol>\w+) (?P<quantity>\d+)$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        symbol = self.matched_groups.get("symbol")
        quantity_str = self.matched_groups.get("quantity")
        if not quantity_str.isdigit() or int(quantity_str) <= 0:
            return False, "购买数量错误！", False
        quantity = int(quantity_str)

        stock_info = stock.get_stock_info(symbol)
        if not stock_info:
            await self.send_text(f"股票代码{symbol}不存在！")
            return False, f"股票代码{symbol}不存在！", False

        try:
            platform = getattr(self.message.message_info, "platform", "")
            user_info = getattr(self.message.message_info, "user_info", None)
            if not user_info:
                return False, "无法获取用户信息！", False
            uid = person_api.get_person_id(platform, user_info.user_id)
        except Exception as e:
            logger.error(f"获取 person_id 失败: {e}")
            return False, "无法获取用户信息！", False

        total_price = int(round(stock_info.price * quantity))
        fee = math.ceil(total_price * 0.05)
        if fee < 1:
            fee = 1
        current_gold = BoomDataManager.get_gold(uid)
        if current_gold < total_price + fee:
            await self.send_text(f"你的金币不足以购买{quantity}股{stock_info.name}（含手续费{fee}金币），需要{total_price + fee}金币，你只有{current_gold}金币。")
            return False, f"金币不足以购买股票！", False

        BoomDataManager.add_gold(uid, -(total_price + fee))
        BoomDataManager._ensure_data_file()
        try:
            with open(BoomDataManager.DATA_FILE, "r", encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = {}
        uid_str = str(uid)
        if uid_str not in data:
            data[uid_str] = {}
        if "stocks" not in data[uid_str]:
            data[uid_str]["stocks"] = {}
        data[uid_str]["stocks"][symbol] = data[uid_str]["stocks"].get(symbol, 0) + quantity
        with open(BoomDataManager.DATA_FILE, "w", encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        try:
            try:
                with open(stock.DATA_FILE, "r", encoding='utf-8') as sf:
                    stock_data = json.load(sf)
            except Exception:
                stock_data = {}
            if symbol not in stock_data:
                stock_data[symbol] = {"name": stock_info.name, "price": stock_info.price}
            cur_weight = float(stock_data[symbol].get('weight', 0) or 0)
            required_per_unit = max(1, int(round(10 * (1 + abs(cur_weight)))))
            units = quantity // required_per_unit
            if units > 0:
                weight_add = -0.01 * units
                new_weight = cur_weight + weight_add
                stock_data[symbol]['weight'] = new_weight
                with open(stock.DATA_FILE, "w", encoding='utf-8') as sf:
                    json.dump(stock_data, sf, indent=4, ensure_ascii=False)
        except Exception:
            logger.exception("更新股票权重时出错")

        remaining = BoomDataManager.get_gold(uid)
        await self.send_text(f"你成功购买了{quantity}股{stock_info.name}，总价{total_price}金币，手续费{fee}金币，已扣除，共计{total_price + fee}金币，剩余{remaining}金币。")
        return True, f"成功购买股票！", False


class SellStockCommand(BaseCommand):
    command_name = "sellstock"
    command_description = "卖出股票"
    command_pattern = r"^.卖出(?P<symbol>\w+) (?P<quantity>\d+)$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        symbol = self.matched_groups.get("symbol")
        quantity_str = self.matched_groups.get("quantity")
        if not quantity_str.isdigit() or int(quantity_str) <= 0:
            return False, "卖出数量错误！", False
        quantity = int(quantity_str)

        stock_info = stock.get_stock_info(symbol)
        if not stock_info:
            await self.send_text(f"股票代码{symbol}不存在！")
            return False, f"股票代码{symbol}不存在！", False

        try:
            platform = getattr(self.message.message_info, "platform", "")
            user_info = getattr(self.message.message_info, "user_info", None)
            if not user_info:
                return False, "无法获取用户信息！", False
            uid = person_api.get_person_id(platform, user_info.user_id)
        except Exception as e:
            logger.error(f"获取 person_id 失败: {e}")
            return False, "无法获取用户信息！", False

        BoomDataManager._ensure_data_file()
        try:
            with open(BoomDataManager.DATA_FILE, "r", encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = {}
        uid_str = str(uid)
        if uid_str not in data or "stocks" not in data[uid_str] or symbol not in data[uid_str]["stocks"]:
            await self.send_text(f"你没有持有股票{stock_info.name}，无法卖出。")
            return False, f"没有持有该股票，无法卖出！", False

        owned_quantity = data[uid_str]["stocks"][symbol]
        if owned_quantity < quantity:
            await self.send_text(f"你持有的股票{stock_info.name}数量不足，无法卖出{quantity}股。")
            return False, f"持有股票数量不足，无法卖出！", False

        total_price = int(round(stock_info.price * quantity))
        fee = math.ceil(total_price * 0.05)
        if fee < 1:
            fee = 1
        if fee >= total_price:
            await self.send_text(f"此次卖出手续费{fee}金币不低于卖出总额{total_price}，无法完成卖出。")
            return False, f"手续费过高，无法卖出。", False

        net_gain = total_price - fee
        if uid_str not in data:
            data[uid_str] = {}
        if "gold" not in data[uid_str] or not isinstance(data[uid_str]["gold"], int):
            data[uid_str]["gold"] = 0
        data[uid_str]["gold"] = max(0, data[uid_str]["gold"] + net_gain)
        data[uid_str]["stocks"][symbol] -= quantity
        if data[uid_str]["stocks"][symbol] == 0:
            del data[uid_str]["stocks"][symbol]
        with open(BoomDataManager.DATA_FILE, "w", encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        try:
            try:
                with open(stock.DATA_FILE, "r", encoding='utf-8') as sf:
                    stock_data = json.load(sf)
            except Exception:
                stock_data = {}
            if symbol not in stock_data:
                stock_data[symbol] = {"name": stock_info.name, "price": stock_info.price}
            cur_weight = float(stock_data[symbol].get('weight', 0) or 0)
            required_per_unit = max(1, int(round(10 * (1 + abs(cur_weight)))))
            units = quantity // required_per_unit
            if units > 0:
                weight_add = 0.01 * units
                new_weight = cur_weight + weight_add
                stock_data[symbol]['weight'] = new_weight
                with open(stock.DATA_FILE, "w", encoding='utf-8') as sf:
                    json.dump(stock_data, sf, indent=4, ensure_ascii=False)
        except Exception:
            logger.exception("更新股票权重时出错")

        remaining = BoomDataManager.get_gold(uid)
        await self.send_text(f"你成功卖出了{quantity}股{stock_info.name}，卖出总额{total_price}金币，手续费{fee}金币，实得{net_gain}金币，当前余额{remaining}金币。")
        return True, f"成功卖出股票！", False


class PortfolioCommand(BaseCommand):
    command_name = "portfolio"
    command_description = "查看持有的股票"
    command_pattern = r"^.持仓$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        try:
            platform = getattr(self.message.message_info, "platform", "")
            user_info = getattr(self.message.message_info, "user_info", None)
            if not user_info:
                return False, "无法获取用户信息！", False
            uid = person_api.get_person_id(platform, user_info.user_id)
        except Exception as e:
            logger.error(f"获取 person_id 失败: {e}")
            return False, "无法获取用户信息！", False

        BoomDataManager._ensure_data_file()
        try:
            with open(BoomDataManager.DATA_FILE, "r", encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = {}
        uid_str = str(uid)
        if uid_str not in data or "stocks" not in data[uid_str]:
            await self.send_text("你当前没有持有任何股票。")
            return True, "查看持仓成功！", False

        portfolio_info = "你当前持有的股票：\n"
        for symbol, quantity in data[uid_str]["stocks"].items():
            stock_info = stock.get_stock_info(symbol)
            if stock_info:
                portfolio_info += f"{stock_info.name} ({stock_info.symbol}): {quantity}股\n"
            else:
                portfolio_info += f"{symbol}: {quantity}股\n"
        portfolio_info += f"你当前有{BoomDataManager.get_gold(uid)}金币。"
        await self.send_text(portfolio_info)
        return True, "查看持仓成功！", False


class StockHistoryCommand(BaseCommand):
    command_name = "stockhistory"
    command_description = "查看股票历史价格"
    command_pattern = r"^.历史价格 (?P<symbol>\w+)$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        symbol = self.matched_groups.get("symbol")

        history = stock.get_stock_price_history(symbol)
        if not history:
            await self.send_text(f"股票代码{symbol}不存在或无历史价格数据！")
            return False, f"股票代码{symbol}不存在或无历史价格数据！", False

        stock_info = stock.get_stock_info(symbol)
        name = stock_info.name if stock_info else ""
        history_info = f"{symbol}{name}的历史：\n"
        for time_fmt, price in history:
            history_info += f"{time_fmt}: ${price}\n"

        await self.send_text(history_info)
        return True, f"查看股票{symbol}历史价格成功！", False


class HelpCommand(BaseCommand):
    command_name = "boom_help"
    command_description = "查看金币炸弹插件帮助信息"
    command_pattern = r"^.金币炸弹$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        help_text = (
            "金币炸弹插件帮助信息：\n"
            "1. .签到\n"
            "2. .金币炸弹 <数量>\n"
            "3. .市场 - 查看当前股票市场\n"
            "4. .购买<股票id> <数量>\n"
            "5. .卖出<股票id> <数量>\n"
            "6. .持仓 - 查看你当前持有的持仓\n"
            "7. .历史价格 <股票id>"
        )
        await self.send_text(help_text)
        return True, "查看帮助信息成功！", False
