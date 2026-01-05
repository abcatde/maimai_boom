
"""金币宝藏游戏实现。

命令：
- .金币宝藏          : 显示游戏规则
- .埋宝藏 <金币数量> : 玩家发起一局并将金币放入宝藏（最低1000）
- .挖宝藏 <数字>      : 消耗10金币挖掘一个位置，命中宝藏则获得宝藏，命中地雷则向宝藏主人支付宝藏价值/10
- .快速挖宝藏 <起> <止> : 一次性触发范围内所有数字（会逐个结算）

实现细节：
- 游戏状态保存在插件目录下的 `gold_treasure_state.json`。
- 挖掘费用固定为 10 金币，触发地雷需额外支付 `treasure_value // 10` 给宝藏主人。
- 埋宝藏时，发起者的金币会被扣除并作为奖池；找到宝藏时，奖池发放给发现者；若 10 个地雷被触发且宝藏未被找到，则游戏结束并退还奖池给发起者。
"""

import os
import json
import random
from typing import Optional, Tuple, List

from src.plugin_system.base.base_command import BaseCommand
from src.plugin_system.apis import person_api
from src.common.logger import get_logger
from .data import BoomDataManager

logger = get_logger("boom_plugin.gold_treasure")

STATE_FILE = os.path.join(os.path.dirname(__file__), "gold_treasure_state.json")


def _ensure_state_file():
	if not os.path.exists(STATE_FILE):
		os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
		with open(STATE_FILE, "w", encoding='utf-8') as f:
			json.dump({"active": False}, f, ensure_ascii=False)


def _load_state() -> dict:
	_ensure_state_file()
	# 使用基于锁文件的互斥，兼容 Windows/Posix
	lock_path = STATE_FILE + ".lock"
	_acquired = False
	try:
		# 尝试获取锁
		_acquired = _acquire_lock(lock_path)
		with open(STATE_FILE, "r", encoding='utf-8') as f:
			return json.load(f)
	except Exception:
		return {"active": False}
	finally:
		if _acquired:
			_release_lock(lock_path)


def _save_state(state: dict):
	# 在写操作时也要持有锁
	lock_path = STATE_FILE + ".lock"
	_acquired = False
	try:
		_acquired = _acquire_lock(lock_path)
		tmp = STATE_FILE + ".tmp"
		with open(tmp, "w", encoding='utf-8') as f:
			json.dump(state, f, indent=4, ensure_ascii=False)
		os.replace(tmp, STATE_FILE)
	finally:
		if _acquired:
			_release_lock(lock_path)


def _acquire_lock(lock_path: str, timeout: float = 5.0, poll: float = 0.05) -> bool:
	"""通过创建一个排他性锁文件来实现互斥。返回是否获取成功。

	这是一个跨平台的简单实现：尝试创建 lock 文件，失败则轮询直到超时。
	"""
	import time
	waited = 0.0
	while True:
		try:
			# 使用 os.O_EXCL 确保原子创建
			fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
			try:
				# 写入当前进程 id 作为调试信息
				os.write(fd, str(os.getpid()).encode('utf-8'))
			finally:
				os.close(fd)
			return True
		except FileExistsError:
			if waited >= timeout:
				return False
			time.sleep(poll)
			waited += poll
			continue
		except Exception:
			# 如果其他错误，记录并返回 False
			logger.exception("获取状态文件锁时出错")
			return False


def _release_lock(lock_path: str):
	try:
		if os.path.exists(lock_path):
			os.remove(lock_path)
	except Exception:
		logger.exception("释放状态文件锁时出错")


class GoldTreasureHelpCommand(BaseCommand):
	command_name = "gold_treasure_help"
	command_description = "查看金币宝藏规则"
	command_pattern = r"^.金币宝藏$"

	async def execute(self) -> Tuple[bool, Optional[str], bool]:
		help_text = (
			"金币宝藏规则：\n"
			"1. .埋宝藏 <金币数量> 开始一局（最低1000金币）\n"
			"2. .挖宝藏 <数字> 消耗10金币挖掘，命中宝藏获得奖池；命中地雷则向宝藏主人支付 宝藏价值/10\n"
			"3. .快速挖宝藏 <起> <止> 一次性触发区间内所有数字（逐个结算）\n"
			"4. 宝藏位置与10个地雷在1-100中随机生成；触发10个地雷或找到宝藏回合结束"
		)
		await self.send_text(help_text)
		return True, "查看金币宝藏规则成功", False


