'''
adminCommands.py管理员命令类

'''



from typing import Optional, Tuple
from src.plugin_system.base.base_command import BaseCommand
from ..core import logCore
from ..core import userCore

#兑换码结构体
class RedeemCode:
    def __init__(self, code: str, amount: int, uses: int):
        self.code = code            # 兑换码字符串
        self.amount = amount        # 兑换码对应的金额
        self.uses = uses            # 兑换码剩余使用次数

#兑换码列表全局变量
redeem_code_list = {}

# 管理员帮助页面
class AdminHelpCommand(BaseCommand):
    command_name = "Admin_Help"
    command_description = "管理员帮助"
    # 接受包含字母数字的密钥，避免仅限数字导致匹配失败
    command_pattern = r"^.admin help (?P<adminPassworld>[A-Za-z0-9]+)$"
    
    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """处理管理员帮助命令"""

        # 限定只能在私聊中进行
        group_info = getattr(self.message.message_info, 'group_info', None)
        if group_info and getattr(group_info, 'group_id', None):
            await self.send_text("管理员命令只能在私聊中使用，请注意保管密钥,如有泄露，及时更新密码。")
            return False, "管理员命令只能在私聊中使用", False
        
        #验证密钥
        admin_passworld = self.matched_groups.get("adminPassworld", "")
        config_Passworld = self.get_config("admin.admin_password", "admin123")
        if admin_passworld != config_Passworld:
            await self.send_text("管理员密钥错误。")
            return False, "管理员密钥错误", False
        
        help_text = (
            "管理员命令列表：\n"
            ".admin save <adminPassworld> - 保存用户和股票数据\n"
            ".admin 生成兑换码 <adminPassworld> <amount> <uses> - 生成指定金额和使用次数的兑换码"

        )
        await self.send_text(help_text)
        return True, "管理员帮助显示成功", False

# 处理保存数据的管理员命令
class SaveDataCommand(BaseCommand):
    command_name = "Save_data"
    command_description = "保存数据"
    command_pattern = r"^.admin save (?P<adminPassworld>[A-Za-z0-9]+)$"
    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """处理保存数据的管理员命令"""
        # 限定只能在私聊中进行
        group_info = getattr(self.message.message_info, 'group_info', None)
        if group_info and getattr(group_info, 'group_id', None):
            await self.send_text("管理员命令只能在私聊中使用，请注意保管密钥,如有泄露，及时更新密码。")
            return False, "管理员命令只能在私聊中使用", False
        
        #验证密钥
        admin_passworld = self.matched_groups.get("adminPassworld", "")
        config_Passworld = self.get_config("admin.admin_password", "admin123")
        if admin_passworld != config_Passworld:
            await self.send_text("管理员密钥错误。")
            return False, "管理员密钥错误", False
        
        #保存数据
        from ..core import user_data
        from ..stock import stock_data
        # 立即同步写入用户与股票数据（用户数据使用同步版本，避免未 await 导致不落盘）
        user_data._save_user_data_sync()
        stock_data.save_stock_data()
        await self.send_text("数据保存成功。")
        logCore.log_write("管理员保存数据命令执行成功。")
        return True, "数据保存成功", False

# 生成指定金额，指定兑换次数的兑换码
class GenerateRedeemCodeCommand(BaseCommand):
    command_name = "Generate_Redeem_Code"
    command_description = "生成兑换码"
    command_pattern = r"^.admin 生成兑换码 (?P<adminPassworld>[A-Za-z0-9]+) (?P<amount>\d+) (?P<uses>\d+)$"
    
    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """处理生成兑换码的管理员命令"""
        # 限定只能在私聊中进行
        group_info = getattr(self.message.message_info, 'group_info', None)
        if group_info and getattr(group_info, 'group_id', None):
            await self.send_text("管理员命令只能在私聊中使用，请注意保管密钥,如有泄露，及时更新密码。")
            return False, "管理员命令只能在私聊中使用", False
        
        #验证密钥
        admin_passworld = self.matched_groups.get("adminPassworld", "")
        config_Passworld = self.get_config("admin.admin_password", "admin123")
        if admin_passworld != config_Passworld:
            await self.send_text("管理员密钥错误。")
            return False, "管理员密钥错误", False
        
        #获取参数
        amount_str = self.matched_groups.get("amount", "0")
        uses_str = self.matched_groups.get("uses", "0")
        try:
            amount = int(amount_str)
            uses = int(uses_str)
            if amount <= 0 or uses <= 0:
                raise ValueError
        except ValueError:
            await self.send_text("无效的金额或使用次数，必须为正整数。")
            return False, "无效的金额或使用次数", False
        
        #生成兑换码，在内存中，用户使用兑换时判断，不需要本地化
        import random
        import string
        redeem_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
        redeem_code_list[redeem_code] = RedeemCode(redeem_code, amount, uses)
        await self.send_text(f"生成兑换码成功：\n兑换码：{redeem_code}\n金额：{amount}\n使用次数：{uses}")
        logCore.log_write(f"管理员生成兑换码命令执行成功，兑换码：{redeem_code}，金额：{amount}，使用次数：{uses}")
        return True, "生成兑换码成功", False
    
# .兑换码 <code>
class RedeemCodeCommand(BaseCommand):
    command_name = "Redeem_Code"
    command_description = "使用兑换码兑换金币"
    command_pattern = r"^.兑换码 (?P<code>[A-Z0-9]{10})$"
    
    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """处理使用兑换码的命令"""
        # 获取用户身份信息，sender 在新版 BaseMessageInfo 中不存在，需使用 user_info
        if not self.message or not self.message.message_info or not self.message.message_info.user_info:
            logCore.log_write("无法获取用户信息，兑换失败")
            return False, "无法获取用户信息", False

        platform = self.message.message_info.platform
        user_id = str(self.message.message_info.user_info.user_id)
        from src.plugin_system.apis import person_api
        person_id = person_api.get_person_id(platform, user_id)

        # 检查用户是否注册
        if not userCore.is_user_registered(person_id):
            await self.send_text("你还没有注册，请先签到注册！")
            return False, "用户未注册", False

        #获取兑换码
        code = self.matched_groups.get("code", "")
        if code not in redeem_code_list:
            await self.send_text("无效的兑换码。")
            return False, "无效的兑换码", False
        
        redeem_code = redeem_code_list[code]
        if redeem_code.uses <= 0:
            await self.send_text("该兑换码已被使用完。")
            return False, "兑换码使用完", False
        
        #给用户增加金币
        userCore.update_coins_to_user(person_id, redeem_code.amount)
        
        #减少兑换码使用次数
        redeem_code.uses -= 1
        await self.send_text(f"@{userCore.get_user_info(person_id).user_name} 兑换成功！你获得了 {redeem_code.amount} 金币。\n当前拥有{userCore.get_user_info(person_id).coins}金币")
        logCore.log_write(f"用户ID {person_id} 使用兑换码 {code} 成功，获得 {redeem_code.amount} 金币，剩余使用次数：{redeem_code.uses}")
        return True, "兑换成功", False