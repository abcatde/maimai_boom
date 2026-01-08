from src.plugin_system.apis import person_api
from src.plugin_system.base.base_command import BaseCommand
from .TexasHoldemCore import Room, Player, fold, join_room, leave_room, place_bet, send_message, start_new_hand, next_betting_round, settle_game
from typing import Dict, Optional, Tuple


# 全局变量，存储房间数据
rooms: Dict[int, Room] = {}

# .德州扑克帮助
class TexasHoldemHelpCommand(BaseCommand):
    command_name = "Texas_Holdem_Help"
    command_description = "德州扑克"
    command_pattern = r"^.德州扑克$"
    
    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """处理德州扑克帮助命令"""
        help_text = (
            "德州扑克指令列表：\n"
            ".创建房间 [倍率] - 创建一个新的德州扑克房间，可选倍率参数（默认为1）\n"
            ".加入房间 <房间ID> - 加入指定ID的德州扑克房间\n"
            ".离开房间 - 离开当前所在的德州扑克房间\n"
            ".开局 - 手动开始游戏（当房间人数足够时）\n"
            ".下注 <金额> - 在当前轮次下注指定金额筹码\n"
            ".跟注 - 跟随当前最高下注金额\n"
            ".加注 <金额> - 在当前最高下注基础上加注指定金额筹码\n"
            ".弃牌 - 弃掉当前手牌，退出本局游戏\n"
            ".下一轮 - 推进游戏到下一轮（发公共牌或结算）\n"
        )
        await self.send_text(help_text)
        return True, "显示德州扑克帮助", True


# .跟注 命令
class CallCommand(BaseCommand):
    command_name = "Call"
    command_description = "跟注"
    command_pattern = r"^.跟注$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        user_id = str(self.message.message_info.user_info.user_id)
        user_id_int = int(user_id)
        for room in rooms.values():
            for player in room.players:
                if player.user_id == user_id_int:
                    call_amount = room.current_bet - player.current_bet
                    if call_amount <= 0:
                        await self.send_text("当前无需跟注。"); return False, "无需跟注", False
                    if player.chips < call_amount:
                        await self.send_text("筹码不足，无法跟注。"); return False, "筹码不足", False
                    place_bet(room, user_id_int, call_amount)
                    await self.send_text(f"{player.username} 跟注 {call_amount} 筹码。当前底池：{room.pot}")
                    return True, f"{player.username} 跟注 {call_amount}", True
        await self.send_text("您不在任何房间中，无法跟注。")
        return False, "用户不在任何房间中", False

# .加注 命令
class RaiseCommand(BaseCommand):
    command_name = "Raise"
    command_description = "加注"
    command_pattern = r"^.加注 (?P<amount>\d+)$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        amount_str = self.matched_groups.get('amount')
        if not amount_str:
            await self.send_text("命令格式错误，请使用 .加注 <金额>")
            return False, "命令格式错误", False
        amount = int(amount_str)
        user_id = str(self.message.message_info.user_info.user_id)
        user_id_int = int(user_id)
        for room in rooms.values():
            for player in room.players:
                if player.user_id == user_id_int:
                    min_raise = max(room.big_blind, room.current_bet * 2 - player.current_bet)
                    if amount < min_raise:
                        await self.send_text(f"加注金额不能低于最小加注额：{min_raise}")
                        return False, "加注金额过低", False
                    if player.chips < amount:
                        await self.send_text("筹码不足，无法加注。"); return False, "筹码不足", False
                    place_bet(room, user_id_int, amount)
                    room.current_bet = player.current_bet
                    await self.send_text(f"{player.username} 加注到 {amount} 筹码。当前底池：{room.pot}")
                    return True, f"{player.username} 加注 {amount}", True
        await self.send_text("您不在任何房间中，无法加注。")
        return False, "用户不在任何房间中", False





