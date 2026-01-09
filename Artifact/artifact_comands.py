'''
artifact_commands.py主要是对于圣遗物相关命令的实现和处理。

'''

from typing import Optional, Tuple

from ..core import user_data
from ..core import logCore
from src.plugin_system.apis import person_api
from src.plugin_system.base.base_command import BaseCommand
from ..core import userCore
from . import artifactCore

# .af 或者 .圣遗物 显示圣遗物系统帮助信息
class ArtifactHelpCommand(BaseCommand):
    command_name = "Artifact_Help"
    command_description = "显示圣遗物系统帮助信息"
    command_pattern = r"^\.af$|^\.圣遗物$"

    """显示圣遗物系统帮助信息"""
    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        help_text = (
            "圣遗物系统命令列表：\n"
            "1. .af 或者 .圣遗物 -显示圣遗物系统帮助信息\n"
            "2. .抽取 <数量> -抽取圣遗物或道具\n"
            "3. .仓库 -显示当前圣遗物仓库\n"
            "4. .分解 <圣遗物ID> -分解指定ID的圣遗物\n"
            "5. .锁定/解锁 <圣遗物ID> -解锁指定ID的圣遗物\n"
            "6. .强化 <圣遗物ID> -使用强化道具提升指定ID的圣遗物等级\n"
            "7. .展示 <圣遗物ID> -展示指定ID的圣遗物详细信息"
        )
        await self.send_text(help_text)
        return True, help_text, False
    
# .af 抽取 <数量> 命令抽取圣遗物或道具
class ArtifactDrawCommand(BaseCommand):
    command_name = "Artifact_Draw"
    command_description = "抽取圣遗物或道具"
    command_pattern = r"^\.抽卡 (?P<quantity>\d+)$"


    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """处理抽取圣遗物或道具命令"""
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

        quantity_str = self.matched_groups.get('quantity')
        if not quantity_str:
            return False, "命令格式错误", False
        try:
            quantity = int(quantity_str)
            if quantity <= 0:
                raise ValueError
            if quantity > 20:
                await self.send_text("一次性抽取数量不能超过20次！")
                return False, "抽取数量过多", False
        except ValueError:
            return False, "抽取数量错误", False
        
        # 根据数量调用artifactCore中的抽取函数，如果金币不足则停止抽取
        result_texts = []
        for _ in range(quantity):
            if user.coins < artifactCore.ARTIFACT_LOTTERY_COST:
                result_texts.append("当前金币金币不足了，无法继续抽取。")
                break
            success, result_text = artifactCore.draw_artifact_lottery(person_id, user.coins)
            result_texts.append(result_text)
            if success:
                # 重新获取用户数据以更新金币
                user = userCore.get_user_info(person_id)
                # 保存圣遗物数据到文件  
                artifactCore.save_user_artifact_data(person_id)
        
        await self.send_text("\n".join(result_texts) + f"\n当前拥有金币{user.coins}个")
        return True, "抽取成功", True
    

