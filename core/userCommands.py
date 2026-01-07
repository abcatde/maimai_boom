'''
userCommands.py主要负责用户命令的处理
在commdands后缀的文件中，只需要处理信息的输入，初步处理后交由core中的模块处理具体逻辑

1.处理用户签到命令
2.处理用户查询个人信息命令
3.处理用户帮助命令

'''

from typing import Optional, Tuple
from src.plugin_system.apis import person_api
from src.plugin_system.base.base_command import BaseCommand
from . import userCore
from . import logCore

class SignInCommand(BaseCommand):
    command_name = "Sign_in"
    command_description = "签到"
    command_pattern = r"^.签到$"
    
    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """处理用户签到命令"""
        # 获取用户信息
        if not self.message or not self.message.message_info or not self.message.message_info.user_info:
            logCore.log_write("无法获取用户信息，签到失败")
            return False, "无法获取用户信息", False
        
        # 获取平台和用户ID
        platform = self.message.message_info.platform
        user_id = str(self.message.message_info.user_info.user_id)
        
        # 获取 person_id
        person_id = person_api.get_person_id(platform, user_id)
        logCore.log_write(f"获取 person_id: {person_id} (平台: {platform}, 用户ID: {user_id})")
        
        # 获取用户昵称（用于注册或显示）
        user_name = await person_api.get_person_value(person_id, "nickname", "未知用户")
        
        # 检查用户是否注册，未注册则先注册
        if not userCore.is_user_registered(person_id):
            userCore.register_user(person_id, user_name)
            logCore.log_write(f"新用户 {user_name} 注册成功，准备进行首次签到")
        
        # 检查今天是否已经签到
        if userCore.is_user_signed_in_today(person_id):
            await self.send_text(f"@{user_name} 你今天已经签到过了，明天再来吧！")
            return False, "今日已签到", False
        
        # 执行签到
        import random
        reward_coins = random.randint(10, 100)
        
        success, is_first_sign, sign_day, total_reward, final_coins = userCore.sign_in_user(person_id, reward_coins)
        
        if success:
            # 立即保存用户数据
            from . import user_data
            user_data._save_user_data_sync()
            
            # 构建签到消息
            if is_first_sign:
                message = f"@{user_name}\n🎉 欢迎！首次签到成功！\n" \
                         f"💰 新人礼包: 1000金币\n" \
                         f"🎲 随机奖励: {reward_coins}金币\n" \
                         f"📅 签到奖励: {sign_day}金币\n" \
                         f"💎 当前余额: {final_coins}金币"
            else:
                message = f"@{user_name}\n" \
                         f"✅ 签到成功！连续签到 {sign_day} 天\n" \
                         f"💰 本次获得: {sign_day}+{reward_coins} = {total_reward}金币\n" \
                         f"💎 当前余额: {final_coins}金币"
            
            await self.send_text(message)
            return True, "签到成功", True
        else:
            await self.send_text(f"@{user_name}\n签到失败，请查看日志或稍后再试。")
            return False, "签到失败", False
                
        
class UserInfoCommand(BaseCommand):
    command_name = "User_Info"
    command_description = "查询个人信息"
    command_pattern = r"^.持仓$"
    
    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """处理用户查询个人信息命令"""
        # 获取用户信息
        if not self.message or not self.message.message_info or not self.message.message_info.user_info:
            logCore.log_write("无法获取用户信息，查询失败")
            return False, "无法获取用户信息", False
        
        # 获取平台和用户ID
        platform = self.message.message_info.platform
        user_id = str(self.message.message_info.user_info.user_id)
        
        # 获取 person_id
        person_id = person_api.get_person_id(platform, user_id)
        logCore.log_write(f"获取 person_id: {person_id} (平台: {platform}, 用户ID: {user_id})")
        
        # 检查用户是否注册
        if not userCore.is_user_registered(person_id):
            await self.send_text("你还没有注册，请先签到注册！")
            return False, "用户未注册", False
        
        # 获取用户数据
        user = userCore.get_user_info(person_id)
        if not user:
            logCore.log_write(f"获取用户数据失败: person_id {person_id}")
            return False, "获取用户数据失败", False
        
        #获取用户持有的股票信息
        stock_list = userCore.get_user_stock_list(person_id)
        if stock_list:
            stock_info_text = "当前持有股票:\n"
            for stock_entry in stock_list:
                stock_info_text += f"{stock_entry['stock_type']} {stock_entry['stock_id']}{stock_entry['stock_name']} {stock_entry['quantity']} 股\n"

        # 构建用户信息文本
        info_text = f"@{user.user_name}\n"
        if stock_list:
            info_text += stock_info_text
        info_text += f"金币: {user.coins}"
        await self.send_text(info_text)
        return True, "查询成功", True
    
class HelpCommand(BaseCommand):
    command_name = "Help"
    command_description = "帮助"
    command_pattern = r"^.帮助$"
    
    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """处理用户帮助命令"""
        help_text = (
            "使用格式: .命令 <参数>\n"
            "1. .签到 - 每天签到获取金币奖励\n"
            "2. .持仓 - 查询个人基础信息\n"
            "3. .金币炸弹 <参数>\n"
            "4. .市场 - 查看股票市场\n"
            "5. .购买 <股票代码> <数量>\n" 
            "6. .出售 <股票代码> <数量>\n" 
            "7. .历史价格 <股票代码>\n"
            "8. .af - 圣遗物帮助\n" 
            "9. .地产 - 地产帮助" 
            
        )
        await self.send_text(help_text)
        return True, "帮助信息发送成功", True
    