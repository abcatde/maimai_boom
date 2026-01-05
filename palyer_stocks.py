from typing import Optional, Tuple
from src.plugin_system import BasePlugin, register_plugin, ComponentInfo
#查看玩家菜单
class PlayerStocksMenu(BasePlugin):
    command_name = "paleMenu"
    command_description = "玩家菜单"
    command_pattern = r"^.玩家菜单 (?P<num>\w+)$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        #获取菜单项
        num_str = self.matched_groups.get("num")

        if not num_str or not num_str.isdigit():
            async def execute(self) -> Tuple[bool, Optional[str], bool]:
                player_help = (
                    "玩家菜单帮助信息：\n"
                    "1. 自上架股票管理\n"
                    "2. 金币宝藏"
                )
                await self.send_text(player_help)
                return True, "查看帮助信息成功！", False
            
        if False:
            async def execute(self) -> Tuple[bool, Optional[str], bool]:
                player_help = (
                    
                    "自上架股票管理：\n"
                    "1. 上架新股票(10000金币)\n"
                    "-花费10000金币上架一只新股票，股票代码需唯一且符合规范。\n"
                    "-交易税由股票持有者获得。"
                    "-如果股票价格归0，股票将被强制下架。\n"
                    "2. 调整交易税率\n"
                    "-调整自己持有股票的交易税率，范围0%-28%，每日可调整两次。\n"
                    "3. 补充保证质押金\n"
                    "-补充自己持有股票的保证质押金，当股票价格低于保证质押金时，会自动消耗质押金抬高股票价格。\n"
                    "4.查看质押金和自建股票"
                    
                    
                )
                await self.send_text(player_help)
                return True, "查看帮助信息成功！", False
            
        if num_str == "2":
            #金币宝藏游戏规则：
            """"1.使用.金币宝藏"""



            async def execute(self) -> Tuple[bool, Optional[str], bool]:
                

                return True, "查看帮助信息成功！", False