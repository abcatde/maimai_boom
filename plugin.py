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
from .scheduler import SimpleScheduler
from . import stock

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
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.scheduler = SimpleScheduler()
            try:
                stock.schedule_stock_price_updates(self.scheduler)
            except Exception:
                logger.exception("调用 stock.schedule_stock_price_updates 时出错")
        except Exception:
            self.scheduler = None
            logger.exception("初始化 SimpleScheduler 失败")