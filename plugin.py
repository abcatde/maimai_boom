from typing import List, Tuple, Type

from src.plugin_system import BasePlugin, register_plugin, ComponentInfo
from src.common.logger import get_logger

from .commands import (
    BoomCommand, CheckInCommand, MarketCommand, BuyStockCommand,
    SellStockCommand, PortfolioCommand, StockHistoryCommand, HelpCommand,
)
from .gold_treasure import (
    GoldTreasureHelpCommand, BuryTreasureCommand, DigTreasureCommand, FastDigTreasureCommand, ShowLandCommand,
)
from .gold_card import (
    CreateRoomCommand, JoinRoomCommand, DealCommand, SettleCommand, RaiseCommand,GoldCardHelp
)
from .scheduler import SimpleScheduler
from . import stock
from . import gold_card

logger = get_logger("boom_plugin")


@register_plugin
class BoomPlugin(BasePlugin):
    plugin_name = "Boom_plugin"
    enable_plugin = True
    dependencies = []
    python_dependencies = []
    config_file_name = "config.toml"
    config_schema = {}

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        return [
            (BoomCommand.get_command_info(), BoomCommand),
            (CheckInCommand.get_command_info(), CheckInCommand),
            (MarketCommand.get_command_info(), MarketCommand),
            (BuyStockCommand.get_command_info(), BuyStockCommand),
            (PortfolioCommand.get_command_info(), PortfolioCommand),
            (SellStockCommand.get_command_info(), SellStockCommand),
            (HelpCommand.get_command_info(), HelpCommand),
            (StockHistoryCommand.get_command_info(), StockHistoryCommand),
            (GoldTreasureHelpCommand.get_command_info(), GoldTreasureHelpCommand),
            (BuryTreasureCommand.get_command_info(), BuryTreasureCommand),
            (DigTreasureCommand.get_command_info(), DigTreasureCommand),
            (FastDigTreasureCommand.get_command_info(), FastDigTreasureCommand),
            (ShowLandCommand.get_command_info(), ShowLandCommand),
            (CreateRoomCommand.get_command_info(), CreateRoomCommand),
            (JoinRoomCommand.get_command_info(), JoinRoomCommand),
            (DealCommand.get_command_info(), DealCommand),
            (RaiseCommand.get_command_info(), RaiseCommand),
            (SettleCommand.get_command_info(), SettleCommand),
            (GoldCardHelp.get_command_info(),GoldCardHelp),
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.scheduler = SimpleScheduler()
            try:
                stock.schedule_stock_price_updates(self.scheduler)
            except Exception:
                logger.exception("调用 stock.schedule_stock_price_updates 时出错")
            try:
                # 注册金币牌局的超时检查任务（每6分钟）
                try:
                    gold_card.schedule_room_timeouts(self.scheduler)
                except Exception:
                    logger.exception("调用 gold_card.schedule_room_timeouts 时出错")
            except Exception:
                logger.exception("注册 gold_card 超时检查失败")
        except Exception:
            self.scheduler = None
            logger.exception("初始化 SimpleScheduler 失败")