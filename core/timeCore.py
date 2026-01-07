import time
import heapq
import threading
from enum import Enum
from typing import Callable, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta

class TaskType(Enum):
    """任务类型枚举"""
    ONCE = "once"           # 一次性任务
    INTERVAL = "interval"   # 间隔任务
    DAILY = "daily"         # 每日任务

@dataclass(order=True)
class ScheduledTask:
    """定时任务类"""
    next_run: float  # 下次执行时间（时间戳）
    task_id: int = field(compare=False)
    task_type: TaskType = field(compare=False)
    func: Callable = field(compare=False)
    args: Tuple = field(default=(), compare=False)
    kwargs: dict = field(default_factory=dict, compare=False)
    
    # 间隔任务专用
    interval: Optional[float] = field(default=None, compare=False)  # 间隔秒数
    
    # 每日任务专用
    daily_time: Optional[Tuple[int, int, int]] = field(default=None, compare=False)  # (时,分,秒)
    
    # 任务状态
    enabled: bool = field(default=True, compare=False)
    last_run: Optional[float] = field(default=None, compare=False)

class TaskScheduler:
    """游戏定时任务调度器"""
    
    # 全局调度器实例，用于装饰器
    _global_instance = None
    _pending_decorated_tasks = []  # 存储待注册的装饰器任务
    
    def __init__(self, time_scale: float = 1.0):
        """
        初始化任务调度器
        
        Args:
            time_scale: 时间缩放因子，用于调试（1.0为正常时间）
        """
        self.tasks = []  # 使用最小堆存储任务
        self.task_counter = 0  # 任务ID计数器
        self.running = False
        self.scheduler_thread = None
        self.time_scale = time_scale
        self.lock = threading.RLock()
        
        # 如果这是第一个实例，设置为全局实例
        if TaskScheduler._global_instance is None:
            TaskScheduler._global_instance = self
            # 注册所有待处理的装饰器任务
            self._register_pending_tasks()
        
    def start(self):
        """启动调度器"""
        if self.running:
            return
            
        self.running = True
        self.scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            daemon=True,
            name="TaskScheduler"
        )
        self.scheduler_thread.start()
        print(f"任务调度器已启动，当前有 {len(self.tasks)} 个任务")
        
        # 输出所有任务信息
        for task in self.tasks:
            print(f"  - 任务 {task.task_id}: {task.func.__name__}, 下次执行: {datetime.fromtimestamp(task.next_run)}")
    
    def stop(self):
        """停止调度器"""
        self.running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=2)
        print("任务调度器已停止")
    
    def add_task(
        self,
        func: Callable,
        task_type: TaskType,
        delay: float = 0,
        interval: Optional[float] = None,
        daily_time: Optional[Tuple[int, int, int]] = None,
        args: Tuple = (),
        kwargs: dict = None
    ) -> int:
        """
        添加定时任务
        
        Args:
            func: 要执行的函数
            task_type: 任务类型
            delay: 延迟执行时间（秒）
            interval: 间隔时间（秒，仅用于INTERVAL类型）
            daily_time: 每日执行时间 (时,分,秒)，仅用于DAILY类型
            args: 函数位置参数
            kwargs: 函数关键字参数
            
        Returns:
            任务ID，可用于取消任务
        """
        with self.lock:
            task_id = self.task_counter
            self.task_counter += 1
            
            # 计算下次执行时间
            current_time = time.time()
            next_run = current_time + delay
            
            if task_type == TaskType.DAILY and daily_time:
                next_run = self._calculate_next_daily_time(daily_time)
            
            task = ScheduledTask(
                next_run=next_run,
                task_id=task_id,
                task_type=task_type,
                func=func,
                args=args,
                kwargs=kwargs or {},
                interval=interval,
                daily_time=daily_time
            )
            
            heapq.heappush(self.tasks, task)
            print(f"任务 {task_id} 已添加，类型: {task_type.value}，下次执行: {datetime.fromtimestamp(next_run)}")
            return task_id
    
    def add_once_task(self, func: Callable, delay: float = 0, args: Tuple = (), kwargs: dict = None) -> int:
        """添加一次性任务"""
        return self.add_task(
            func=func,
            task_type=TaskType.ONCE,
            delay=delay,
            args=args,
            kwargs=kwargs
        )
    
    def add_interval_task(self, func: Callable, interval: float, delay: float = 0, 
                         args: Tuple = (), kwargs: dict = None) -> int:
        """添加间隔任务（如每6分钟执行）"""
        return self.add_task(
            func=func,
            task_type=TaskType.INTERVAL,
            delay=delay,
            interval=interval,
            args=args,
            kwargs=kwargs
        )
    
    def add_daily_task(self, func: Callable, hour: int, minute: int = 0, second: int = 0,
                      args: Tuple = (), kwargs: dict = None) -> int:
        """添加每日任务（如每天0点执行）"""
        return self.add_task(
            func=func,
            task_type=TaskType.DAILY,
            daily_time=(hour, minute, second),
            args=args,
            kwargs=kwargs
        )
    
    def cancel_task(self, task_id: int) -> bool:
        """取消任务"""
        with self.lock:
            for i, task in enumerate(self.tasks):
                if task.task_id == task_id:
                    task.enabled = False
                    # 从堆中移除（惰性删除，在执行时跳过）
                    return True
            return False
    
    def get_pending_tasks(self) -> list:
        """获取等待执行的任务列表"""
        with self.lock:
            return [
                {
                    'task_id': task.task_id,
                    'type': task.task_type.value,
                    'next_run': datetime.fromtimestamp(task.next_run),
                    'enabled': task.enabled
                }
                for task in sorted(self.tasks)
            ]
    
    def get_task_next_run(self, func: Callable) -> Optional[datetime]:
        """获取特定函数的下次执行时间
        
        Args:
            func: 要查询的函数
            
        Returns:
            下次执行时间的 datetime 对象，如果未找到则返回 None
        """
        with self.lock:
            for task in self.tasks:
                if task.func == func and task.enabled:
                    return datetime.fromtimestamp(task.next_run)
            return None
    
    def _calculate_next_daily_time(self, daily_time: Tuple[int, int, int]) -> float:
        """计算下一次每日任务执行时间"""
        hour, minute, second = daily_time
        now = datetime.now()
        
        # 构造今天的执行时间
        target_time = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
        
        # 如果今天的时间已经过了，就安排在明天
        if now >= target_time:
            target_time += timedelta(days=1)
        
        return target_time.timestamp()
    
    def _scheduler_loop(self):
        """调度器主循环"""
        while self.running:
            try:
                self._process_tasks()
                time.sleep(0.1 * self.time_scale)  # 每100ms检查一次
            except Exception as e:
                print(f"调度器错误: {e}")
    
    def _process_tasks(self):
        """处理到达执行时间的任务"""
        current_time = time.time()
        
        with self.lock:
            while self.tasks and self.tasks[0].next_run <= current_time:
                task = heapq.heappop(self.tasks)
                
                if not task.enabled:
                    continue  # 任务已被取消
                
                # 执行任务
                try:
                    task.last_run = current_time
                    print(f"执行任务 {task.task_id}: {task.func.__name__}")
                    task.func(*task.args, **task.kwargs)
                    print(f"任务 {task.task_id} ({task.func.__name__}) 执行完成")
                except Exception as e:
                    print(f"任务 {task.task_id} ({task.func.__name__}) 执行失败: {e}")
                    import traceback
                    traceback.print_exc()
                
                # 重新调度任务（如果需要）
                if task.task_type != TaskType.ONCE and task.enabled:
                    if task.task_type == TaskType.INTERVAL and task.interval:
                        task.next_run = current_time + task.interval
                        heapq.heappush(self.tasks, task)
                    elif task.task_type == TaskType.DAILY and task.daily_time:
                        task.next_run = self._calculate_next_daily_time(task.daily_time)
                        heapq.heappush(self.tasks, task)
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
    
    def _register_pending_tasks(self):
        """注册所有通过装饰器定义的待处理任务"""
        print(f"开始注册装饰器任务，待处理任务数: {len(TaskScheduler._pending_decorated_tasks)}")
        
        for task_info in TaskScheduler._pending_decorated_tasks:
            task_type = task_info['type']
            func = task_info['func']
            kwargs = task_info['kwargs']
            
            print(f"注册任务: {func.__name__}, 类型: {task_type}, 参数: {kwargs}")
            
            if task_type == 'interval':
                self.add_interval_task(func, **kwargs)
            elif task_type == 'daily':
                self.add_daily_task(func, **kwargs)
            elif task_type == 'once':
                self.add_once_task(func, **kwargs)
        
        print(f"装饰器任务注册完成，当前任务总数: {len(self.tasks)}")
        
        # 清空待处理列表
        TaskScheduler._pending_decorated_tasks.clear()
    
    @classmethod
    def interval_task(cls, minutes: int = 0, seconds: int = 0, hours: int = 0):
        """装饰器：注册间隔任务
        
        Args:
            minutes: 间隔分钟数
            seconds: 间隔秒数
            hours: 间隔小时数
            
        示例:
            @TaskScheduler.interval_task(minutes=30)
            def save_data():
                print("保存数据")
        """
        interval = hours * 3600 + minutes * 60 + seconds
        
        def decorator(func):
            # 将任务信息添加到待处理列表
            cls._pending_decorated_tasks.append({
                'type': 'interval',
                'func': func,
                'kwargs': {'interval': interval}
            })
            
            # 如果全局实例已经存在，立即注册
            if cls._global_instance is not None:
                cls._global_instance.add_interval_task(func, interval=interval)
            
            return func
        return decorator
    
    @classmethod
    def daily_task(cls, hour: int, minute: int = 0, second: int = 0):
        """装饰器：注册每日任务
        
        Args:
            hour: 小时 (0-23)
            minute: 分钟 (0-59)
            second: 秒 (0-59)
            
        示例:
            @TaskScheduler.daily_task(hour=0, minute=0)
            def daily_reset():
                print("每日重置")
        """
        def decorator(func):
            cls._pending_decorated_tasks.append({
                'type': 'daily',
                'func': func,
                'kwargs': {'hour': hour, 'minute': minute, 'second': second}
            })
            
            if cls._global_instance is not None:
                cls._global_instance.add_daily_task(func, hour=hour, minute=minute, second=second)
            
            return func
        return decorator
    
    @classmethod
    def once_task(cls, delay: float = 0):
        """装饰器：注册一次性任务
        
        Args:
            delay: 延迟执行时间（秒）
            
        示例:
            @TaskScheduler.once_task(delay=10)
            def startup_task():
                print("启动后10秒执行")
        """
        def decorator(func):
            cls._pending_decorated_tasks.append({
                'type': 'once',
                'func': func,
                'kwargs': {'delay': delay}
            })
            
            if cls._global_instance is not None:
                cls._global_instance.add_once_task(func, delay=delay)
            
            return func
        return decorator