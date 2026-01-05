import datetime
import json
import os
from typing import Optional


class BoomDataManager:
    """管理爆炸插件的数据（持久化到 boom_data.json）。

    该类为纯数据访问层，负责读写用户数据与简单的操作。将来可替换为数据库实现。
    """
    DATA_FILE = os.path.join(os.path.dirname(__file__), "boom_data.json")

    @staticmethod
    def _ensure_data_file():
        if not os.path.exists(BoomDataManager.DATA_FILE):
            os.makedirs(os.path.dirname(BoomDataManager.DATA_FILE), exist_ok=True)
            with open(BoomDataManager.DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump({}, f, ensure_ascii=False)

    @staticmethod
    def read_id(uid: int) -> bool:
        BoomDataManager._ensure_data_file()
        try:
            with open(BoomDataManager.DATA_FILE, "r", encoding='utf-8') as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return False

        return str(uid) in data

    @staticmethod
    def register_id(uid: int):
        BoomDataManager._ensure_data_file()
        try:
            with open(BoomDataManager.DATA_FILE, "r", encoding='utf-8') as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}

        data[str(uid)] = {
            "registered_at": str(datetime.datetime.now()),
            "gold": 10
        }

        with open(BoomDataManager.DATA_FILE, "w", encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    @staticmethod
    def add_gold(uid: int, amount: int):
        BoomDataManager._ensure_data_file()
        try:
            with open(BoomDataManager.DATA_FILE, "r", encoding='utf-8') as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return

        uid_str = str(uid)
        if uid_str not in data:
            BoomDataManager.register_id(uid)
            with open(BoomDataManager.DATA_FILE, "r", encoding='utf-8') as f:
                data = json.load(f)

        if "gold" not in data[uid_str] or not isinstance(data[uid_str]["gold"], int):
            data[uid_str]["gold"] = 0
        data[uid_str]["gold"] = max(0, data[uid_str]["gold"] + int(amount))

        with open(BoomDataManager.DATA_FILE, "w", encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    @staticmethod
    def get_gold(uid: int) -> int:
        BoomDataManager._ensure_data_file()
        try:
            with open(BoomDataManager.DATA_FILE, "r") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return 0

        uid_str = str(uid)
        if uid_str in data and "gold" in data[uid_str]:
            return data[uid_str]["gold"]
        return 0
