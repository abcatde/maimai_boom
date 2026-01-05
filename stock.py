import os
import json
import datetime
from typing import Optional
from src.common.logger import get_logger

logger = get_logger("boom_plugin")


#确保stock_data.json文件存在
DATA_FILE = os.path.join(os.path.dirname(__file__), "stock_data.json")

# module-level scheduler/job id 保存，方便在其它位置（如 command）不传 scheduler 时回退使用
_SCHEDULER = None
_UPDATE_JOB_ID = "update_prices"
# 每次价格更新从权重储备中取出的比例（例如 0.2 表示每次取出 20%）
APPLY_FRACTION = 0.2
if not os.path.exists(DATA_FILE):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump({}, f, ensure_ascii=False)

#股票结构体
class Stock:
    def __init__(self, symbol: str, name: str, price: float):
        self.symbol = symbol  # 股票代码
        self.name = name      # 股票名称
        self.price = price    # 当前价格


#查询stock_data.json中股票当前价格
def get_stock_price(symbol: str) -> float:
    with open(DATA_FILE, "r", encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            data = {}
    stock_info = data.get(symbol)
    if stock_info:
        return stock_info['price']
    return 0.0

#查询股票信息
def get_stock_info(symbol: str) -> Optional[Stock]:
    with open(DATA_FILE, "r", encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            data = {}
    stock_info = data.get(symbol)
    if stock_info:
        return Stock(symbol, stock_info['name'], stock_info['price'])
    return None

#更新股票价格，储存上一个价格，如果大于30个价格则删除最早的价格
def update_stock_price(symbol: str, name: str, new_price: float):
    with open(DATA_FILE, "r", encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            data = {}
    now_iso = datetime.datetime.now().isoformat()
    if symbol not in data:
        data[symbol] = {
            'name': name,
            'price': new_price,
            'history': []
        }
    else:
        # 保存历史价格（带时间戳），兼容旧的只保存价格的格式
        history = data[symbol].get('history', [])
        prev_price = data[symbol].get('price')
        if prev_price is not None:
            # 存为 dict 以记录时间和价格
            history.append({'time': now_iso, 'price': prev_price})
        # 保持最多 10 条历史
        if len(history) > 10:
            history = history[-10:]
        data[symbol]['history'] = history
        data[symbol]['price'] = new_price

    with open(DATA_FILE, "w", encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

 

    #创建长期任务，修改json储存，最低结果为0
def schedule_stock_price_updates(scheduler):
    import random

    async def update_prices():
        with open(DATA_FILE, "r", encoding='utf-8') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = {}

        # 为现有股票确保默认属性：official 和 owner
        changed = False
        for sym, info in list(data.items()):
            if 'official' not in info:
                data[sym]['official'] = True
                changed = True
            if 'owner' not in info:
                data[sym]['owner'] = 'official'
                changed = True
        if changed:
            with open(DATA_FILE, "w", encoding='utf-8') as wf:
                json.dump(data, wf, indent=4, ensure_ascii=False)
        # 对所有股票在内存中计算更新，最后一次性写回文件，避免反复读写导致覆盖或并发问题
        for symbol, info in list(data.items()):
            base_change = random.uniform(-0.2, 0.2)  # -20% 到 +20%
            # 如果是官方股票且价格低于100，则按价格低于100的程度增加权重储备
            # 公式：bonus = (100 - price) * 0.1，当 price < 100 时生效
            try:
                if info.get('official') and float(info.get('price', 0)) < 100:
                    bonus = (100 - float(info.get('price', 0))) * 0.1
                    data[symbol]['weight'] = float(info.get('weight', 0) or 0.0) + bonus
                    # 更新本地 info 以使用新的权重
                    info = data[symbol]
            except Exception:
                logger.exception("为官方股票添加权重 bonus 时出错")

            # 权重储备（可能为正或负），每次取出一部分 applied 参与本次价格变动
            weight_reservoir = float(info.get('weight', 0) or 0.0)
            applied = weight_reservoir * APPLY_FRACTION
            change_percent = base_change + applied
            # 计算新价格并在内存中更新历史与价格，不立即写入磁盘
            old_price = float(info.get('price', 0) or 0)
            new_price = max(1, int(old_price * (1 + change_percent)))
            # 扣减已应用的储备
            data[symbol]['weight'] = weight_reservoir - applied
            # 更新历史（保存旧价）并截断到最近10条
            now_iso = datetime.datetime.now().isoformat()
            history = info.get('history', []) or []
            if old_price is not None:
                history.append({'time': now_iso, 'price': old_price})
            if len(history) > 10:
                history = history[-10:]
            data[symbol]['history'] = history
            data[symbol]['price'] = new_price

        # 一次性持久化所有变化
        with open(DATA_FILE, "w", encoding='utf-8') as wf:
            json.dump(data, wf, indent=4, ensure_ascii=False)
            
        

    # 添加稳定的 job id/name 并返回 job
    # 注意：使用与查询一致的 id（'update_prices'），以便通过 id 可靠查找到该任务
    # 记录到模块变量，方便后续查询
    global _SCHEDULER
    _SCHEDULER = scheduler
    job = scheduler.add_job(update_prices, 'interval', hours=0.1, id=_UPDATE_JOB_ID, name=_UPDATE_JOB_ID, next_run_time=None)
    return job

    #获取下次更新价格时间
def get_next_update_time(scheduler) -> Optional[str]:
    """返回下次更新时间的可读字符串。

    如果未传入 `scheduler`，会回退到模块级 `_SCHEDULER`（如果已通过 schedule_stock_price_updates 注册）。
    返回示例："5分30秒后" 或 ISO 时间字符串，找不到则返回 None。
    """
    # 回退到模块级调度器
    if scheduler is None:
        scheduler = _SCHEDULER

    if scheduler is None:
        return None

    # 优先通过 get_job id 获取
    try:
        job = None
        get_job = getattr(scheduler, 'get_job', None)
        if callable(get_job):
            job = scheduler.get_job(_UPDATE_JOB_ID)
            if job is not None:
                nr = getattr(job, 'next_run_time', None)
                if nr:
                    return _format_next_run_time(nr)
    except Exception:
        pass

    # 回退：枚举所有 jobs，按 id/name 匹配
    try:
        jobs = scheduler.get_jobs()
    except Exception:
        jobs = []

    for job in jobs:
        if getattr(job, 'id', None) == _UPDATE_JOB_ID or getattr(job, 'name', None) == _UPDATE_JOB_ID:
            nr = getattr(job, 'next_run_time', None)
            if nr:
                return _format_next_run_time(nr)

    # 最后一招：返回所有 job 中最早的 next_run_time（如果存在）
    earliest = None
    for job in jobs:
        nr = getattr(job, 'next_run_time', None)
        if nr is None:
            continue
        if earliest is None or nr < earliest:
            earliest = nr
    return _format_next_run_time(earliest) if earliest is not None else None


def get_stock_price_history(symbol: str):
    """返回股票历史价格列表，格式为 [(time_str, price), ...]。

    兼容两种历史存储格式：
    - 旧格式：history 列表中为价格数字 -> 返回索引基础的占位时间
    - 新格式：history 列表中为 {'time': ..., 'price': ...}
    返回空列表表示无数据或 symbol 不存在。
    """
    try:
        with open(DATA_FILE, "r", encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

    stock_info = data.get(symbol)
    if not stock_info:
        return []

    history = stock_info.get('history', []) or []
    result = []
    # 处理已记录的历史条目（history 中为旧格式数字或新格式 dict）
    for entry in history:
        if isinstance(entry, dict):
            t = entry.get('time', '')
            p = entry.get('price')
            result.append((t, p))
        else:
            # 旧的仅数字格式，时间未知
            result.append(("", entry))

    # 不在查询时添加/存储当前价格（避免查询时写入或产生大量无意义记录）
    # 取最近 10 条（如果超过），并按升序（最旧->最近）返回
    if len(result) > 10:
        result = result[-10:]
    formatted = []
    for t_str, price in result:
        if t_str:
            try:
                dt = datetime.datetime.fromisoformat(t_str)
                time_fmt = f"{dt.month}月{dt.day}日{dt.hour}点{dt.minute}分"
            except Exception:
                time_fmt = "【未知时间】"
        else:
            time_fmt = "【未知时间】"
        formatted.append((time_fmt, price))

    return formatted



#历史价格
def _format_next_run_time(next_run_time: datetime.datetime) -> str:
    """将 datetime 转为相对时间字符串或 ISO 字符串。"""
    try:
        now = datetime.datetime.now(next_run_time.tzinfo) if next_run_time.tzinfo else datetime.datetime.now()
        delta = next_run_time - now
        secs = int(delta.total_seconds())
        if secs <= 0:
            return "即将更新"
        mins, sec = divmod(secs, 60)
        hours, mins = divmod(mins, 60)
        parts = []
        if hours:
            parts.append(f"{hours}小时")
        if mins:
            parts.append(f"{mins}分")
        if sec and not hours:
            parts.append(f"{sec}秒")
        if parts:
            return "".join(parts) + "后"
        return "少于1秒后"
    except Exception:
        return str(next_run_time)
    
