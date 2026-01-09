'''
adminCommands.py管理员命令类

'''



from src.plugin_system.base.base_command import BaseCommand
from ..core import logCore


# 处理保存数据的管理员命令
class SaveStockDataCommand(BaseCommand):
    command_name = "Save_data"
    command_description = "保存数据"
    command_pattern = r"^.admin save_data (?P<adminPassworld>\d+)$"
    async def execute(self) -> tuple[bool, str, bool]:
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
        user_data.save_user_data()
        stock_data.save_stock_data()
        await self.send_text("数据保存成功。")
        logCore.log_write("管理员保存数据命令执行成功。")
        return True, "数据保存成功", False

