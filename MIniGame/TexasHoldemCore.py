'''
Texas Hold'em 德州扑克游戏模块
标准德州扑克牌游戏规则实现
游戏数据储存在内存中，如果牌局结束则结算并清除数据



'''

from typing import List, Dict, Optional
import random

from src.plugin_system.apis import send_api


# 玩家结构体
class Player:
    def __init__(self, user_id: int, username: str, user_qq: int, chips: int):
        self.user_id = user_id
        self.username = username
        self.user_qq = user_qq
        self.chips = chips
        self.hand: List[str] = []
        self.current_bet: int = 0
        self.has_folded: bool = False
        self.is_all_in: bool = False
        self.round_bet: int = 0
        self.is_dealer: bool = False
        self.is_small_blind: bool = False
        self.is_big_blind: bool = False



# 房间结构体
class Room:
    def __init__(self, room_id: int, max_players: int = 6, initial_chips: int = 1000):
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
        self.small_blind = 10
        self.big_blind = 20
        self.last_raiser_index = 0
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
            p.has_folded = False
            p.is_all_in = False
            p.is_dealer = False
            p.is_small_blind = False
            p.is_big_blind = False
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





# 发送消息到指定用户（异步）
import asyncio
async def send_message(user_id: int, message: str):
    await send_api.text_to_user(message, str(user_id))


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
def place_bet(room: Room, user_id: int, amount: int) -> bool:
    for player in room.players:
        if player.user_id == user_id:
            if amount > player.chips:
                return False
            player.chips -= amount
            player.current_bet += amount
            player.round_bet += amount
            room.pot += amount
            if amount > room.current_bet:
                room.current_bet = amount
            if player.chips == 0:
                player.is_all_in = True
            return True
    return False


# 弃牌
def fold(room: Room, user_id: int) -> bool:
    for player in room.players:
        if player.user_id == user_id:
            player.has_folded = True
            return True
    return False


# 结算（仅主干，牌型比较需补充）
def settle_game(room: Room):
    # 评比所有未弃牌玩家的牌型，找出最大牌型
    from collections import Counter
    def hand_rank(cards):
        # 输入7张牌，返回(牌型等级, 主要点数, kicker...)
        # 牌型等级：9皇家同花顺 8同花顺 7四条 6葫芦 5同花 4顺子 3三条 2两对 1一对 0高牌
        # 牌面映射
        rank_map = {'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,'10':10,'J':11,'Q':12,'K':13,'A':14}
        suits = [c[-1] for c in cards]
        ranks = [c[:-1] for c in cards]
        rank_nums = sorted([rank_map[r] for r in ranks], reverse=True)
        # 统计
        count = Counter(rank_nums)
        counts = sorted(count.items(), key=lambda x: (-x[1], -x[0]))
        is_flush = any(suits.count(s) >= 5 for s in 'HDCS')
        flush_suit = next((s for s in 'HDCS' if suits.count(s) >= 5), None)
        flush_cards = [rank_map[c[:-1]] for c in cards if c[-1]==flush_suit] if flush_suit else []
        # 顺子
        def get_straight(nums):
            nums = sorted(set(nums), reverse=True)
            for i in range(len(nums)-4):
                window = nums[i:i+5]
                if window[0]-window[4]==4:
                    return window[0]
            # 特判A5432
            if set([14,5,4,3,2]).issubset(nums):
                return 5
            return None
        straight_high = get_straight(rank_nums)
        flush_straight_high = get_straight(flush_cards) if is_flush else None
        # 皇家同花顺
        if is_flush and flush_straight_high==14:
            return (9, 14)
        # 同花顺
        if is_flush and flush_straight_high:
            return (8, flush_straight_high)
        # 四条
        if counts[0][1]==4:
            kicker = max([x for x in rank_nums if x!=counts[0][0]])
            return (7, counts[0][0], kicker)
        # 葫芦
        if counts[0][1]==3 and counts[1][1]>=2:
            return (6, counts[0][0], counts[1][0])
        # 同花
        if is_flush:
            top5 = sorted(flush_cards, reverse=True)[:5]
            return (5, *top5)
        # 顺子
        if straight_high:
            return (4, straight_high)
        # 三条
        if counts[0][1]==3:
            kickers = [x for x in rank_nums if x!=counts[0][0]][:2]
            return (3, counts[0][0], *kickers)
        # 两对
        if counts[0][1]==2 and counts[1][1]==2:
            kicker = max([x for x in rank_nums if x!=counts[0][0] and x!=counts[1][0]])
            return (2, counts[0][0], counts[1][0], kicker)
        # 一对
        if counts[0][1]==2:
            kickers = [x for x in rank_nums if x!=counts[0][0]][:3]
            return (1, counts[0][0], *kickers)
        # 高牌
        return (0, *rank_nums[:5])

    def hand_name(rank_tuple):
        names = ["高牌","一对","两对","三条","顺子","同花","葫芦","四条","同花顺","皇家同花顺"]
        return names[rank_tuple[0]]

    active_players = [p for p in room.players if not p.has_folded]
    if not active_players:
        return None
    best = None
    best_player = None
    best_hand_cards = None
    for p in active_players:
        # 7张牌选5张最大
        from itertools import combinations
        all_cards = p.hand + room.community_cards
        best5 = None
        bestrank = None
        for comb in combinations(all_cards,5):
            r = hand_rank(list(comb))
            if bestrank is None or r > bestrank:
                bestrank = r
                best5 = list(comb)
        if best is None or bestrank > best:
            best = bestrank
            best_player = p
            best_hand_cards = best5
    if best_player:
        best_player.chips += room.pot
        return best_player, best_hand_cards, hand_name(best)
    return None

# 更新筹码
def update_chips(player: Player, amount: int):
    player.chips += amount

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
    if n >= 3:
        sb = room.players[(room.dealer_index + 1) % n]
        bb = room.players[(room.dealer_index + 2) % n]
        place_bet(room, sb.user_id, min(room.small_blind, sb.chips))
        place_bet(room, bb.user_id, min(room.big_blind, bb.chips))
    deal_hole_cards(room)
    room.round_stage = "preflop"

def next_betting_round(room: Room):
    if room.round_stage == "preflop":
        deal_community_cards(room, 3)
        room.round_stage = "flop"
    elif room.round_stage == "flop":
        deal_community_cards(room, 1)
        room.round_stage = "turn"
    elif room.round_stage == "turn":
        deal_community_cards(room, 1)
        room.round_stage = "river"
    elif room.round_stage == "river":
        room.round_stage = "showdown"
        settle_game(room)