class BuryTreasureCommand(BaseCommand):
	command_name = "bury_treasure"
	command_description = "埋藏宝藏"
	command_pattern = r"^.埋宝藏 (?P<amount>\d+)$"

	async def execute(self) -> Tuple[bool, Optional[str], bool]:
		amount_str = self.matched_groups.get("amount")
		if not amount_str or not amount_str.isdigit():
			return False, "金额无效", False
		amount = int(amount_str)
		if amount < 1000:
			await self.send_text("埋藏宝藏太少了会被风吹走啊，最低埋1000个金币吧！")
			return False, "埋藏宝藏金额太少", False

		try:
			platform = getattr(self.message.message_info, "platform", "")
			user_info = getattr(self.message.message_info, "user_info", None)
			if not user_info:
				return False, "无法获取用户信息", False
			uid = person_api.get_person_id(platform, user_info.user_id)
		except Exception as e:
			logger.error(f"获取 person_id 失败: {e}")
			return False, "无法获取用户信息", False

		# 检查当前是否已有活动回合
		state = _load_state()
		if state.get("active"):
			await self.send_text("找宝藏的活动已经开始了，先去找找看吧")
			return False, "已有活动回合", False

		# 检查提交者金币
		cur = BoomDataManager.get_gold(uid)
		if cur < amount:
			await self.send_text(f"你的金币不足以埋藏{amount}，当前只有{cur}金币")
			return False, "金币不足", False

		# 扣除并创建回合
		BoomDataManager.add_gold(uid, -amount)
		treasure_number = random.randint(1, 100)
		# 生成 10 个地雷，确保不包含宝藏位置
		mines = set()
		while len(mines) < 10:
			m = random.randint(1, 100)
			if m == treasure_number:
				continue
			mines.add(m)

		state = {
			"active": True,
			"owner_uid": uid,
			"treasure_amount": amount,
			"treasure_number": treasure_number,
			"mines": sorted(list(mines)),
			"triggered_mines": [],
			"found": False,
		}
		_save_state(state)
		await self.send_text(f"刚刚有人埋了{amount}个金币的宝藏，大家快去找吧！")
		return True, "埋藏宝藏成功", False


def _ensure_can_pay(uid: int, cost: int) -> Tuple[bool, int]:
	cur = BoomDataManager.get_gold(uid)
	return (cur >= cost, cur)


