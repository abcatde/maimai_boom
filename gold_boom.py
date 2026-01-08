'''
gold_boom.py主要负责黄金爆炸小游戏的逻辑处理
谁记得我当时只准备写个这个...、
'''

from typing import Optional, Tuple
from src.plugin_system.apis import send_api
from src.plugin_system.base.base_command import BaseCommand
from ..core import userCore


# .金币炸弹 <数量> 命令
class GoldBoomCommand(BaseCommand):
    command_name = "Gold_Boom"
    command_description = "金币炸弹"
    command_pattern = r"^.金币炸弹 (\d+)$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """处理金币炸弹小游戏命令"""
        if not self.message or not self.message.message_info or not self.message.message_info.user_info:
            return False, "无法获取用户信息", False

        user_id = str(self.message.message_info.user_info.user_id)
        user_qq = self.message.message_info.user_info.user_qq
        amount_str = self.get_matched_group(1)
        
        try:
            amount = int(amount_str)
            if amount <= 0:
                await self.send_text("请输入正整数数量的金币进行游戏。")
                return False, "无效数量", False
        except ValueError:
            await self.send_text("请输入有效的金币数量。")
            return False, "无效数量格式", False

        # 检查用户金币是否足够
        user_coins = await send_api.get_user_coins(self.message.message_info.platform, user_id)
        if user_coins < amount:
            await self.send_text(f"你的金币不足，当前持有金币：{user_coins}。")
            return False, "金币不足", False

        # 扣除金币并进行游戏逻辑
        userCore.update_coins_to_user(user_id, -amount)

        # 游戏逻辑,随机获得[-1, +1]倍的金币
        import random
        multiplier = random.choice([-1, 0, 1])
        reward = amount * multiplier + amount  # 赢得的金币
        #为用户添加奖励金币
        userCore.update_coins_to_user(user_id, reward)
        await self.send_text(f"金币炸弹结果：你投入了 {amount} 金币，获得了 {reward} 金币！（倍率：{multiplier + 1}）")
        return True, "金币炸弹完成", True