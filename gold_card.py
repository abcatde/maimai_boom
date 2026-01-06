from __future__ import annotations

import asyncio
import json
import os
import random
import time
from typing import Dict, Any, Optional, Tuple

from src.common.logger import get_logger
from src.plugin_system.base.base_command import BaseCommand
from src.plugin_system.apis import person_api
from .data import BoomDataManager

logger = get_logger("boom_plugin.gold_card")

STATE_FILE = os.path.join(os.path.dirname(__file__), "gold_card_state.json")
LOCK_PATH = STATE_FILE + ".lock"


def _ensure_state_file() -> None:
    if not os.path.exists(STATE_FILE):
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"rooms": {}}, f, ensure_ascii=False)


def _load_state() -> Dict[str, Any]:
    _ensure_state_file()
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_state(state: Dict[str, Any]) -> None:
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)


def _acquire_lock(lock_path: str, timeout: float = 5.0, poll: float = 0.05) -> bool:
    import time as _time
    waited = 0.0
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, str(os.getpid()).encode("utf-8"))
            finally:
                os.close(fd)
            return True
        except FileExistsError:
            if waited >= timeout:
                return False
            _time.sleep(poll)
            waited += poll
            continue
        except Exception:
            logger.exception("获取状态文件锁时出错")
            return False


def _release_lock(lock_path: str) -> None:
    try:
        if os.path.exists(lock_path):
            os.remove(lock_path)
    except Exception:
        logger.exception("释放状态文件锁时出错")


async def _run_with_state(cmd_self, coro):
    got = _acquire_lock(LOCK_PATH)
    if not got:
        logger.warning("gold_card lock timeout")
        try:
            await cmd_self.send_text("系统繁忙，请稍后重试")
        except Exception:
            pass
        return False, "系统繁忙", False
    try:
        state = _load_state()
        res = await coro(state)
        _save_state(state)
        return res
    finally:
        _release_lock(LOCK_PATH)


async def _get_nick(person_id: int) -> str:
    try:
        nick = await person_api.get_person_value(person_id, "nickname", "未知用户")
        return nick or "未知用户"
    except Exception:
        return "未知用户"


def _gen_room_code() -> str:
    return "%06d" % random.randint(0, 999999)


def schedule_room_timeouts(scheduler, send_func=None):
    """Register a periodic job to check room timeouts every 6 minutes.

    `send_func` should be an async callable accepting a single string argument
    (the message). If omitted, messages will be logged.
    """
    async def _check_job():
        got = _acquire_lock(LOCK_PATH)
        if not got:
            logger.warning("gold_card timeout-check lock busy")
            return
        try:
            state = _load_state()
            rooms = state.setdefault("rooms", {})
            now = time.time()
            for code, room in list(rooms.items()):
                if room.get("finished"):
                    continue
                # created but no guest -> destroy after 6 minutes
                if room.get("guest") is None:
                    if now - room.get("created_at", now) > 6 * 60:
                        BoomDataManager.add_gold(room["host"], room.get("stake", 0))
                        host_n = await _get_nick(room["host"])
                        rooms.pop(code, None)
                        msg = f"{host_n} 的房间创建超时，已销毁。"
                        try:
                            if send_func:
                                res = send_func(msg)
                                if asyncio.iscoroutine(res):
                                    await res
                            else:
                                logger.info(msg)
                        except Exception:
                            logger.exception("发送房间销毁消息失败")
                else:
                    # started but not finished -> timeout settlement after 12 minutes
                    if now - room.get("started_at", now) > 12 * 60:
                        # reuse settle logic
                        try:
                            res = await GoldCardBase()._do_settle(state, rooms, room)
                            if send_func:
                                r = send_func(res)
                                if asyncio.iscoroutine(r):
                                    await r
                            else:
                                logger.info(res)
                        except Exception:
                            logger.exception("自动结算时出错")
            _save_state(state)
        finally:
            _release_lock(LOCK_PATH)

    global _SCHEDULER
    try:
        _SCHEDULER = scheduler
        job = scheduler.add_job(_check_job, 'interval', hours=0.1, id='gold_card_timeouts', name='gold_card_timeouts', next_run_time=None)
        return job
    except Exception:
        logger.exception("注册房间超时检查任务失败")
        return None


