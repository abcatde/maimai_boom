from encodings.punycode import T
from typing import List, Tuple, Type

from src.plugin_system import BasePlugin, register_plugin, ComponentInfo
from src.plugin_system.base.config_types import ConfigField
from .core import userCommands
from .stock import stockCommands
from .Artifact import artifact_comands
from .MiniGame import TexasHoldemCommands
from .MiniGame import gold_boom

@register_plugin
class MaillStreetStoriesPlugin(BasePlugin):
    plugin_name = "maill_street_stories_plugin"
    enable_plugin = True
    dependencies = []
    python_dependencies = []
    config_file_name = "config.toml"
    config_schema = {}
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.scheduler = None

    # 加载数据
    def on_plugin_load(self):
        from .core import user_data
        from .core import timeCore
        from .stock import stock_data
        from .stock import stockPriceControl  # 导入价格控制模块以注册定时任务
        
        # 创建并启动任务调度器
        self.scheduler = timeCore.TaskScheduler()
        self.scheduler.start()
        
        # 加载数据
        user_data.load_user_data()
        stock_data.load_stock_data()

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        self.on_plugin_load()#初始化数据
        return [
            # 在这里注册你的命令类
            (userCommands.SignInCommand.get_command_info(), userCommands.SignInCommand),        
            (userCommands.UserInfoCommand.get_command_info(), userCommands.UserInfoCommand),    
            (userCommands.HelpCommand.get_command_info(), userCommands.HelpCommand),
            (stockCommands.MarketCommand.get_command_info(), stockCommands.MarketCommand),
            (stockCommands.StockPriceHistoryCommand.get_command_info(), stockCommands.StockPriceHistoryCommand),
            (stockCommands.BuyStockCommand.get_command_info(), stockCommands.BuyStockCommand),
            (stockCommands.SellStockCommand.get_command_info(), stockCommands.SellStockCommand),
            (artifact_comands.ArtifactHelpCommand.get_command_info(), artifact_comands.ArtifactHelpCommand),
            (artifact_comands.ArtifactEnhanceCommand.get_command_info(), artifact_comands.ArtifactEnhanceCommand),
            (artifact_comands.ArtifactDrawCommand.get_command_info(), artifact_comands.ArtifactDrawCommand),
            (artifact_comands.ArtifactDismantleCommand.get_command_info(), artifact_comands.ArtifactDismantleCommand),
            (artifact_comands.ArtifactLockCommand.get_command_info(), artifact_comands.ArtifactLockCommand),
            (artifact_comands.ArtifactUnlockCommand.get_command_info(), artifact_comands.ArtifactUnlockCommand),
            (artifact_comands.ArtifactStorageCommand.get_command_info(), artifact_comands.ArtifactStorageCommand),
            (artifact_comands.ArtifactShowCommand.get_command_info(), artifact_comands.ArtifactShowCommand),
            (TexasHoldemCommands.TexasHoldemHelpCommand.get_command_info(), TexasHoldemCommands.TexasHoldemHelpCommand),
            (TexasHoldemCommands.CreateRoomCommand.get_command_info(), TexasHoldemCommands.CreateRoomCommand),
            (TexasHoldemCommands.JoinRoomCommand.get_command_info(), TexasHoldemCommands.JoinRoomCommand),
            (TexasHoldemCommands.LeaveRoomCommand.get_command_info(), TexasHoldemCommands.LeaveRoomCommand),
            (TexasHoldemCommands.StartGameCommand.get_command_info(), TexasHoldemCommands.StartGameCommand),
            (TexasHoldemCommands.BetCommand.get_command_info(), TexasHoldemCommands.BetCommand),
            (TexasHoldemCommands.FoldCommand.get_command_info(), TexasHoldemCommands.FoldCommand),
            (TexasHoldemCommands.NextRoundCommand.get_command_info(), TexasHoldemCommands.NextRoundCommand),
            (TexasHoldemCommands.RaiseCommand.get_command_info(), TexasHoldemCommands.RaiseCommand),
            (TexasHoldemCommands.CallCommand.get_command_info(), TexasHoldemCommands.CallCommand),
            (TexasHoldemCommands.CheckCommand.get_command_info(), TexasHoldemCommands.CheckCommand),
            (TexasHoldemCommands.ViewRoomCommand.get_command_info(), TexasHoldemCommands.ViewRoomCommand),
            (gold_boom.GoldBoomCommand.get_command_info(), gold_boom.GoldBoomCommand),

        ]
    
    
        # 配置Schema定义
    config_schema: dict = {
        "plugin": {
            "name": ConfigField(type=str, default="maill_street_stories_plugin", description="插件名称"),
            "version": ConfigField(type=str, default="1.2.0", description="插件版本"),
            "enabled": ConfigField(type=bool, default=True, description="是否启用插件"),
        },
        #参数配置
        "settings": {
            "initial_coins": ConfigField(type=int, default=1000, description="新用户初始金币数量"),
            
        },
    }