# .af 仓库 命令显示当前圣遗物仓库
class ArtifactStorageCommand(BaseCommand):
    command_name = "Artifact_Storage"
    command_description = "显示当前圣遗物仓库"
    command_pattern = r"^\.仓库$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """处理显示当前圣遗物仓库命令"""
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

        # 调用artifactCore中的函数获取仓库信息
        storage_info = artifactCore.get_artifact_storage_info(person_id)
        await self.send_text(storage_info)
        return True, "仓库信息发送成功", True
    
# .af 分解 <圣遗物ID> 命令分解指定ID的圣遗物
class ArtifactDismantleCommand(BaseCommand):
    command_name = "Artifact_Dismantle"
    command_description = "分解指定ID的圣遗物"
    command_pattern = r"^\.分解 (?P<artifact_id>\d+)$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """处理分解指定ID的圣遗物命令"""
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

        artifact_id_str = self.matched_groups.get('artifact_id')
        if not artifact_id_str:
            return False, "命令格式错误", False
        
        try:
            artifact_id = int(artifact_id_str)
            if artifact_id <= 0:
                raise ValueError
        except ValueError:
            return False, "圣遗物ID错误", False
        
        # 调用artifactCore中的函数分解圣遗物
        success, result_text = artifactCore.disassemble_artifact(person_id, artifact_id)
        await self.send_text(result_text)
        #保存圣遗物数据到文件
        artifactCore.save_user_artifact_data(person_id)
        return success, result_text, success
    
    # .af 锁定 <圣遗物ID> 命令锁定指定ID的圣遗物
class ArtifactLockCommand(BaseCommand):
    command_name = "Artifact_Lock"
    command_description = "锁定指定ID的圣遗物"
    command_pattern = r"^\.锁定 (?P<artifact_id>\d+)$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """处理锁定指定ID的圣遗物命令"""
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

        artifact_id_str = self.matched_groups.get('artifact_id')
        if not artifact_id_str:
            return False, "命令格式错误", False
        
        try:
            artifact_id = int(artifact_id_str)
            if artifact_id <= 0:
                raise ValueError
        except ValueError:
            return False, "圣遗物ID错误", False
        
        # 调用artifactCore中的函数锁定圣遗物
        success = artifactCore.lock_artifact(person_id, artifact_id)
        if success:
            result_text = f"圣遗物 {artifact_id} 已成功锁定。"
        else:
            result_text = f"锁定圣遗物 {artifact_id} 失败，圣遗物不存在。"
        await self.send_text(result_text)
        return success, result_text, success
    
# .af 解锁 <圣遗物ID> 命令解锁指定ID的圣遗物
class ArtifactUnlockCommand(BaseCommand):
    command_name = "Artifact_Unlock"
    command_description = "解锁指定ID的圣遗物"
    command_pattern = r"^\.解锁 (?P<artifact_id>\d+)$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """处理解锁指定ID的圣遗物命令"""
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

        artifact_id_str = self.matched_groups.get('artifact_id')
        if not artifact_id_str:
            return False, "命令格式错误", False
        
        try:
            artifact_id = int(artifact_id_str)
            if artifact_id <= 0:
                raise ValueError
        except ValueError:
            return False, "圣遗物ID错误", False
        
        # 调用artifactCore中的函数解锁圣遗物
        success = artifactCore.unlock_artifact(person_id, artifact_id)
        if success:
            result_text = f"圣遗物 {artifact_id} 已成功解锁。"
        else:
            result_text = f"解锁圣遗物 {artifact_id} 失败，圣遗物不存在。"
        await self.send_text(result_text)
        return success, result_text, success
    
# .强化 <圣遗物ID> 命令使用强化道具提升指定ID的圣遗物等级
'''
升级需要消耗的强化道具数量 = 当前等级 * 2 ,需要金币数量 = 当前等级 * 100
每次强化成功，圣遗物等级提升1级，最高等级不限制
'''
class ArtifactEnhanceCommand(BaseCommand):
    command_name = "Artifact_Enhance"
    command_description = "使用强化道具提升指定ID的圣遗物等级"
    command_pattern = r"^\.强化 (?P<artifact_id>\d+)$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """处理使用强化道具提升指定ID的圣遗物等级命令"""
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

        artifact_id_str = self.matched_groups.get('artifact_id')
        if not artifact_id_str:
            return False, "命令格式错误", False
        
        try:
            artifact_id = int(artifact_id_str)
            if artifact_id <= 0:
                raise ValueError
        except ValueError:
            return False, "圣遗物ID错误", False
        
        # 获取用户的强化道具数量
        reinforcement_items = user_data.get_artifact_upgrade_items(person_id)
        
        # 调用artifactCore中的函数强化圣遗物
        success, result_text = artifactCore.enhance_artifact(person_id, artifact_id, reinforcement_items)
        await self.send_text(result_text)
        #保存圣遗物数据到文件
        artifactCore.save_user_artifact_data(person_id)
        return success, result_text, success

# .展示 <圣遗物ID> 命令展示指定ID的圣遗物详细信息
class ArtifactShowCommand(BaseCommand):
    command_name = "Artifact_Show"
    command_description = "展示指定ID的圣遗物详细信息"
    command_pattern = r"^\.展示 (?P<artifact_id>\d+)$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """处理展示指定ID的圣遗物详细信息命令"""
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

        artifact_id_str = self.matched_groups.get('artifact_id')
        if not artifact_id_str:
            return False, "命令格式错误", False
        
        try:
            artifact_id = int(artifact_id_str)
            if artifact_id <= 0:
                raise ValueError
        except ValueError:
            return False, "圣遗物ID错误", False
        
        # 调用artifactCore中的函数获取圣遗物详细信息
        success, result_text = artifactCore.get_artifact_info(person_id, artifact_id)
        await self.send_text(result_text)
        return success, result_text, success