class GoldCardBase:
    def _find_room_by_user(self, rooms: Dict[str, Any], uid: int) -> Optional[Dict[str, Any]]:
        for code, r in rooms.items():
            if r.get("host") == uid or r.get("guest") == uid:
                r.setdefault("_code", code)
                return r
        return None

    async def _check_timeouts(self, state: Dict[str, Any]) -> None:
        now = time.time()
        rooms = state.setdefault("rooms", {})
        for code, room in list(rooms.items()):
            if room.get("finished"):
                continue
            if room.get("guest") is None:
                if now - room.get("created_at", now) > 6 * 60:
                    # refund host and destroy room
                    BoomDataManager.add_gold(room["host"], room.get("stake", 0))
                    host_n = await _get_nick(room["host"])
                    # remove room from state
                    rooms.pop(code, None)
                    msg = f"{host_n} 的房间创建超时，已销毁。"
                    try:
                        await self.send_text(msg)
                    except Exception:
                        logger.info(msg)
            else:
                if now - room.get("started_at", now) > 12 * 60:
                    rounds = room.get("rounds", [])
                    if rounds:
                        first = rounds[0]
                        host_card = first["host"]
                        guest_card = first["guest"]
                        if host_card > guest_card:
                            winner = room["host"]
                        elif guest_card > host_card:
                            winner = room["guest"]
                        else:
                            winner = None
                        if winner is None:
                            BoomDataManager.add_gold(room["host"], room.get("stake", 0))
                            BoomDataManager.add_gold(room["guest"], room.get("stake", 0))
                            rooms.pop(code, None)
                            msg = "超时平局，已退款"
                            try:
                                await self.send_text(msg)
                            except Exception:
                                logger.info(msg)
                        else:
                            pot = room.get("pot", 0)
                            fee = max(1, int((pot * 0.01) + 0.9999))
                            BoomDataManager.add_gold(winner, pot - fee)
                            rooms.pop(code, None)
                            winner_n = await _get_nick(winner)
                            msg = f"超时结算，赢家 {winner_n} 获得 {pot-fee} (手续费 {fee})"
                            try:
                                await self.send_text(msg)
                            except Exception:
                                logger.info(msg)

    async def _do_settle(self, state: Dict[str, Any], rooms: Dict[str, Any], room: Dict[str, Any]) -> str:
        if room.get("finished"):
            return "牌局已结束"
        rounds = room.get("rounds", [])
        if not rounds:
            return "尚未发牌，无法结算"
        # 比较所有轮次牌面的总和
        host = room["host"]
        guest = room.get("guest")
        pot = room.get("pot", 0)
        sum_host = sum(int(r.get("host", 0)) for r in rounds)
        sum_guest = sum(int(r.get("guest", 0)) for r in rounds)
        # 三轮且总和值相等 -> 三轮平局
        if sum_host == sum_guest:
            if len(rounds) >= 3:
                stake = room.get("stake", 0)
                BoomDataManager.add_gold(host, stake * 2)
                BoomDataManager.add_gold(guest, stake * 2)
                room["finished"] = True
                room["result"] = "三轮平局，返还双倍赌注给双方"
                if rooms is not None:
                    code = room.get("_code")
                    if code:
                        rooms.pop(code, None)
                return room["result"]
            else:
                return "本轮牌面相同，任意一方可继续或加注"

        if sum_host > sum_guest:
            winner = host
        else:
            winner = guest

        fee = max(1, int((pot * 0.01) + 0.9999))
        BoomDataManager.add_gold(winner, pot - fee)
        room["finished"] = True
        winner_n = await _get_nick(winner)
        room["result"] = f"玩家 {winner_n} 获胜，获得 {pot-fee}，手续费 {fee}"
        if rooms is not None:
            code = room.get("_code")
            if code:
                rooms.pop(code, None)
        return room["result"]

