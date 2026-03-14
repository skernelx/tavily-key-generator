"""
API Key 轮询池
"""
import threading
from database import get_active_keys, update_key_usage


class KeyPool:
    def __init__(self):
        self._lock = threading.Lock()
        self._index = 0
        self._keys = []
        self._initialized = False

    def reload(self):
        with self._lock:
            self._keys = [dict(row) for row in get_active_keys()]
            if self._index >= len(self._keys):
                self._index = 0
            self._initialized = True

    def get_next_key(self):
        """Round-robin 返回下一个可用 key，返回 dict 或 None"""
        if not self._initialized:
            self.reload()
        with self._lock:
            if not self._keys:
                return None
            key = self._keys[self._index]
            self._index = (self._index + 1) % len(self._keys)
            return key

    def report_result(self, key_id, success):
        """记录使用结果，失败 3 次自动禁用并从池中移除"""
        update_key_usage(key_id, success)
        if not success:
            with self._lock:
                self._keys = [k for k in self._keys if k["id"] != key_id or k.get("consecutive_fails", 0) < 2]
                # 完整重载以获取最新状态
            self.reload()


# 全局单例
pool = KeyPool()