class DigTreasureCommand(BaseCommand):
	command_name = "dig_treasure"
	command_description = "挖宝藏"
	command_pattern = r"^.挖宝藏 (?P<num>\d+)$"

	async def execute(self) -> Tuple[bool, Optional[str], bool]:
		num_str = self.matched_groups.get("num")
		if not num_str or not num_str.isdigit():
			return False, "数字无效", False
		num = int(num_str)
		if not (1 <= num <= 100):
			await self.send_text("请输入1到100之间的数字")
			return False, "数字范围错误", False

		try:
			platform = getattr(self.message.message_info, "platform", "")
			user_info = getattr(self.message.message_info, "user_info", None)
			if not user_info:
				return False, "无法获取用户信息", False
			uid = person_api.get_person_id(platform, user_info.user_id)
		except Exception as e:
			logger.error(f"获取 person_id 失败: {e}")
			return False, "无法获取用户信息", False

		state = _load_state()
		if not state.get("active"):
			await self.send_text("当前没有正在进行的宝藏回合")
			return False, "无活动回合", False

		# 支付挖掘费用 10 金币
		cost = 10
		can_pay, cur = _ensure_can_pay(uid, cost)
		if not can_pay:
			await self.send_text(f"挖掘需要{cost}金币，你只有{cur}金币")
			return False, "金币不足", False
		BoomDataManager.add_gold(uid, -cost)

		# 已经被触发过的位置（避免重复扣费但允许多次挖同一位）
		if state.get("found"):
			await self.send_text("本回合宝藏已被找到，等待结算")
			return False, "已找到宝藏", False

		# 命中宝藏
		if num == state.get("treasure_number"):
			# 发现者获得奖池
			amount = int(state.get("treasure_amount", 0))
			BoomDataManager.add_gold(uid, amount)
			state["found"] = True
			state["active"] = False
			_save_state(state)
			await self.send_text(f"恭喜！你挖到了宝藏，获得{amount}金币！")
			return True, "找到宝藏", False

		# 命中地雷
		if num in state.get("mines", []):
			# 如果已触发过该地雷，不再重复计入触发数量，但仍不额外收费（已经扣除10金币）
			if num in state.get("triggered_mines", []):
				await self.send_text("这个位置的地雷已经被触发过了，什么也没有发生")
				return False, "地雷已触发", False

			# 需要向宝藏主人支付 treasure_amount // 10
			penalty = max(1, int(state.get("treasure_amount", 0) // 10))
			can_pay_penalty, cur2 = _ensure_can_pay(uid, penalty)
			if not can_pay_penalty:
				# 如果支付不起罚款，只触发地雷并将罚款为100
				penalty = 100
			else:
				BoomDataManager.add_gold(uid, -penalty)
				BoomDataManager.add_gold(state.get("owner_uid"), penalty)

			state.setdefault("triggered_mines", []).append(num)
			# 检查是否触发了10个地雷
			if len(state.get("triggered_mines", [])) >= 10:
				# 结束回合，退还奖池给发起者
				owner = state.get("owner_uid")
				pot = int(state.get("treasure_amount", 0))
				BoomDataManager.add_gold(owner, pot)
				state["active"] = False
				_save_state(state)
				await self.send_text(f"不幸！第10个地雷被触发，回合结束，奖池已退还给宝藏主人。")
				return True, "触发第10个地雷，回合结束", False

			_save_state(state)
			await self.send_text(f"哎呀，你踩到地雷被炸死了！宝藏主人从你的残骸里找到了{penalty}金币。当前已触发{len(state.get('triggered_mines', []))}个地雷。")
			return False, "踩到地雷", False

		# 普通的空地，记录已挖位置后返回
		dug = set(state.get("dug_positions", []))
		if num not in dug:
			dug.add(num)
			state["dug_positions"] = sorted(list(dug))
			_save_state(state)
		await self.send_text("这里什么也没有，继续努力！")
		return False, "未命中", False


class FastDigTreasureCommand(BaseCommand):
    command_name = "fast_dig_treasure"
    command_description = "快速挖宝藏（范围）"
    # 支持两种格式："起 止" 或 "起-止"，并允许可选空格及多种连字符
    command_pattern = r"^.快速挖宝藏\s*(?P<start>\d+)[\s\-–—,;]*(?P<end>\d+)$"
    async def execute(self) -> Tuple[bool, Optional[str], bool]:
            start = self.matched_groups.get("start")
            end = self.matched_groups.get("end")
            if not (start and end and start.isdigit() and end.isdigit()):
                return False, "参数无效", False
            a = int(start); b = int(end)
            if a > b:
                a, b = b, a
            a = max(1, min(100, a)); b = max(1, min(100, b))
            try:
                platform = getattr(self.message.message_info, "platform", "")
                user_info = getattr(self.message.message_info, "user_info", None)
                if not user_info:
                    return False, "无法获取用户信息", False
                uid = person_api.get_person_id(platform, user_info.user_id)
            except Exception as e:
                logger.error(f"获取 person_id 失败: {e}")
                return False, "无法获取用户信息", False

            msgs: List[str] = []
            # 逐个调用挖掘逻辑，但避免重复读取/写入文件太多次：简单实现为多次调用 Dig 命令逻辑
            for num in range(a, b + 1):
                # 对每个数字构造独立的 Dig 命令实例，确保 matched_groups 在该实例上
                dig_cmd = DigTreasureCommand(self.message)
                dig_cmd.matched_groups = {"num": str(num)}
                # 临时替换 send_text，收集所有子命令的输出，避免刷屏
                collected: List[str] = []
                async def _collect(text: str):
                    collected.append(text)
                # 备份原始方法
                _orig_send = getattr(dig_cmd, 'send_text', None)
                dig_cmd.send_text = _collect
                ok, msg, _ = await dig_cmd.execute()
                # 恢复原始 send_text
                if _orig_send is not None:
                    dig_cmd.send_text = _orig_send
                # 使用 collected 中的消息作为显示内容，若为空则使用返回的 msg
                if collected:
                    for m in collected:
                        msgs.append(f"挖{num}: {m}")
                else:
                    msgs.append(f"挖{num}: {msg}")
                state = _load_state()
                if not state.get("active"):
                    break

            await self.send_text("\n".join(msgs))
            return True, "快速挖掘完成", False


class ShowLandCommand(BaseCommand):
	command_name = "show_land"
	command_description = "查看未被挖掘的土地（10x10 网格）"
	command_pattern = r"^.查看土地$"

	async def execute(self) -> Tuple[bool, Optional[str], bool]:
		state = _load_state()
		mines = set(state.get("mines", []))
		triggered = set(state.get("triggered_mines", []))
		dug = set(state.get("dug_positions", []))

		lines = []
		for row in range(10):
			cols = []
			for col in range(10):
				num = row * 10 + col + 1
				if num in triggered and num in mines:
					cols.append("X")
				elif num in dug:
					cols.append("*")
				else:
					cols.append(str(num))
			lines.append(" ".join(cols))

		await self.send_text("\n".join(lines))
		return True, "显示土地成功", False