class GoldCardHelp(GoldCardBase,BaseCommand):
        command_name = "card_help"
        command_description = "卡牌帮助"
        command_pattern = r"^.开一局牌$"
        command_pattern = r"^.金币卡牌$"

        async def execute(self) -> Tuple[bool, Optional[str], bool]:
            help_text = (
                "金币卡牌命令：\n"
                "1. .开一局牌 <下注金额> 开始一局牌，下注金额最低为20金币\n"
                "2. .加入牌局 <房间ID>\n"
                "3. .加注 <加注金额> 在回合内可多次加注\n"
                "4. .结算 只有牌更小的一方可以主动结算牌局，结算时需缴纳总下注1%的费率"
                )
            await self.send_text(help_text)
            return True, "查看金币卡牌规则成功", False



class CreateRoomCommand(GoldCardBase, BaseCommand):
    command_name = "create_gold_card"
    command_description = "开一局牌"
    command_pattern = r"^.开一局牌\s*(?P<stake>\d+)$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        async def _logic(state: Dict[str, Any]):
            stake = int(self.matched_groups.get("stake") or 0)
            if stake < 20:
                await self.send_text("赌注最小为20")
                return False, "赌注太小", False
            platform = getattr(self.message.message_info, "platform", "")
            user_info = getattr(self.message.message_info, "user_info", None)
            if not user_info:
                return False, "无法获取用户信息", False
            uid = person_api.get_person_id(platform, user_info.user_id)
            rooms = state.setdefault("rooms", {})
            # 检查用户是否已在其他牌局中
            existing = self._find_room_by_user(rooms, uid)
            if existing:
                await self.send_text("你已经在一个牌局中，无法创建新的牌局（请先结束或离开当前牌局）")
                return False, "已在牌局中", False
            if BoomDataManager.get_gold(uid) < stake:
                await self.send_text("金币不足，无法创建房间")
                return False, "金币不足", False
            code = _gen_room_code()
            BoomDataManager.add_gold(uid, -stake)
            state.setdefault("rooms", {})[code] = {
                "host": uid,
                "guest": None,
                "stake": stake,
                "raises": {str(uid): 0},
                "pot": stake,
                "rounds": [],
                "created_at": time.time(),
                "started_at": None,
                "finished": False,
            }
            await self.send_text(f"房间已创建，房间代码：{code}，等待玩家加入")
            return True, "创建成功", False

        return await _run_with_state(self, _logic)


