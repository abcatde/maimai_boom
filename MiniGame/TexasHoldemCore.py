'''
Texas Hold'em 德州扑克游戏模块
标准德州扑克牌游戏规则实现
游戏数据储存在内存中，如果牌局结束则结算并清除数据



'''

import time
from typing import List, Dict, Optional, Tuple
import random
from ..core import logCore
from src.plugin_system.apis import chat_api, send_api
from ..core import userCore





# 玩家结构体
class Player:
    def __init__(self, user_id: int, username: str, chips: int):
        self.user_id = user_id
        self.username = username
        self.chips = chips
        self.hand: List[str] = []
        self.current_bet: int = 0
        self.has_folded: bool = False
        self.is_all_in: bool = False
        self.round_bet: int = 0
        self.total_bet: int = 0  # 本手牌累计投入（用于边池）
        self.is_dealer: bool = False
        self.is_small_blind: bool = False
        self.is_big_blind: bool = False
        self.has_acted_this_round: bool = False



# 房间结构体
class Room:
    def __init__(self, room_id: int, max_players: int = 6, initial_chips: int = 1000, rate: int = 1):
        self.room_id = room_id
        self.players: List[Player] = []
        self.pot: int = 0
        self.community_cards: List[str] = []
        self.current_bet: int = 0
        self.dealer_index: int = 0
        self.current_player_index: int = 0
        self.deck: List[str] = self.create_deck()
        self.round_stage: str = "waiting"  # waiting, preflop, flop, turn, river, showdown
        self.max_players = max_players
        self.initial_chips = initial_chips
        self.rate = rate
        self.small_blind = 10 * rate  # 盲注随倍率缩放，保持筹码成本比例
        self.big_blind = 20 * rate
        self.last_raiser_index: Optional[int] = None
        self.last_bet_amount = 0
        random.shuffle(self.deck)

    def create_deck(self) -> List[str]:
        suits = ['H', 'D', 'C', 'S']
        ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        return [rank + suit for suit in suits for rank in ranks]

    def reset_for_new_hand(self):
        self.pot = 0
        self.community_cards = []
        self.current_bet = 0
        self.deck = self.create_deck()
        random.shuffle(self.deck)
        for p in self.players:
            p.hand = []
            p.current_bet = 0
            p.round_bet = 0
            p.total_bet = 0
            p.has_folded = False
            p.is_all_in = False
            p.is_dealer = False
            p.is_small_blind = False
            p.is_big_blind = False
            p.has_acted_this_round = False
        self.round_stage = "preflop"

    def get_active_players(self) -> List[Player]:
        return [p for p in self.players if not p.has_folded and not p.is_all_in and p.chips > 0]

    def next_player_index(self, idx):
        n = len(self.players)
        for i in range(1, n):
            ni = (idx + i) % n
            p = self.players[ni]
            if not p.has_folded and not p.is_all_in and p.chips > 0:
                return ni
        return None

def _active_players(room: Room) -> List[Player]:
    return [p for p in room.players if not p.has_folded]

def _actionable_players(room: Room) -> List[Player]:
    return [p for p in room.players if not p.has_folded and not p.is_all_in and p.chips > 0]

def _reset_street_bets(room: Room):
    room.current_bet = 0
    for p in room.players:
        p.current_bet = 0
        p.round_bet = 0
        p.has_acted_this_round = False

def _first_to_act_index(room: Room, stage: str) -> Optional[int]:
    """返回本轮第一个可行动玩家的索引，跳过已弃牌/全下/无筹码玩家。"""
    n = len(room.players)
    if n == 0:
        return None
    dealer = room.dealer_index % n
    start = None
    if stage == "preflop":
        if n == 2:
            start = dealer  # 头对头局：庄家（小盲）先行动
        else:
            start = (dealer + 3) % n  # 大盲左侧（UTG）
    else:
        start = (dealer + 1) % n  # 翻牌圈及之后，小盲左侧先行动

    for i in range(n):
        idx = (start + i) % n
        p = room.players[idx]
        if not p.has_folded and not p.is_all_in and p.chips > 0:
            return idx
    return None

