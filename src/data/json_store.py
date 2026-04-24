"""
JSON 存储封装
提供统一的 JSON 文件读写接口，带缓存机制
"""

import json
import os
from pathlib import Path
from typing import Any, Optional, Dict
from copy import deepcopy


class JSONStore:
    """
    JSON 文件存储封装类
    
    特性:
    - 延迟加载: 首次访问时才读取文件
    - 写时保存: 修改数据后自动落盘
    - 缓存机制: 避免频繁 IO
    - 原子写入: 写入前备份，失败可恢复
    """

    def __init__(self, file_path: str, auto_save: bool = True):
        """
        Args:
            file_path: JSON 文件路径 (相对于插件目录)
            auto_save: 修改后是否自动保存
        """
        self.file_path = self._resolve_path(file_path)
        self.auto_save = auto_save
        self._cache: Optional[dict] = None
        self._loaded = False

    def _resolve_path(self, file_path: str) -> str:
        """解析为绝对路径"""
        if os.path.isabs(file_path):
            return file_path
        # 相对于插件根目录
        plugin_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        return os.path.join(plugin_root, file_path)

    def _load(self, force: bool = False) -> dict:
        """加载 JSON 文件"""
        if self._loaded and not force:
            return self._cache

        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    self._cache = json.load(f)
            except json.JSONDecodeError as e:
                # 文件损坏，尝试备份
                self._backup()
                self._cache = {}
                raise ValueError(f"JSON 文件损坏 ({self.file_path}): {e}")
        else:
            # 文件不存在，创建空数据
            self._ensure_dir()
            self._cache = {}

        self._loaded = True
        return self._cache

    def _ensure_dir(self):
        """确保目录存在"""
        dir_path = os.path.dirname(self.file_path)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)

    def _backup(self):
        """备份损坏的文件"""
        if os.path.exists(self.file_path):
            backup_path = self.file_path + '.backup'
            os.rename(self.file_path, backup_path)

    def _save(self):
        """保存到文件"""
        if not self.auto_save:
            return

        self._ensure_dir()

        # 原子写入: 先写临时文件，再重命名
        temp_path = self.file_path + '.tmp'
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, self.file_path)
        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise ValueError(f"保存 JSON 文件失败: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取值
        
        Args:
            key: 键，支持点分隔的路径如 "users.123.name"
            default: 默认值
        
        Returns:
            获取到的值或默认值
        """
        data = self._load()
        
        # 支持点分隔路径
        keys = key.split('.')
        for k in keys:
            if isinstance(data, dict):
                data = data.get(k)
                if data is None:
                    return default
            else:
                return default
        
        return data if data is not None else default

    def set(self, key: str, value: Any):
        """
        设置值 (整体替换)
        
        Args:
            key: 键
            value: 要设置的值
        """
        data = self._load()
        data[key] = value
        self._save()

    def update(self, key: str, updates: Dict):
        """
        更新字典中的字段
        
        Args:
            key: 键
            updates: 要更新的字段
        """
        data = self._load()
        target = data.get(key, {})
        if not isinstance(target, dict):
            target = {}
        target.update(updates)
        data[key] = target
        self._save()

    def delete(self, key: str, *keys: str):
        """
        删除键
        
        Args:
            key: 主键
            *keys: 点分隔的子键路径
        """
        data = self._load()
        
        if not keys:
            # 直接删除主键
            if key in data:
                del data[key]
        else:
            # 嵌套删除
            target = data.get(key, {})
            for k in keys[:-1]:
                if not isinstance(target, dict):
                    return
                target = target.get(k, {})
            
            if isinstance(target, dict) and keys[-1] in target:
                del target[keys[-1]]
        
        self._save()

    def get_all(self) -> dict:
        """获取完整数据副本"""
        return deepcopy(self._load())

    def set_all(self, data: dict):
        """设置完整数据"""
        self._cache = data
        self._loaded = True
        self._save()

    def reload(self):
        """强制重新加载"""
        self._loaded = False
        self._load(force=True)

    def exists(self, key: str) -> bool:
        """检查键是否存在"""
        return self.get(key) is not None

    @property
    def path(self) -> str:
        """返回文件路径"""
        return self.file_path