class JoinRoomCommand(GoldCardBase, BaseCommand):
    command_name = "join_gold_card"
    command_description = "加入牌局"
    command_pattern = r"^.加入牌局\s*(?P<code>\d+)$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        async def _logic(state: Dict[str, Any]):
            code = self.matched_groups.get("code")
            rooms = state.setdefault("rooms", {})
            if code not in rooms:
                await self.send_text("未找到该房间")
                return False, "未找到房间", False
            room = rooms[code]
            if room.get("guest") is not None:
                await self.send_text("房间已满")
                return False, "房间已满", False
            platform = getattr(self.message.message_info, "platform", "")
            user_info = getattr(self.message.message_info, "user_info", None)
            if not user_info:
                return False, "无法获取用户信息", False
            uid = person_api.get_person_id(platform, user_info.user_id)
            # 检查用户是否已在其他牌局中
            existing = self._find_room_by_user(rooms, uid)
            if existing:
                await self.send_text("你已经在一个牌局中，无法加入其他牌局（请先结束或离开当前牌局）")
                return False, "已在牌局中", False
            if uid == room["host"]:
                await self.send_text("房主不能加入自己的房间")
                return False, "房主不能加入", False
            stake = room["stake"]
            if BoomDataManager.get_gold(uid) < stake:
                await self.send_text("金币不足，无法加入房间")
                return False, "金币不足", False
            BoomDataManager.add_gold(uid, -stake)
            room["guest"] = uid
            room.setdefault("raises", {})[str(uid)] = 0
            room["pot"] += stake
            room["started_at"] = time.time()
            # 自动进行第一轮发牌
            host = room["host"]
            guest = uid
            host_card = random.randint(1, 13)
            guest_card = random.randint(1, 13)
            room["rounds"].append({"host": host_card, "guest": guest_card, "ts": time.time()})
            if host_card < guest_card:
                room["action_expected"] = host
            elif guest_card < host_card:
                room["action_expected"] = guest
            else:
                room["action_expected"] = None

            # 如果这是第三轮或之后的发牌，直接结算（无需询问）
            if len(room.get("rounds", [])) >= 3:
                res = await self._do_settle(state, rooms, room)
                await self.send_text(res)
                return True, "已结算", False

            host_n = await _get_nick(host)
            guest_n = await _get_nick(guest)
            def _cards_for(key: str) -> str:
                return " ".join(str(r.get(key)) for r in room.get("rounds", []))

            cards_host = _cards_for("host")
            cards_guest = _cards_for("guest")
            pot = room.get("pot", 0)
            # 计算每人已下注（底注 + 加注）
            stake = room.get("stake", 0)
            raises = room.get("raises", {})
            host_contrib = stake + int(raises.get(str(host), 0))
            guest_contrib = stake + int(raises.get(str(guest), 0))
            msg_lines = [f"已加入房间 {code}；当前彩池：{pot}（注：{host_n} 已下注 {host_contrib}，{guest_n} 已下注 {guest_contrib}）",
                         f"{host_n} 手牌： {cards_host}",
                         f"{guest_n} 手牌： {cards_guest}"]
            if room["action_expected"] is None:
                msg_lines.append("等待任意一方操作（.结算 或 .加注）")
            else:
                ae_n = await _get_nick(room["action_expected"])
                msg_lines.append(f"等待玩家 {ae_n} 进行 .结算 或 .加注")

            await self.send_text("\n".join(msg_lines))
            return True, "加入成功", False

        return await _run_with_state(self, _logic)