def _is_betting_round_settled(room: Room) -> bool:
    actionable = _actionable_players(room)
    if not actionable:
        return True
    target = room.current_bet
    for p in actionable:
        if p.current_bet != target:
            return False
        if not p.has_acted_this_round:
            return False
    return True

def _check_single_player_win(room: Room) -> Optional[Player]:
    alive = [p for p in room.players if not p.has_folded]
    if len(alive) == 1:
        winner = alive[0]
        winner.chips += room.pot
        room.pot = 0
        return winner
    return None

def _collect_blinds(room: Room):
    n = len(room.players)
    if n < 2:
        return
    sb_idx = (room.dealer_index + 1) % n
    bb_idx = (room.dealer_index + 2) % n if n > 2 else (room.dealer_index + 1) % n
    sb_player = room.players[sb_idx]
    bb_player = room.players[bb_idx]
    sb_amount = min(room.small_blind, sb_player.chips)
    bb_amount = min(room.big_blind, bb_player.chips)
    place_bet(room, sb_player.user_id, sb_amount, mark_action=False)
    place_bet(room, bb_player.user_id, bb_amount, mark_action=False)
    room.current_bet = max(sb_amount, bb_amount)
    room.last_raiser_index = bb_idx if bb_amount >= sb_amount else sb_idx


def reset_hand_state(room: Room):
    """清理一手牌后的状态，回到等待开局阶段"""
    room.pot = 0
    room.community_cards = []
    room.current_bet = 0
    room.deck = room.create_deck()
    random.shuffle(room.deck)
    room.round_stage = "waiting"
    room.current_player_index = None
    room.last_raiser_index = None
    for p in room.players:
        p.hand = []
        p.current_bet = 0
        p.round_bet = 0
        p.total_bet = 0
        p.has_folded = False
        p.is_all_in = False
        p.has_acted_this_round = False
        p.is_dealer = False
        p.is_small_blind = False
        p.is_big_blind = False


#向用户发起私聊消息
async def send_private_message(
    user_id: str,
    message: str,
    platform: str = "qq",
    config_getter=None
) -> Tuple[bool, str]:
    """
    向指定用户发送私聊消息
    
    Args:
        user_id: 用户ID
        message: 要发送的消息内容
        platform: 平台名称，默认为 "qq"
        config_getter: 配置获取函数
    
    Returns:
        Tuple[bool, str]: (是否成功, 结果描述)
    """
    try:
        # 检查冷却时间
        if config_getter:
            cooldown_seconds = config_getter("general.cooldown_seconds", 300)
            if not PrivateChatCooldown.can_send(user_id, cooldown_seconds):
                remaining = PrivateChatCooldown.get_remaining_time(user_id, cooldown_seconds)
                return False, f"冷却中，还需等待 {remaining} 秒"
        
        # 获取用户的私聊流
        chat_stream = chat_api.get_stream_by_user_id(user_id, platform)
        
        if chat_stream is None:
            logCore.log_write(f"未找到用户 {user_id} 的私聊流，可能该用户从未与麦麦私聊过")
            return False, f"未找到用户 {user_id} 的私聊流"
        
        # 发送消息
        success = await send_api.text_to_stream(
            text=message,
            stream_id=chat_stream.stream_id,
            typing=True,  # 显示正在输入
            storage_message=True  # 存储消息到数据库
        )
        
        if success:
            # 记录发送时间
            PrivateChatCooldown.record_send(user_id)
            logCore.log_write(f"向用户 {user_id} 发送私聊消息成功")
            return True, "私聊消息发送成功"
        else:
            logCore.log_write(f"向用户 {user_id} 发送私聊消息失败")
            return False, "消息发送失败"
            
    except Exception as e:
        logCore.log_write(f"发送私聊消息时出错: {e}")
        return False, f"发送出错: {str(e)}"