# .创建房间 命令
class CreateRoomCommand(BaseCommand):
    command_name = "Create_Room"
    command_description = "创建房间"
    command_pattern = r"^.创建房间$"
    
    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """处理创建房间命令"""
        # 获取平台和用户ID
        user_id = str(self.message.message_info.user_info.user_id)
        username = self.message.message_info.user_info.nickname
        
        #确保用户不在房间中
        for room in rooms.values():
            for player in room.players:
                if player.user_id == int(user_id):
                    await self.send_text("您已经在一个房间中，无法创建新房间。")
                    return False, "用户已在房间中", False
        # 创建新房间，生产10001-99999的房间ID，确保不重复
        import random
        while True:
            room_id = random.randint(10001, 99999)
            if room_id not in rooms:
                break
        new_room = Room(room_id)
        rooms[room_id] = new_room
        await self.send_text(f"房间 {room_id} 创建成功！请 .加入房间 {room_id} 参与游戏。")
        return True, f"房间 {room_id} 创建成功！", True
        

# .创建房间 命令（支持倍率）
class CreateRoomCommand(BaseCommand):
    command_name = "Create_Room"
    command_description = "创建房间"
    command_pattern = r"^.创建房间(?: (?P<rate>\d+))?$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """处理创建房间命令，支持倍率参数"""
        user_id = str(self.message.message_info.user_info.user_id)
        username = self.message.message_info.user_info.nickname
        rate_str = self.matched_groups.get('rate')
        rate = int(rate_str) if rate_str else 1
        if rate < 1:
            await self.send_text("倍率必须为正整数！")
            return False, "倍率无效", False
        #确保用户不在房间中
        for room in rooms.values():
            for player in room.players:
                if player.user_id == int(user_id):
                    await self.send_text("您已经在一个房间中，无法创建新房间。")
                    return False, "用户已在房间中", False
        # 创建新房间，生产10001-99999的房间ID，确保不重复
        import random
        while True:
            room_id = random.randint(10001, 99999)
            if room_id not in rooms:
                break
        new_room = Room(room_id)
        new_room.rate = rate
        rooms[room_id] = new_room
        await self.send_text(f"房间 {room_id} 创建成功！\n倍率：{rate}（1筹码={rate}金币）\n请使用 .加入房间 {room_id} 参与游戏。")
        return True, f"房间 {room_id} 创建成功！", True

        
    
# .加入房间 <房间ID> 命令
class JoinRoomCommand(BaseCommand):
    command_name = "Join_Room"
    command_description = "加入房间"
    command_pattern = r"^.加入房间 (?P<room_id>\d+)$"
    
    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """处理加入房间命令"""
        room_id_str = self.matched_groups.get('room_id')
        if not room_id_str:
            await self.send_text("命令格式错误，请使用 .加入房间 <房间ID>")
            return False, "命令格式错误", False
        room_id = int(room_id_str)
        
        # 检查房间是否存在
        if room_id not in rooms:
            await self.send_text(f"房间 {room_id} 不存在。")
            return False, f"房间 {room_id} 不存在", False
        
        room = rooms[room_id]
        
        # 获取玩家信息
        user_id = str(self.message.message_info.user_info.user_id)
        username = self.message.message_info.user_info.nickname
        
        # 创建玩家对象，初始筹码为房间设定
        user_qq = getattr(self.message.message_info.user_info, 'user_qq', 0)
        player = Player(int(user_id), username, user_qq, room.initial_chips)
        
        # 尝试加入房间
        if not join_room(room, player):
            await self.send_text(f"房间 {room_id} 已满，无法加入。")
            return False, f"房间 {room_id} 已满", False

        # 读取金币余额
        person = await person_api.get_person_by_platform_and_user_id(self.message.message_info.platform, user_id)
        gold = getattr(person, 'coins', 0) if person else 0
        rate = getattr(room, 'rate', 1)
        chips_needed = room.initial_chips * rate
        if gold < chips_needed:
            await self.send_text(f"金币不足，加入本房间需 {chips_needed} 金币（倍率{rate}，初始筹码{room.initial_chips}）。")
            return False, "金币不足", False
        # 扣除金币
        await person_api.add_coins(self.message.message_info.platform, user_id, -chips_needed)
        player = Player(int(user_id), username, user_qq, room.initial_chips)
        # 尝试加入房间
        if not join_room(room, player):
            await self.send_text(f"房间 {room_id} 已满，无法加入。")
            # 返还金币
            await person_api.add_coins(self.message.message_info.platform, user_id, chips_needed)
            return False, f"房间 {room_id} 已满", False
        await self.send_text(f"--------------------\n{username} 成功加入房间 {room_id}！\n当前房间人数：{len(room.players)}\n--------------------")
        # 自动开局：仅当房间人数达到最大人数时自动开局（最大人数为room.max_players）
        if hasattr(room, 'max_players') and len(room.players) >= room.max_players and room.round_stage == "waiting":
            start_new_hand(room)
            await self.send_text(f"房间 {room_id} 游戏开始！\n庄家：{room.players[room.dealer_index].username}")
            # 私聊每位玩家手牌
            for p in room.players:
                hand_str = ', '.join(p.hand)
                await send_message(p.user_id, f"您的手牌是: {hand_str}")
            await self.send_text(f"请玩家依次操作。当前轮次：{room.round_stage}")
        return True, f"{username} 加入房间 {room_id} 成功", True

    # .开局 命令
    class StartGameCommand(BaseCommand):
        command_name = "Start_Game"
        command_description = "手动开局"
        command_pattern = r"^.开局$"

        async def execute(self) -> Tuple[bool, Optional[str], bool]:
            user_id = str(self.message.message_info.user_info.user_id)
            user_id_int = int(user_id)
            for room_id, room in rooms.items():
                for player in room.players:
                    if player.user_id == user_id_int:
                        if room.round_stage != "waiting":
                            return False, "房间已在游戏中", False
                        if len(room.players) < 2:
                            await self.send_text("房间人数不足2人，无法开局。"); return False, "人数不足", False
                        start_new_hand(room)
                        await self.send_text(f"房间 {room_id} 游戏开始！\n庄家：{room.players[room.dealer_index].username}")
                        for p in room.players:
                            hand_str = ', '.join(p.hand)
                            await send_message(p.user_id, f"您的手牌是: {hand_str}")
                        await self.send_text(f"请玩家依次操作。当前轮次：{room.round_stage}")
                        return True, "手动开局成功", True
            await self.send_text("您不在任何房间中，无法开局。")
            return False, "用户不在任何房间中", False
        
# .离开房间 命令
class LeaveRoomCommand(BaseCommand):
    command_name = "Leave_Room"
    command_description = "离开房间"
    command_pattern = r"^.离开房间$"
    
    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """处理离开房间命令"""
        user_id = str(self.message.message_info.user_info.user_id)
        user_id_int = int(user_id)
        
        # 查找玩家所在的房间
        for room_id, room in rooms.items():
            for player in room.players:
                if player.user_id == user_id_int:
                    # 返还剩余筹码对应金币
                    rate = getattr(room, 'rate', 1)
                    if player.chips > 0:
                        gold_back = player.chips * rate
                        from src.plugin_system.apis import person_api
                        await person_api.add_coins(self.message.message_info.platform, str(player.user_id), gold_back)
                        await self.send_text(f"返还剩余筹码：{player.chips}，已返还 {gold_back} 金币。")
                    leave_room(room, user_id_int)
                    await self.send_text(f"{player.username} 已离开房间 {room_id}。")
                    return True, f"{player.username} 离开房间 {room_id} 成功", True
        await self.send_text("您不在任何房间中，无法离开。")
        return False, "用户不在任何房间中", False
    
# .下一轮 命令（推进流程/发公共牌/结算）
class NextRoundCommand(BaseCommand):
    command_name = "Next_Round"
    command_description = "推进到下一轮"
    command_pattern = r"^.下一轮$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        user_id = str(self.message.message_info.user_info.user_id)
        user_id_int = int(user_id)
        # 查找玩家所在的房间
        for room in rooms.values():
            for player in room.players:
                if player.user_id == user_id_int:
                    # 推进流程
                    prev_stage = room.round_stage
                    next_betting_round(room)
                    if room.round_stage != prev_stage:
                        await self.send_text(f"房间{room.room_id} 进入阶段：{room.round_stage}，公共牌：{' '.join(room.community_cards)}")
                        if room.round_stage == "showdown":
                            # 优化结算，展示胜者手牌和牌型
                            result = settle_game(room)
                            if result and isinstance(result, tuple) and len(result) == 3:
                                winner, best_hand, hand_name = result
                            else:
                                winner, best_hand, hand_name = result, None, None
                            if winner:
                                hand_str = ', '.join(best_hand) if best_hand else '未知'
                                hand_name_str = hand_name if hand_name else '未知牌型'
                                await self.send_text(f"本局胜者：{winner.username}\n手牌：{hand_str}\n牌型：{hand_name_str}\n获得底池{room.pot}筹码！")
                            else:
                                await self.send_text("无人获胜。")
                            if winner:
                                # 结算金币
                                rate = getattr(room, 'rate', 1)
                                gold_win = room.pot * rate
                                await person_api.add_coins(self.message.message_info.platform, str(winner.user_id), gold_win)
                                await self.send_text(f"🎉🎉 本局胜者：{winner.username}，获得底池 {room.pot} 筹码（返还 {gold_win} 金币）！🎉🎉")
                            # 补充所有玩家筹码到1000，扣除金币
                            for p in room.players:
                                if p.chips < 1000:
                                    need = 1000 - p.chips
                                    person = await person_api.get_person_by_platform_and_user_id(self.message.message_info.platform, str(p.user_id))
                                    gold = getattr(person, 'coins', 0) if person else 0
                                    rate = getattr(room, 'rate', 1)
                                    gold_need = need * rate
                                    if gold > 0:
                                        real_add = min(need, gold // rate)
                                        if real_add > 0:
                                            await person_api.add_coins(self.message.message_info.platform, str(p.user_id), -real_add * rate)
                                            p.chips += real_add
                                            await send_message(p.user_id, f"[系统] 您的筹码已自动补充至 {p.chips}，扣除 {real_add * rate} 金币。")
                                        else:
                                            await send_message(p.user_id, f"[系统] 金币不足，无法补充筹码。当前筹码：{p.chips}")
                                    else:
                                        await send_message(p.user_id, f"[系统] 金币不足，无法补充筹码。当前筹码：{p.chips}")
                    else:
                        await self.send_text("当前无法推进到下一轮。")
                    return True, f"房间{room.room_id} 阶段推进", True
        await self.send_text("您不在任何房间中，无法操作。")
        return False, "用户不在任何房间中", False
                
# .下注 命令
class BetCommand(BaseCommand):
    command_name = "Bet"
    command_description = "下注"
    command_pattern = r"^.下注 (?P<amount>\d+)$"
    
    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """处理下注命令"""
        amount_str = self.matched_groups.get('amount')
        if not amount_str:
            await self.send_text("命令格式错误，请使用 .下注 <金额>")
            return False, "命令格式错误", False
        amount = int(amount_str)
        
        user_id = str(self.message.message_info.user_info.user_id)
        user_id_int = int(user_id)
        
        # 查找玩家所在的房间
        for room in rooms.values():
            for player in room.players:
                if player.user_id == user_id_int:
                    # 玩家找到，执行下注操作
                    if place_bet(room, user_id_int, amount):
                        await self.send_text(f"{player.username} 成功下注 {amount} 筹码。")
                        return True, f"{player.username} 下注 {amount} 成功", True
                    else:
                        await self.send_text(f"{player.username} 下注失败，筹码不足。")
                        return False, f"{player.username} 下注失败", False
        
        await self.send_text("您不在任何房间中，无法下注。")
        return False, "用户不在任何房间中", False


# .弃牌 命令
class FoldCommand(BaseCommand):
    command_name = "Fold"
    command_description = "弃牌"
    command_pattern = r"^.弃牌$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        user_id = str(self.message.message_info.user_info.user_id)
        user_id_int = int(user_id)
        for room in rooms.values():
            for player in room.players:
                if player.user_id == user_id_int:
                    if fold(room, user_id_int):
                        await self.send_text(f"{player.username} 已弃牌。")
                        return True, f"{player.username} 弃牌成功", True
                    else:
                        await self.send_text(f"{player.username} 弃牌失败。")
                        return False, f"{player.username} 弃牌失败", False
        await self.send_text("您不在任何房间中，无法弃牌。")
        return False, "用户不在任何房间中", False