class DealCommand(GoldCardBase, BaseCommand):
    command_name = "deal_gold_card"
    command_description = "开牌"
    command_pattern = r"^.开牌$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        async def _logic(state: Dict[str, Any]):
            platform = getattr(self.message.message_info, "platform", "")
            user_info = getattr(self.message.message_info, "user_info", None)
            if not user_info:
                return False, "无法获取用户信息", False
            uid = person_api.get_person_id(platform, user_info.user_id)

            # timeouts check
            await self._check_timeouts(state)

            rooms = state.setdefault("rooms", {})
            room = self._find_room_by_user(rooms, uid)
            if not room:
                await self.send_text("你不在任何牌局中")
                return False, "不在牌局", False
            if room.get("finished"):
                reason = room.get("result") or "已结束"
                logger.debug("拒绝加注：房间已结束，原因：%s", reason)
                await self.send_text(f"牌局已结束：{reason}")
                return False, "已结束", False
            if room.get("guest") is None:
                await self.send_text("尚无人加入房间，无法发牌")
                return False, "无人加入", False
            if len(room["rounds"]) >= 3:
                # auto settle
                res = await self._do_settle(state, rooms, room)
                await self.send_text(res)
                return True, "已结算", False

            host = room["host"]
            guest = room["guest"]
            host_card = random.randint(1, 13)
            guest_card = random.randint(1, 13)
            room["rounds"].append({"host": host_card, "guest": guest_card, "ts": time.time()})
            if host_card < guest_card:
                room["action_expected"] = host
            elif guest_card < host_card:
                room["action_expected"] = guest
            else:
                room["action_expected"] = None

            # 构建合并消息：当前下注，玩家手牌（按轮次列出）
            def _cards_for(key: str) -> str:
                return " ".join(str(r.get(key)) for r in room.get("rounds", []))

            host_n = await _get_nick(host)
            guest_n = await _get_nick(guest)
            cards_host = _cards_for("host")
            cards_guest = _cards_for("guest")
            pot = room.get("pot", 0)
            # 每人已下注显示
            stake = room.get("stake", 0)
            raises = room.get("raises", {})
            host_contrib = stake + int(raises.get(str(host), 0))
            guest_contrib = stake + int(raises.get(str(guest), 0))
            lines = [f"第{len(room['rounds'])}轮发牌；当前彩池：{pot}（注：{host_n} 已下注 {host_contrib}，{guest_n} 已下注 {guest_contrib}）",
                     f"玩家1 {host_n} 手牌： {cards_host}",
                     f"玩家2 {guest_n} 手牌： {cards_guest}"]
            if room["action_expected"] is None:
                lines.append("等待任意一方操作（.结算 或 .加注）")
            else:
                ae_n = await _get_nick(room["action_expected"])
                lines.append(f"等待玩家 {ae_n} 进行 .结算 或 .加注")

            await self.send_text("\n".join(lines))
            return True, "发牌完成", False

        return await _run_with_state(self, _logic)

    def _find_room_by_user(self, rooms: Dict[str, Any], uid: int) -> Optional[Dict[str, Any]]:
        for code, r in rooms.items():
            if r.get("host") == uid or r.get("guest") == uid:
                r.setdefault("_code", code)
                return r
        return None

    async def _check_timeouts(self, state: Dict[str, Any]) -> None:
        now = time.time()
        rooms = state.setdefault("rooms", {})
        for code, room in list(rooms.items()):
            if room.get("finished"):
                continue
            if room.get("guest") is None:
                if now - room.get("created_at", now) > 6 * 60:
                    # refund host
                    BoomDataManager.add_gold(room["host"], room.get("stake", 0))
                    host_n = await _get_nick(room["host"])
                    room["finished"] = True
                    room["result"] = f"超时 未加入，已退款 给 {host_n}"
            else:
                if now - room.get("started_at", now) > 12 * 60:
                    rounds = room.get("rounds", [])
                    if rounds:
                        first = rounds[0]
                        host_card = first["host"]
                        guest_card = first["guest"]
                        if host_card > guest_card:
                            winner = room["host"]
                        elif guest_card > host_card:
                            winner = room["guest"]
                        else:
                            winner = None
                        if winner is None:
                            BoomDataManager.add_gold(room["host"], room.get("stake", 0))
                            BoomDataManager.add_gold(room["guest"], room.get("stake", 0))
                            room["finished"] = True
                            room["result"] = "超时平局，已退款"
                        else:
                            pot = room.get("pot", 0)
                            fee = max(1, int((pot * 0.01) + 0.9999))
                            BoomDataManager.add_gold(winner, pot - fee)
                            room["finished"] = True
                            winner_n = await _get_nick(winner)
                            room["result"] = f"超时结算，赢家 {winner_n} 获得 {pot-fee} (手续费 {fee})"

    # _do_settle 已在 GoldCardBase 中实现，此处删除重复定义


class SettleCommand(GoldCardBase, BaseCommand):
    command_name = "settle_gold_card"
    command_description = "结算当前轮"
    command_pattern = r"^.结算$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        async def _logic(state: Dict[str, Any]):
            platform = getattr(self.message.message_info, "platform", "")
            user_info = getattr(self.message.message_info, "user_info", None)
            if not user_info:
                return False, "无法获取用户信息", False
            uid = person_api.get_person_id(platform, user_info.user_id)
            rooms = state.setdefault("rooms", {})
            room = self._find_room_by_user(rooms, uid)
            if not room:
                await self.send_text("你不在任何牌局中")
                return False, "不在牌局", False
            res = await self._do_settle(state, rooms, room)
            await self.send_text(res)
            return True, "已结算", False

        return await _run_with_state(self, _logic)