async def send_message(user_id: str, message: str, platform: str = "qq") -> Tuple[bool, str]:
    """兼容性的用户消息发送封装，主要用于系统提示。"""
    try:
        chat_stream = chat_api.get_stream_by_user_id(user_id, platform)
        if chat_stream is None:
            return False, "未找到聊天会话"
        success = await send_api.text_to_stream(
            text=message,
            stream_id=chat_stream.stream_id,
            typing=False,
            storage_message=True
        )
        return success, "发送成功" if success else "发送失败"
    except Exception as exc:
        logCore.log_write(f"发送消息异常: {exc}")
        return False, f"发送失败: {exc}"
    
class PrivateChatCooldown:
    """私聊冷却时间管理器"""
    
    _cooldowns: Dict[str, float] = {}
    
    @classmethod
    def can_send(cls, user_id: str, cooldown_seconds: int) -> bool:
        """检查是否可以向指定用户发送私聊"""
        last_time = cls._cooldowns.get(user_id, 0)
        return time.time() - last_time >= cooldown_seconds
    
    @classmethod
    def record_send(cls, user_id: str):
        """记录向指定用户发送私聊的时间"""
        cls._cooldowns[user_id] = time.time()
    
    @classmethod
    def get_remaining_time(cls, user_id: str, cooldown_seconds: int) -> int:
        """获取剩余冷却时间（秒）"""
        last_time = cls._cooldowns.get(user_id, 0)
        remaining = cooldown_seconds - (time.time() - last_time)
        return max(0, int(remaining))

def find_player_room(rooms: Dict[int, 'Room'], user_id: str) -> Optional[Tuple[int, 'Room', Player]]:
    """返回玩家所在的房间信息 (room_id, room, player)。"""
    target_id = int(user_id)
    for room_id, room in rooms.items():
        for player in room.players:
            if player.user_id == target_id:
                return room_id, room, player
    return None

def create_room_and_join(rooms: dict, user_id: str, username: str,  rate: int, person_id: str) -> Tuple[bool, Optional[str], Optional['Room']]:
    """
    创建房间并自动加入，负责金币判断和扣除
    """

    # 检查是否已在房间
    occupied = find_player_room(rooms, user_id)
    if occupied:
        occupied_room_id, _, _ = occupied
        return False, f"您已在房间 {occupied_room_id}，请先离开当前房间。", None
            
    import random
    
    while True:
        room_id = random.randint(10001, 99999)
        if room_id not in rooms:
            break
    new_room = Room(room_id, rate=rate)
    chips_needed = new_room.initial_chips * rate
    user = userCore.get_user_info(person_id)
    if user is None:
        return False, "未找到用户信息，请先签到注册或重试。", None
    coins = user.coins
    if coins < chips_needed:
        return False, f"金币不足，创建房间需 {chips_needed} 金币（倍率{rate}，初始筹码{new_room.initial_chips}）。", None
    userCore.update_coins_to_user(person_id, -chips_needed)
    # 确保玩家ID为整型，保持与房间查询/比较一致
    player = Player(int(user_id), username, new_room.initial_chips)
    join_room(new_room, player)
    rooms[room_id] = new_room
    return True, f"房间 {room_id} 创建成功并已自动加入！\n倍率：{rate}（1筹码={rate}金币）\n当前房间人数：1\n如需邀请他人，请让其使用 .加入房间 {room_id}", new_room

# 加入房间
def join_room(room: Room, player: Player) -> bool:
    if len(room.players) >= room.max_players:
        return False
    room.players.append(player)
    return True


# 离开房间
def leave_room(room: Room, user_id: int) -> bool:
    for i, player in enumerate(room.players):
        if player.user_id == user_id:
            del room.players[i]
            return True
    return False


# 发手牌
def deal_hole_cards(room: Room):
    for player in room.players:
        player.hand = [room.deck.pop(), room.deck.pop()]


# 发公共牌
def deal_community_cards(room: Room, number: int):
    for _ in range(number):
        room.community_cards.append(room.deck.pop())


