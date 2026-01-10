from ..core import user_data
from ..core import logCore
from src.plugin_system.apis import person_api
from src.plugin_system.base.base_command import BaseCommand
from typing import Dict, Optional, Tuple, List
import math
from . import TexasHoldemCore
from ..core import userCore


def _mention_next(room: TexasHoldemCore.Room) -> str:
    if room.current_player_index is None or room.current_player_index >= len(room.players):
        return "@所有人"
    return f"@{room.players[room.current_player_index].username}"


def _mention_user(name: str) -> str:
    return f"@{name}"


def _pretty_card(card: str) -> str:
    if not card:
        return card
    suit = card[-1]
    rank = card[:-1]
    suit_map = {"H": "♥", "D": "♦", "C": "♣", "S": "♠"}
    return f"{suit_map.get(suit, suit)}{rank}"


def _pretty_cards(cards) -> str:
    return " ".join(_pretty_card(c) for c in cards)


def _calc_buy_cost(chips: int, rate: int) -> Tuple[int, int, int]:
    base = chips * rate
    fee = math.ceil(base * 0.1)
    return base, fee, base + fee


async def _refill_chips(room: TexasHoldemCore.Room, platform: str) -> List[str]:
    """在一手结束后为不足初始筹码的玩家自动补充。"""
    refill_lines: List[str] = []
    for p in room.players:
        if p.chips >= room.initial_chips:
            continue
        need = room.initial_chips - p.chips
        refill_person_id = person_api.get_person_id(platform, str(p.user_id))
        if not refill_person_id:
            refill_lines.append(f"[系统] 玩家 {p.username} 账户未找到，无法补充筹码。当前筹码：{p.chips}")
            continue
        user = userCore.get_user_info(refill_person_id)
        if not user:
            refill_lines.append(f"[系统] 玩家 {p.username} 账户数据缺失，无法补充筹码。当前筹码：{p.chips}")
            continue
        gold = user.coins
        if gold <= 0:
            refill_lines.append(f"[系统] 玩家 {p.username} 金币不足，无法补充筹码。当前筹码：{p.chips}")
            continue
        rate = room.rate
        real_add = min(need, gold // rate)
        if real_add > 0:
            userCore.update_coins_to_user(refill_person_id, -real_add * rate)
            p.chips += real_add
            refill_lines.append(f"[系统] 玩家 {p.username} 补充筹码 {real_add}（消耗 {real_add * rate} 金币），当前筹码：{p.chips}")
        else:
            refill_lines.append(f"[系统] 玩家 {p.username} 金币不足，无法补充筹码。当前筹码：{p.chips}")
    return refill_lines


async def _advance_round(room: TexasHoldemCore.Room, platform: str, send_text, *, manual: bool) -> Tuple[bool, str]:
    """推进到下一轮或完成摊牌，复用 .下一轮 逻辑。"""
    pot_snapshot = room.pot

    # 单人存活直接获胜
    winner = TexasHoldemCore._check_single_player_win(room)
    if winner:
        hand_line = f"胜者手牌：{_pretty_cards(winner.hand)}" if winner.hand else "胜者手牌：未发牌"
        refill_lines = await _refill_chips(room, platform)
        messages = [
            f"{_mention_next(room)} 房间{room.room_id} 只剩 {winner.username}，底池 {pot_snapshot} 筹码直接获胜！",
            hand_line,
        ]
        if refill_lines:
            messages.extend(refill_lines)
        messages.append("牌局已重置，使用 .开局 可开始下一手。")
        await send_text("\n".join(messages))
        TexasHoldemCore.reset_hand_state(room)
        return True, "单人存活自动结算"

    # 下注轮未结算
    if not TexasHoldemCore._is_betting_round_settled(room):
        if manual:
            await send_text(f"{_mention_next(room)} 还有玩家未跟注或未行动，暂不能进入下一轮。")
        return False, "下注轮未结算"

    result = TexasHoldemCore.next_betting_round(room)
    if result is False:
        if manual:
            await send_text(f"{_mention_next(room)} 当前无法推进到下一轮。")
        return False, "无法推进"

    # 摊牌结算
    if room.round_stage == "showdown":
        messages = []
        if result:
            if isinstance(result, list):
                for idx, item in enumerate(result, start=1):
                    winner_item, best_hand, hand_name, pot_won = item[:4]
                    tied_names = item[4] if len(item) >= 5 else [winner_item.username]
                    share = pot_won // len(tied_names)
                    remainder = pot_won % len(tied_names)
                    remainder_hint = f"，其中前 {remainder} 人多得 1" if remainder else ""
                    split_hint = "平分" if len(tied_names) > 1 else "获得"
                    messages.append(
                        f"池{idx}: {', '.join(tied_names)} {split_hint} {pot_won} 筹码（每人 {share}{remainder_hint}），"
                        f"牌型 {hand_name}，手牌 {_pretty_cards(best_hand)}"
                    )
            else:
                winner_player, best_hand, hand_name = result[:3]
                pot_won = result[3] if len(result) >= 4 else pot_snapshot
                messages.append(
                    f"{_mention_next(room)} 本局胜者：{winner_player.username}\n"
                    f"手牌：{_pretty_cards(best_hand)}\n"
                    f"牌型：{hand_name}\n"
                    f"获得底池 {pot_won} 筹码"
                )
        else:
            messages.append(f"{_mention_next(room)} 无人获胜。")

        # 摊牌后自动补充筹码
        refill_lines = await _refill_chips(room, platform)
        if refill_lines:
            messages.extend(refill_lines)
        TexasHoldemCore.reset_hand_state(room)
        messages.append("牌局已重置至等待状态，使用 .开局 可开始下一手。")
        await send_text("\n".join(messages))
        return True, "摊牌结算完成"

    await send_text(
        f"{_mention_next(room)} 房间{room.room_id} 进入阶段：{room.round_stage} ,公共牌：\n{_pretty_cards(room.community_cards)}\n当前底池：{room.pot}"
    )
    return True, f"房间{room.room_id} 阶段推进"


async def _auto_advance_if_settled(room: TexasHoldemCore.Room, platform: str, send_text) -> None:
    """在下注轮结算后自动推进，无提示信息。"""
    while TexasHoldemCore._is_betting_round_settled(room):
        prev_stage = room.round_stage
        advanced, _ = await _advance_round(room, platform, send_text, manual=False)
        if not advanced:
            break
        if room.round_stage in ("waiting", "showdown"):
            break
        if room.round_stage == prev_stage:
            break

# 全局变量，存储房间数据
rooms: Dict[int, TexasHoldemCore.Room] = {}
# .德州扑克帮助
class TexasHoldemHelpCommand(BaseCommand):
    command_name = "Texas_Holdem_Help"
    command_description = "德州扑克"
    command_pattern = r"^.德州扑克$"
    
    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """处理德州扑克帮助命令"""
        help_text = (
            "德州扑克指令列表：\n"
            ".创建房间 [倍率] - (仅私聊有效)创建一个新的德州扑克房间，可选倍率参数（默认为1）\n"
            ".加入房间 <房间ID> - (仅私聊有效)加入指定ID的德州扑克房间\n"
            ".离开房间 - 离开当前所在的德州扑克房间\n"
            ".开局 - 手动开始游戏\n"
            ".下注 <金额> - 在当前轮次下注指定金额筹码\n"
            ".跟注 - 跟随当前最高下注金额\n"
            ".加注 <金额> - 在当前最高下注基础上加注指定金额筹码\n"
            ".过牌 - 当前无人下注时选择过牌\n"
            ".allin - 将所有筹码全部压上\n"
            ".弃牌 - 弃掉当前手牌，退出本局游戏\n"
            ".购买筹码 <手数> - 等待阶段按房间倍率购买筹码（1手=100筹码，含10%手续费）"
        )
        await self.send_text(help_text)
        return True, "显示德州扑克帮助", True

# .创建房间 命令
class CreateRoomCommand(BaseCommand):
    command_name = "Create_Room"
    command_description = "创建房间"
    command_pattern = r"^.创建房间(?: (?P<rate>\d+))?$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """处理创建房间命令，支持倍率参数"""
        # 限定创建房间只能在私聊中进行
        group_info = getattr(self.message.message_info, 'group_info', None)
        if group_info and getattr(group_info, 'group_id', None):
            await self.send_text("德州扑克房间仅支持私聊创建（含倍率），请在私聊窗口使用该命令。")
            return False, "群聊不支持创建房间（含倍率）", False
        
        """处理用户查询个人信息命令"""        
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

        username = await person_api.get_person_value(person_id, "nickname", user_id)
        rate_str = self.matched_groups.get('rate')
        rate = int(rate_str) if rate_str else 1
        if rate < 1:
            await self.send_text("倍率必须为正整数！")
            return False, "倍率无效", False
            # 仅参数校验和调用核心方法

        
        success, msg, room = TexasHoldemCore.create_room_and_join(rooms, user_id, username, rate, person_id)
        await self.send_text(msg)
        return success, msg, success
        
# .加入房间 <房间ID> 命令
class JoinRoomCommand(BaseCommand):
    command_name = "Join_Room"
    command_description = "加入房间"
    command_pattern = r"^.加入房间 (?P<room_id>\d+)$"
    
    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        # 限定加入房间只能在私聊中进行
        group_info = getattr(self.message.message_info, 'group_info', None)
        if group_info and getattr(group_info, 'group_id', None):
            await self.send_text("德州扑克房间仅支持私聊加入，请在私聊窗口使用该命令。")
            return False, "群聊不支持加入房间", False
        
        """处理用户查询个人信息命令"""
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

        """处理加入房间命令"""
        room_id_str = self.matched_groups.get('room_id')
        if not room_id_str:
            await self.send_text("命令格式错误，请使用 .加入房间 <房间ID>")
            return False, "命令格式错误", False
        room_id = int(room_id_str)

        # 检查是否已在某个房间，避免重复加入或跨房间加入
        occupied = TexasHoldemCore.find_player_room(rooms, user_id)
        if occupied:
            occupied_room_id, _, _ = occupied
            if occupied_room_id == room_id:
                await self.send_text(f"您已在房间 {room_id}，无需重复加入。")
                return False, "已在目标房间", False
            await self.send_text(f"您已在房间 {occupied_room_id}，请先离开后再加入新的房间。")
            return False, "已在其他房间", False

        # 检查房间是否存在
        if room_id not in rooms:
            await self.send_text(f"房间 {room_id} 不存在。")
            return False, f"房间 {room_id} 不存在", False
        
        room = rooms[room_id]
        
        # 获取玩家昵称
        username = await person_api.get_person_value(person_id, "nickname", user_id)
        
        # 创建玩家对象，初始筹码为房间设定
        user = userCore.get_user_info(person_id)
        rate = getattr(room, 'rate', 1)
        chips_needed = room.initial_chips * rate
        if user.coins < chips_needed:
            await self.send_text(f"金币不足，加入本房间需 {chips_needed} 金币（倍率{rate}，初始筹码{room.initial_chips}）。")
            return False, "金币不足", False

        # 先检查座位，再扣金币，防止满员时白扣金币
        if len(room.players) >= room.max_players:
            await self.send_text(f"房间 {room_id} 已满，无法加入。")
            return False, f"房间 {room_id} 已满", False

        # 扣金币并确保失败时返还
        userCore.update_coins_to_user(person_id, -chips_needed)
        try:
            player = TexasHoldemCore.Player(int(user_id), username, room.initial_chips)
            if not TexasHoldemCore.join_room(room, player):
                # 理论上不会走到这里，兜底返还
                userCore.update_coins_to_user(person_id, chips_needed)
                await self.send_text(f"房间 {room_id} 已满，无法加入。")
                return False, f"房间 {room_id} 已满", False
        except Exception as exc:  # 防止意外异常导致金币丢失
            userCore.update_coins_to_user(person_id, chips_needed)
            logCore.log_write(f"加入房间异常，已返还金币: {exc}")
            await self.send_text("加入房间失败，金币已返还，请稍后重试。")
            return False, "加入房间异常", False

        await self.send_text(
            f"--------------------\n{username} 成功加入房间 {room_id}！\n当前房间人数：{len(room.players)}\n已花费 {chips_needed} 金币获取筹码 {room.initial_chips}\n--------------------"
        )
        # 自动开局：仅当房间人数达到最大人数时自动开局（最大人数为room.max_players）
        if hasattr(room, 'max_players') and len(room.players) >= room.max_players and room.round_stage == "waiting":
            TexasHoldemCore.start_new_hand(room)
            sb = next((p for p in room.players if p.is_small_blind), None)
            bb = next((p for p in room.players if p.is_big_blind), None)
            sb_line = f"小盲：{sb.username} 投注 {sb.current_bet}" if sb else "小盲：-"
            bb_line = f"大盲：{bb.username} 投注 {bb.current_bet}" if bb else "大盲：-"
            await self.send_text(
                f"{_mention_next(room)} 房间 {room_id} 游戏开始！\n"
                f"庄家：{room.players[room.dealer_index].username}\n"
                f"{sb_line}\n{bb_line}\n"
                f"当前底池：{room.pot}\n当前轮次：{room.round_stage}"
            )
            # 私聊每位玩家手牌
            for p in room.players:
                hand_str = _pretty_cards(p.hand)
                logCore.log_write(f"[JoinRoomCommand] 给玩家 {p.user_id} 发送手牌私聊: {hand_str}")
                send_result = await TexasHoldemCore.send_private_message(str(p.user_id), f"您的手牌是: {hand_str}", platform)
                logCore.log_write(f"[JoinRoomCommand] send_private_message 返回: {send_result}")
        return True, f"{username} 加入房间 {room_id} 成功", True

# .开局 命令
class StartGameCommand(BaseCommand):
    command_name = "Start_Game"
    command_description = "手动开局"
    command_pattern = r"^.开局$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:

        #检查用户是否注册
        platform = self.message.message_info.platform
        user_id = str(self.message.message_info.user_info.user_id)
        person_id = person_api.get_person_id(platform, user_id)
        if not userCore.is_user_registered(person_id):
            await self.send_text("你还没有注册，请先签到注册！")
            return False, "用户未注册", False
        # 查找玩家所在的房间并开局
        for room_id, room in rooms.items():
            for player in room.players:
                logCore.log_write(f"[StartGameCommand] 检查玩家 {player.user_id} 是否为命令发起者 {user_id}，{player.user_id == user_id}")
                if player.user_id == int(user_id):
                    if room.round_stage != "waiting":
                        # 容错：若上一手已结束但状态未复位，则自动复位
                        hands_cleared = all(len(p.hand) == 0 for p in room.players)
                        no_pot = room.pot == 0
                        if room.round_stage == "showdown" or (hands_cleared and no_pot):
                            TexasHoldemCore.reset_hand_state(room)
                        else:
                            return False, "房间已在游戏中", False
                    if len(room.players) < 2:
                        await self.send_text("房间人数不足2人，无法开局。"); return False, "人数不足", False
                    TexasHoldemCore.start_new_hand(room)
                    sb = next((p for p in room.players if p.is_small_blind), None)
                    bb = next((p for p in room.players if p.is_big_blind), None)
                    sb_line = f"小盲：{sb.username} 投注 {sb.current_bet}" if sb else "小盲：-"
                    bb_line = f"大盲：{bb.username} 投注 {bb.current_bet}" if bb else "大盲：-"
                    await self.send_text(
                        f"{_mention_next(room)} 房间 {room_id}\n 牌局开始！\n"
                        f"庄家：{room.players[room.dealer_index].username}\n"
                        f"{sb_line}\n{bb_line}\n"
                        f"当前底池：{room.pot}\n当前轮次：{room.round_stage}\n"
                        #当前行动玩家
                        f"当前行动玩家：{_mention_next(room)}"
                    )
                    for p in room.players:
                        hand_str = _pretty_cards(p.hand)
                        logCore.log_write(f"[StartGameCommand] 给玩家 {p.user_id} 发送手牌私聊: {hand_str}")
                        send_result = await TexasHoldemCore.send_private_message(str(p.user_id), f"您的手牌是: {hand_str}", platform)
                        logCore.log_write(f"[StartGameCommand] send_private_message 返回: {send_result}")
                    return True, "手动开局成功", True
        await self.send_text("您不在任何房间中，无法开局。")
        return False, "用户不在任何房间中", False
        
# .查看房间 命令
class ViewRoomCommand(BaseCommand):
    command_name = "View_Room"
    command_description = "查看房间信息"
    command_pattern = r"^.查看房间$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """处理查看房间信息命令"""
        #获取玩家id
        platform = self.message.message_info.platform
        user_id = str(self.message.message_info.user_info.user_id)
        person_id = person_api.get_person_id(platform, user_id)
        if not userCore.is_user_registered(person_id):
            await self.send_text("你还没有注册，请先签到注册！")
            return False, "用户未注册", False
        #查找玩家所在的房间
        located = TexasHoldemCore.find_player_room(rooms, user_id)
        if located:
            room_id, room, player = located
            player_lines = []
            for p in room.players:
                status = "（已弃牌）" if p.has_folded else ""
                player_lines.append(f"- {p.username} 筹码: {p.chips} {status}")
            player_list_str = "\n".join(player_lines)
            await self.send_text(
                f"房间 {room_id} 信息：\n"
                f"当前阶段：{room.round_stage}\n"
                f"底池：{room.pot}\n"
                f"玩家列表：\n{player_list_str}\n"
                f"当前行动玩家：{_mention_next(room)}"
            )
            return True, "查看房间信息成功", True
        await self.send_text("您不在任何房间中，无法查看房间信息。")
        return False, "用户不在任何房间中", False


class BuyChipsCommand(BaseCommand):
    command_name = "Buy_Chips"
    command_description = "购买筹码"
    command_pattern = r"^.购买筹码 (?P<hands>\d+)$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        platform = self.message.message_info.platform
        user_id = str(self.message.message_info.user_info.user_id)
        person_id = person_api.get_person_id(platform, user_id)
        if not userCore.is_user_registered(person_id):
            await self.send_text("你还没有注册，请先签到注册！")
            return False, "用户未注册", False

        hands_str = self.matched_groups.get("hands")
        if not hands_str:
            await self.send_text("命令格式错误，请使用 .购买筹码 <手数>（1手=100筹码）。")
            return False, "命令格式错误", False
        hands = int(hands_str)
        if hands < 1:
            await self.send_text("最少购买 1 手（100 筹码）。")
            return False, "购买手数过低", False

        located = TexasHoldemCore.find_player_room(rooms, user_id)
        if not located:
            await self.send_text(f"@{user_id} 您不在任何房间中，无法购买筹码。")
            return False, "用户不在任何房间中", False

        room_id, room, player = located
        if room.round_stage != "waiting":
            await self.send_text(f"房间 {room_id} 当前牌局进行中，仅等待/准备阶段可购买筹码。")
            return False, "非等待阶段", False

        chips_to_buy = hands * 100
        base_cost, fee, total_cost = _calc_buy_cost(chips_to_buy, room.rate)
        user = userCore.get_user_info(person_id)
        if not user:
            await self.send_text("用户账户异常，购买失败。")
            return False, "账户缺失", False
        if user.coins < total_cost:
            await self.send_text(
                f"金币不足，购买 {hands} 手（{chips_to_buy} 筹码）需 {total_cost} 金币，"
                f"其中手续费 {fee} 金币（10%）。当前金币：{user.coins}。"
            )
            return False, "金币不足", False

        userCore.update_coins_to_user(person_id, -total_cost)
        player.chips += chips_to_buy
        await self.send_text(
            f"已购买 {hands} 手筹码（{chips_to_buy} 筹码）。\n"
            f"扣除 {base_cost} 金币 + 手续费 {fee}（10%）= {total_cost} 金币。\n"
            f"房间倍率：{room.rate}，当前筹码：{player.chips}。"
        )
        return True, "购买筹码成功", True



# .离开房间 命令
class LeaveRoomCommand(BaseCommand):
    command_name = "Leave_Room"
    command_description = "离开房间"
    command_pattern = r"^.离开房间$"
    
    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """处理离开房间命令，统一 person_id 逻辑"""
        platform = self.message.message_info.platform
        user_id = str(self.message.message_info.user_info.user_id)
        person_id = person_api.get_person_id(platform, user_id)
        if not userCore.is_user_registered(person_id):
            await self.send_text("你还没有注册，请先签到注册！")
            return False, "用户未注册", False
        # 查找玩家所在的房间
        for room_id, room in rooms.items():
            for player in room.players:
                if player.user_id == int(user_id):
                    auto_fold_msg = ""
                    if room.round_stage not in ("waiting", "showdown"):
                        TexasHoldemCore.fold(room, int(user_id))
                        auto_fold_msg = "（牌局中已自动为你弃牌，已投入的筹码不予退还）"
                    # 返还剩余筹码对应金币
                    rate = getattr(room, 'rate', 1)
                    if player.chips > 0:
                        gold_back = player.chips * rate
                        userCore.update_coins_to_user(person_id, gold_back)
                        leave_msgs = [f"返还剩余筹码：{player.chips}，已返还 {gold_back} 金币。{auto_fold_msg}"]
                    else:
                        leave_msgs = [f"{auto_fold_msg}"] if auto_fold_msg else []
                    TexasHoldemCore.leave_room(room, int(user_id))
                    leave_msgs.append(f"{player.username} 已离开房间 {room_id}。")
                    if leave_msgs:
                        await self.send_text("\n".join(leave_msgs))
                    return True, f"{player.username} 离开房间 {room_id} 成功", True
        await self.send_text(f"@{user_id} 您不在任何房间中，无法离开。")
        return False, "用户不在任何房间中", False
    
# .下一轮 命令（推进流程/发公共牌/结算）
class NextRoundCommand(BaseCommand):
    command_name = "Next_Round"
    command_description = "推进到下一轮"
    command_pattern = r"^.下一轮$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        platform = self.message.message_info.platform
        user_id = str(self.message.message_info.user_info.user_id)
        person_id = person_api.get_person_id(platform, user_id)
        if not userCore.is_user_registered(person_id):
            await self.send_text("你还没有注册，请先签到注册！")
            return False, "用户未注册", False
        # 查找玩家所在的房间
        located = TexasHoldemCore.find_player_room(rooms, user_id)
        if located:
            _, room, _ = located
            success, reason = await _advance_round(room, platform, self.send_text, manual=True)
            return success, reason, success
        await self.send_text(f"@{user_id} 您不在任何房间中，无法操作。")
        return False, "用户不在任何房间中", False
                
# .过牌 命令
class CheckCommand(BaseCommand):
    command_name = "Check"
    command_description = "过牌"
    command_pattern = r"^.过牌$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        platform = self.message.message_info.platform
        user_id = str(self.message.message_info.user_info.user_id)
        person_id = person_api.get_person_id(platform, user_id)
        if not userCore.is_user_registered(person_id):
            await self.send_text("你还没有注册，请先签到注册！")
            return False, "用户未注册", False
        located = TexasHoldemCore.find_player_room(rooms, user_id)
        if not located:
            await self.send_text(f"@{user_id} 您不在任何房间中，无法过牌。")
            return False, "用户不在任何房间中", False
        _, room, player = located
        if room.round_stage in ("waiting", "showdown"):
            await self.send_text(f"{_mention_user(player.username)} \n当前不在有效的下注阶段。")
            return False, "阶段错误", False
        if not TexasHoldemCore.is_player_turn(room, int(user_id)):
            actor = room.players[room.current_player_index].username if room.current_player_index is not None else "未知玩家"
            await self.send_text(f"{_mention_user(player.username)} \n还未轮到你行动，当前应行动玩家：{actor}")
            return False, "非行动顺序", False
        need_call = max(room.current_bet - player.current_bet, 0)
        if need_call > 0:
            await self.send_text(f"{_mention_user(player.username)} 当前有下注需至少跟注 {need_call}，无法过牌。")
            return False, "无法过牌", False
        TexasHoldemCore.mark_player_acted(room, int(user_id))
        TexasHoldemCore.move_to_next_player(room)
        settle_tip = "本轮下注已结算" if TexasHoldemCore._is_betting_round_settled(room) else ""
        next_player = room.players[room.current_player_index] if room.current_player_index is not None else None
        lines = [f"{_mention_next(room)} {player.username} 选择过牌。"]
        if settle_tip:
            lines.append(settle_tip)
        await self.send_text("\n".join(lines))
        await _auto_advance_if_settled(room, platform, self.send_text)
        return True, f"{player.username} 过牌", True
                
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
        platform = self.message.message_info.platform
        user_id = str(self.message.message_info.user_info.user_id)
        person_id = person_api.get_person_id(platform, user_id)
        if not userCore.is_user_registered(person_id):
            await self.send_text("你还没有注册，请先签到注册！")
            return False, "用户未注册", False
        located = TexasHoldemCore.find_player_room(rooms, user_id)
        if not located:
            await self.send_text(f"@{user_id} 您不在任何房间中，无法下注。")
            return False, "用户不在任何房间中", False

        _, room, player = located
        if room.round_stage in ("waiting", "showdown"):
            await self.send_text(f"{_mention_user(player.username)} \n当前不在有效的下注阶段。")
            return False, "阶段错误", False
        if not TexasHoldemCore.is_player_turn(room, int(user_id)):
            actor = room.players[room.current_player_index].username if room.current_player_index is not None else "未知玩家"
            await self.send_text(f"{_mention_user(player.username)} \n还未轮到你行动，当前应行动玩家：{actor}")
            return False, "非行动顺序", False
        if room.current_bet > 0 and player.current_bet != room.current_bet:
            await self.send_text(f"{_mention_user(player.username)} \n当前已有下注，请使用 .跟注 或 .加注。")
            return False, "已有下注", False
        if amount < room.big_blind:
            await self.send_text(f"{_mention_user(player.username)} \n下注额不能低于大盲注：{room.big_blind}")
            return False, "下注过低", False
        if player.chips < amount:
            await self.send_text(f"{_mention_user(player.username)} \n筹码不足，无法下注。")
            return False, "筹码不足", False
        TexasHoldemCore.place_bet(room, int(user_id), amount)
        room.current_bet = max(room.current_bet, player.current_bet)
        room.last_raiser_index = room.players.index(player)
        TexasHoldemCore.move_to_next_player(room)
        settle_tip = "本轮下注已结算" if TexasHoldemCore._is_betting_round_settled(room) else ""
        next_player = room.players[room.current_player_index] if room.current_player_index is not None else None
        lines = [f"{_mention_next(room)} {player.username} 下注 {amount} 筹码。当前底池：{room.pot}"]
        if settle_tip:
            lines.append(settle_tip)
        await self.send_text("\n".join(lines))
        await _auto_advance_if_settled(room, platform, self.send_text)
        return True, f"{player.username} 下注 {amount}", True


# .弃牌 命令
class FoldCommand(BaseCommand):
    command_name = "Fold"
    command_description = "弃牌"
    command_pattern = r"^.弃牌$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """处理弃牌命令，统一 person_id 逻辑"""
        platform = self.message.message_info.platform
        user_id = str(self.message.message_info.user_info.user_id)
        person_id = person_api.get_person_id(platform, user_id)
        if not userCore.is_user_registered(person_id):
            await self.send_text("你还没有注册，请先签到注册！")
            return False, "用户未注册", False
        located = TexasHoldemCore.find_player_room(rooms, user_id)
        if not located:
            await self.send_text(f"@{user_id} 您不在任何房间中，无法弃牌。")
            return False, "用户不在任何房间中", False
        _, room, player = located
        if room.round_stage in ("waiting", "showdown"):
            await self.send_text(f"{_mention_user(player.username)} \n当前不在游戏中，无需弃牌。")
            return False, "阶段错误", False
        TexasHoldemCore.fold(room, int(user_id))
        pot_snapshot = room.pot
        winner = TexasHoldemCore._check_single_player_win(room)
        if winner:
            message_lines = [f"{_mention_next(room)} \n{player.username} 已弃牌。"]
            hand_line = f"胜者手牌：{_pretty_cards(winner.hand)}" if winner.hand else "胜者手牌：未发牌"
            message_lines.append(f"仅剩 {winner.username}，直接赢得底池 {pot_snapshot} 筹码。\n{hand_line}")
            refill_lines = await _refill_chips(room, platform)
            if refill_lines:
                message_lines.extend(refill_lines)
            TexasHoldemCore.reset_hand_state(room)
            message_lines.append("牌局已重置，使用 .开局 可开始下一手。")
        else:
            TexasHoldemCore.move_to_next_player(room)
            message_lines = [f"{_mention_next(room)} \n{player.username} 已弃牌。"]
        next_player = room.players[room.current_player_index] if room.current_player_index is not None else None
        await self.send_text("\n".join(message_lines))
        await _auto_advance_if_settled(room, platform, self.send_text)
        return True, f"{player.username} 弃牌成功", True
    

# .跟注 命令
class CallCommand(BaseCommand):
    command_name = "Call"
    command_description = "跟注"
    command_pattern = r"^.跟注$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        platform = self.message.message_info.platform
        user_id = str(self.message.message_info.user_info.user_id)
        person_id = person_api.get_person_id(platform, user_id)
        if not userCore.is_user_registered(person_id):
            await self.send_text("你还没有注册，请先签到注册！")
            return False, "用户未注册", False
        located = TexasHoldemCore.find_player_room(rooms, user_id)
        if not located:
            await self.send_text(f"@{user_id} 您不在任何房间中，无法跟注。")
            return False, "用户不在任何房间中", False
        _, room, player = located
        if room.round_stage in ("waiting", "showdown"):
            await self.send_text(f"{_mention_user(player.username)} \n当前不在有效的下注阶段。")
            return False, "阶段错误", False
        # 若本轮已结算但未推进，先自动推进，避免重复跟注循环
        if TexasHoldemCore._is_betting_round_settled(room):
            await _advance_round(room, platform, self.send_text, manual=False)
            return False, "本轮已结算，已自动推进", False
        if not TexasHoldemCore.is_player_turn(room, int(user_id)):
            actor = room.players[room.current_player_index].username if room.current_player_index is not None else "未知玩家"
            await self.send_text(f"{_mention_user(player.username)} \n还未轮到你行动，当前应行动玩家：{actor}")
            return False, "非行动顺序", False
        call_amount = room.current_bet - player.current_bet
        if call_amount < 0:
            call_amount = 0
        pay = min(call_amount, player.chips)
        action_line = ""
        if pay == 0 and room.current_bet == 0:
            action_line = f"{player.username} 过牌。"
            TexasHoldemCore.mark_player_acted(room, int(user_id))
        elif pay == 0:
            action_line = f"{player.username} 已跟注到当前 {room.current_bet}，无需额外支付。"
            TexasHoldemCore.mark_player_acted(room, int(user_id))
        else:
            TexasHoldemCore.place_bet(room, int(user_id), pay)
            action_line = f"{player.username} 跟注 {pay} 筹码。\n当前底池：{room.pot}"
        TexasHoldemCore.move_to_next_player(room)
        tip = "本轮下注已结算" if TexasHoldemCore._is_betting_round_settled(room) else ""
        next_player = room.players[room.current_player_index] if room.current_player_index is not None else None
        lines = [f"{_mention_next(room)} \n{action_line}"]
        if tip:
            lines.append(tip)
        await self.send_text("\n".join(lines))
        await _auto_advance_if_settled(room, platform, self.send_text)
        return True, f"{player.username} 跟注 {pay}", True

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
        platform = self.message.message_info.platform
        user_id = str(self.message.message_info.user_info.user_id)
        person_id = person_api.get_person_id(platform, user_id)
        if not userCore.is_user_registered(person_id):
            await self.send_text("你还没有注册，请先签到注册！")
            return False, "用户未注册", False
        located = TexasHoldemCore.find_player_room(rooms, user_id)
        if not located:
            await self.send_text(f"@{user_id} 您不在任何房间中，无法加注。")
            return False, "用户不在任何房间中", False
        _, room, player = located
        if room.round_stage in ("waiting", "showdown"):
            await self.send_text(f"{_mention_user(player.username)} 当前不在有效的下注阶段。")
            return False, "阶段错误", False
        if not TexasHoldemCore.is_player_turn(room, int(user_id)):
            actor = room.players[room.current_player_index].username if room.current_player_index is not None else "未知玩家"
            await self.send_text(f"{_mention_user(player.username)} \n还未轮到你行动，当前应行动玩家：{actor}")
            return False, "非行动顺序", False
        if amount <= room.current_bet:
            await self.send_text(f"{_mention_user(player.username)} \n加注额必须大于当前下注额，若仅跟注请使用 .跟注。")
            return False, "加注过低", False
        raise_size = amount - room.current_bet
        if raise_size < room.big_blind:
            min_total = room.current_bet + room.big_blind
            await self.send_text(
                f"{_mention_user(player.username)} \n当前最高注：{room.current_bet}，加注幅度至少为大盲注 {room.big_blind}，\n"
                f"最少加注为 {min_total}。"
            )
            return False, "加注幅度不足", False
        need_pay = amount - player.current_bet
        if need_pay > player.chips:
            await self.send_text(f"{_mention_user(player.username)} \n筹码不足，无法完成该加注。")
            return False, "筹码不足", False
        TexasHoldemCore.place_bet(room, int(user_id), need_pay)
        room.current_bet = amount
        room.last_raiser_index = room.players.index(player)
        TexasHoldemCore.move_to_next_player(room)
        next_player = room.players[room.current_player_index] if room.current_player_index is not None else None
        await self.send_text(
            f"{_mention_next(room)} \n{player.username} 加注到 {amount} 筹码。\n当前底池：{room.pot}"
        )
        await _auto_advance_if_settled(room, platform, self.send_text)
        return True, f"{player.username} 加注 {amount}", True

# .allin 命令
class AllInCommand(BaseCommand):
    command_name = "All_In"
    command_description = "全下"
    command_pattern = r"^.allin$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        platform = self.message.message_info.platform
        user_id = str(self.message.message_info.user_info.user_id)
        person_id = person_api.get_person_id(platform, user_id)
        if not userCore.is_user_registered(person_id):
            await self.send_text("你还没有注册，请先签到注册！")
            return False, "用户未注册", False
        located = TexasHoldemCore.find_player_room(rooms, user_id)
        if not located:
            await self.send_text(f"@{user_id} \n您不在任何房间中，无法全下。")
            return False, "用户不在任何房间中", False
        _, room, player = located
        if room.round_stage in ("waiting", "showdown"):
            await self.send_text(f"{_mention_user(player.username)} \n当前不在有效的下注阶段。")
            return False, "阶段错误", False
        if not TexasHoldemCore.is_player_turn(room, int(user_id)):
            actor = room.players[room.current_player_index].username if room.current_player_index is not None else "未知玩家"
            await self.send_text(f"{_mention_user(player.username)} \n还未轮到你行动，当前应行动玩家：{actor}")
            return False, "非行动顺序", False
        if player.chips <= 0:
            await self.send_text(f"{_mention_user(player.username)} \n没有可用筹码，无法全下。")
            return False, "筹码不足", False
        prev_bet = room.current_bet
        allin_amount = player.chips
        TexasHoldemCore.place_bet(room, int(user_id), allin_amount)
        room.current_bet = max(room.current_bet, player.current_bet)
        if player.current_bet > prev_bet:
            room.last_raiser_index = room.players.index(player)
        TexasHoldemCore.mark_player_acted(room, int(user_id))
        TexasHoldemCore.move_to_next_player(room)
        settle_tip = "本轮下注已结算" if TexasHoldemCore._is_betting_round_settled(room) else ""
        next_player = room.players[room.current_player_index] if room.current_player_index is not None else None
        lines = [f"{_mention_next(room)} \n{player.username} 全下 {allin_amount} 筹码。\n当前底池：{room.pot}"]
        if settle_tip:
            lines.append(settle_tip)
        await self.send_text("\n".join(lines))
        await _auto_advance_if_settled(room, platform, self.send_text)
        return True, f"{player.username} 全下 {allin_amount}", True

# 检查是否有空房间，如果有就删除，每三十分钟执行一次
from ..core import timeCore
@timeCore.schedule_interval(minutes=30)
def cleanup_empty_rooms():
    empty_rooms = [room_id for room_id, room in rooms.items() if len(room.players) == 0]
    for room_id in empty_rooms:
        del rooms[room_id]
        logCore.log_write(f"已删除空房间 {room_id}。")