class RaiseCommand(GoldCardBase, BaseCommand):
    command_name = "raise_gold_card"
    command_description = "加注"
    command_pattern = r"^.加注\s*(?P<amount>\d+)$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        async def _logic(state: Dict[str, Any]):
            amount = int(self.matched_groups.get("amount") or 0)
            if amount <= 0:
                await self.send_text("加注金额必须大于0")
                return False, "金额错误", False
            platform = getattr(self.message.message_info, "platform", "")
            user_info = getattr(self.message.message_info, "user_info", None)
            if not user_info:
                return False, "无法获取用户信息", False
            uid = person_api.get_person_id(platform, user_info.user_id)
            rooms = state.setdefault("rooms", {})
            room = self._find_room_by_user(rooms, uid)
            if not room:
                await self.send_text("你不在任何牌局中")
                return False, "不在牌局", False
            if room.get("finished"):
                await self.send_text("牌局已结束")
                return False, "已结束", False
            expected = room.get("action_expected")
            if expected is not None and expected != uid:
                await self.send_text("当前不在你操作回合")
                return False, "非操作方", False
            if BoomDataManager.get_gold(uid) < amount:
                await self.send_text("金币不足，无法加注")
                return False, "金币不足", False
            BoomDataManager.add_gold(uid, -amount)
            room.setdefault("raises", {})[str(uid)] = room.setdefault("raises", {}).get(str(uid), 0) + amount
            room["pot"] = room.get("pot", 0) + amount
            room["action_expected"] = None
            # 显示加注后每人累计下注
            stake = room.get("stake", 0)
            raises = room.get("raises", {})
            host_id = room.get("host")
            guest_id = room.get("guest")
            host_contrib = stake + int(raises.get(str(host_id), 0))
            guest_contrib = stake + int(raises.get(str(guest_id), 0)) if guest_id else stake
            host_n = await _get_nick(host_id)
            guest_n = await _get_nick(guest_id) if guest_id else "未加入"
            await self.send_text(f"已加注 {amount}，当前彩池 {room['pot']}；{host_n} 已下注 {host_contrib}，{guest_n} 已下注 {guest_contrib}。请任意一方使用 .开牌 继续发牌")
            return True, "已加注", False

        return await _run_with_state(self, _logic)


__all__ = [
    "CreateRoomCommand",
    "JoinRoomCommand",
    "DealCommand",
    "SettleCommand",
    "RaiseCommand",
    "GoldCardHelp",
]

''''
gold_card金币卡牌游戏类：
游戏规则：
1.使用 .开一局牌 <赌注数量> 建立一个房间，赌注数量最小20
2.另一名玩家使用 .加入牌局 <牌局代码>加入房间，房主不能加入自己的房间，加入后自动开第一轮牌
3.身处牌局中的玩家可以使用 .开牌 进行发牌，系统随机给两人从(1,2,....,10,J（11）,Q（12）,K（13）)中发牌
4.总共有三轮发牌机会，第一轮发牌结束后 等待牌序较小的一位发送 .结算 结算本轮牌局或 .加注 <金额> 指令继续牌局
5.每轮发牌后，如果两人的牌大小相同，则等待其中任意一位指令即可
6.每轮结束后，如果使用 .结算，则牌大的那一位获得赌注数量和所有加注的金币，同时扣除所得金额的1%作为手续费，最低1金币向上取整，如果三轮后牌大小相同，则返还双倍金币
7.每轮结束后，如果使用 .加注 <金额>指令，那么继续发第二轮牌
8.当第三轮发票结束后，自动结算
9.牌局超时：如果牌局创建后6分钟内无人加入，自动结算。如果已经开始的牌局，12分钟内没有结束，则自动按照第一局的发牌排序结算，如果牌大小相同




'''