# 下注
def place_bet(room: Room, user_id: int, amount: int, mark_action: bool = True) -> bool:
    for player in room.players:
        if player.user_id == user_id:
            if amount > player.chips:
                return False
            prev_room_bet = room.current_bet
            player.chips -= amount
            player.current_bet += amount
            player.round_bet += amount
            player.total_bet += amount
            room.pot += amount
            room.current_bet = max(room.current_bet, player.current_bet)
            if mark_action and player.current_bet > prev_room_bet:
                room.last_raiser_index = room.players.index(player)
            if player.chips == 0:
                player.is_all_in = True
            if mark_action:
                player.has_acted_this_round = True
            return True
    return False


# 弃牌
def fold(room: Room, user_id: int) -> bool:
    for player in room.players:
        if player.user_id == user_id:
            player.has_folded = True
            player.has_acted_this_round = True
            # 若弃牌者是当前最大下注来源，回落当前下注基准，避免无人跟注卡轮次
            remaining = [p.current_bet for p in room.players if not p.has_folded]
            room.current_bet = max(remaining) if remaining else 0
            return True
    return False


def mark_player_acted(room: Room, user_id: int) -> None:
    player = get_player(room, user_id)
    if player:
        player.has_acted_this_round = True


def _hand_rank(cards):
    from collections import Counter
    rank_map = {'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,'10':10,'J':11,'Q':12,'K':13,'A':14}
    suits = [c[-1] for c in cards]
    ranks = [c[:-1] for c in cards]
    rank_nums = sorted([rank_map[r] for r in ranks], reverse=True)
    count = Counter(rank_nums)
    counts = sorted(count.items(), key=lambda x: (-x[1], -x[0]))
    is_flush = any(suits.count(s) >= 5 for s in 'HDCS')
    flush_suit = next((s for s in 'HDCS' if suits.count(s) >= 5), None)
    flush_cards = [rank_map[c[:-1]] for c in cards if c[-1]==flush_suit] if flush_suit else []

    def get_straight(nums):
        nums = sorted(set(nums), reverse=True)
        for i in range(len(nums)-4):
            window = nums[i:i+5]
            if window[0]-window[4]==4:
                return window[0]
        if set([14,5,4,3,2]).issubset(nums):
            return 5
        return None

    straight_high = get_straight(rank_nums)
    flush_straight_high = get_straight(flush_cards) if is_flush else None
    if is_flush and flush_straight_high==14:
        return (9, 14)
    if is_flush and flush_straight_high:
        return (8, flush_straight_high)
    if counts[0][1]==4:
        kicker = max([x for x in rank_nums if x!=counts[0][0]])
        return (7, counts[0][0], kicker)
    if counts[0][1]==3 and counts[1][1]>=2:
        return (6, counts[0][0], counts[1][0])
    if is_flush:
        top5 = sorted(flush_cards, reverse=True)[:5]
        return (5, *top5)
    if straight_high:
        return (4, straight_high)
    if counts[0][1]==3:
        kickers = [x for x in rank_nums if x!=counts[0][0]][:2]
        return (3, counts[0][0], *kickers)
    if counts[0][1]==2 and counts[1][1]==2:
        kicker = max([x for x in rank_nums if x!=counts[0][0] and x!=counts[1][0]])
        return (2, counts[0][0], counts[1][0], kicker)
    if counts[0][1]==2:
        kickers = [x for x in rank_nums if x!=counts[0][0]][:3]
        return (1, counts[0][0], *kickers)
    return (0, *rank_nums[:5])


def _hand_name(rank_tuple):
    names = ["高牌","一对","两对","三条","顺子","同花","葫芦","四条","同花顺","皇家同花顺"]
    return names[rank_tuple[0]]


def _best_five_for_player(player: Player, community_cards: List[str]):
    from itertools import combinations
    all_cards = player.hand + community_cards
    best5 = None
    bestrank = None
    for comb in combinations(all_cards,5):
        r = _hand_rank(list(comb))
        if bestrank is None or r > bestrank:
            bestrank = r
            best5 = list(comb)
    return bestrank, best5


def settle_game(room: Room):
    """摊牌结算，支持边池，包含已弃牌玩家投入的筹码。"""
    contenders = [p for p in room.players if not p.has_folded]
    if not contenders:
        return None

    # 使用所有投入过筹码的玩家构建层级，以防弃牌筹码被漏掉
    contrib = {p: p.total_bet for p in room.players if p.total_bet > 0}
    if not contrib:
        return None
    levels = sorted(set(contrib.values()))
    pots = []  # (amount, participants)
    prev = 0
    for level in levels:
        eligible_all = [p for p, v in contrib.items() if v >= level]
        participants = [p for p in eligible_all if not p.has_folded]
        if not participants:
            prev = level
            continue
        slice_amount = (level - prev) * len(eligible_all)
        if slice_amount > 0:
            pots.append((slice_amount, participants))
        prev = level

    results = []
    for amount, participants in pots:
        ranked = []
        for p in participants:
            rank, best5 = _best_five_for_player(p, room.community_cards)
            ranked.append((rank, p, best5))
        ranked.sort(key=lambda x: x[0], reverse=True)
        winners = [r for r in ranked if r[0] == ranked[0][0]]
        split = amount // len(winners)
        remainder = amount % len(winners)
        for idx, (_, player, best5) in enumerate(winners):
            gain = split + (1 if idx < remainder else 0)
            player.chips += gain
        show_rank, show_player, show_hand = winners[0]
        tied_names = [w[1].username for w in winners]
        results.append((show_player, show_hand, _hand_name(show_rank), amount, tied_names))

    room.pot = 0

    return results if results else None

# 更新筹码
def update_chips(player: Player, amount: int):
    player.chips += amount

def get_player(room: Room, user_id: int) -> Optional[Player]:
    for p in room.players:
        if p.user_id == user_id:
            return p
    return None

def is_player_turn(room: Room, user_id: int) -> bool:
    if room.current_player_index is None:
        return False
    return room.players[room.current_player_index].user_id == user_id

def move_to_next_player(room: Room):
    if _is_betting_round_settled(room):
        room.current_player_index = None
        return
    if room.current_player_index is None:
        room.current_player_index = _first_to_act_index(room, room.round_stage)
        return
    nxt = room.next_player_index(room.current_player_index)
    room.current_player_index = nxt

# 游戏流程推进主干（伪代码/接口，具体命令层实现）
def start_new_hand(room: Room):
    room.reset_for_new_hand()
    # 轮转庄家
    n = len(room.players)
    room.dealer_index = (room.dealer_index + 1) % n if n > 0 else 0
    for i, p in enumerate(room.players):
        p.is_dealer = (i == room.dealer_index)
        p.is_small_blind = (i == (room.dealer_index + 1) % n)
        p.is_big_blind = (i == (room.dealer_index + 2) % n)
    # 收盲注
    _collect_blinds(room)
    deal_hole_cards(room)
    room.round_stage = "preflop"
    room.current_player_index = _first_to_act_index(room, "preflop")
    room.last_raiser_index = room.current_player_index

def next_betting_round(room: Room):
    # 仅在下注轮已结算时推进
    if not _is_betting_round_settled(room):
        return False
    if room.round_stage == "preflop":
        _reset_street_bets(room)
        deal_community_cards(room, 3)
        room.round_stage = "flop"
    elif room.round_stage == "flop":
        _reset_street_bets(room)
        deal_community_cards(room, 1)
        room.round_stage = "turn"
    elif room.round_stage == "turn":
        _reset_street_bets(room)
        deal_community_cards(room, 1)
        room.round_stage = "river"
    elif room.round_stage == "river":
        room.round_stage = "showdown"
        return settle_game(room)
    room.current_player_index = _first_to_act_index(room, room.round_stage)
    room.last_raiser_index = room.current_player_index
    return True