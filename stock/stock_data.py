'''
stock数据处理模块
负责管理和操作stock相关的数据，包括读取、写入和更新stock信息。提供方法供core调用

提供方法：
1. 获取stock信息
2. 更新stock信息
'''
import json
import os
from ..core import logCore
from ..core import timeCore
from datetime import datetime

# 获取插件目录的绝对路径
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PLUGIN_DIR, 'data')
STOCK_DATA_FILE = os.path.join(DATA_DIR, 'stock_data.json')

#stock结构体
class Stock:
    def __init__(self, stock_id, stock_name, stock_price, stock_type, stock_owner, stock_base_price,
                 price_fluctuation_positive=0.05, price_fluctuation_negative=0.05,
                 price_fluctuation_reserve=0.00, price_fluctuation_max=0.20, price_history=None):
        self.stock_id = stock_id
        self.stock_name = stock_name
        self.stock_price = stock_price

        #stock_type: 股票类型，官方/用户
        self.stock_type = stock_type
        #stock_owner: 股票拥有者，官方/用户ID
        self.stock_owner = stock_owner
        #stock_base_price : 股票基准价格
        self.stock_base_price = stock_base_price

        #交易费率
        self.transaction_fee_rate = 0.05 #[0.01,0.2]

        #价格波动正值
        self.price_fluctuation_positive = price_fluctuation_positive
        #价格波动负值
        self.price_fluctuation_negative = price_fluctuation_negative
        #价格波动储备值
        self.price_fluctuation_reserve = price_fluctuation_reserve
        #价格波动最大转移值
        self.price_fluctuation_max = price_fluctuation_max
        
        # price_history: 价格历史记录，列表，存储最近的价格变动
        self.price_history = price_history if price_history is not None else []



# 全局变量，存储stock数据
stock_data = {}

# 加载stock数据到内存
def load_stock_data(file_path=None):
    """加载stock数据到内存"""
    global stock_data
    
    if file_path is None:
        file_path = STOCK_DATA_FILE
    
    # 确保目录存在
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    #确保文件存在,如果不存在则创建新文件，添加数条股票
    if not os.path.exists(file_path):
        logCore.log_write(f'stock数据不存在，创建新的stock数据到 {file_path}')
        
        # 初始化空的 stock_data
        stock_data = {}
        
        # 添加数条默认股票
        default_stocks = [
            {"stock_id": "01", "stock_name": "麦麦金币", "stock_price": 1200, "stock_type": "官方", "stock_owner": "官方", "stock_base_price": 1000},
            {"stock_id": "02", "stock_name": "哈吉流动", "stock_price": 250, "stock_type": "官方", "stock_owner": "官方", "stock_base_price": 150},
            {"stock_id": "03", "stock_name": "微硬", "stock_price": 600, "stock_type": "官方", "stock_owner": "官方", "stock_base_price": 500},
            {"stock_id": "04", "stock_name": "能人智工", "stock_price": 300, "stock_type": "官方", "stock_owner": "官方", "stock_base_price": 200},
            {"stock_id": "05", "stock_name": "平果", "stock_price": 500, "stock_type": "官方", "stock_owner": "官方", "stock_base_price": 350}
        ]
        
        for stock in default_stocks:
            add_new_stock(stock["stock_id"], stock["stock_name"], stock["stock_price"], 
                         stock["stock_type"], stock["stock_owner"], stock["stock_base_price"])
        
        # 保存到文件
        save_stock_data(file_path)
        logCore.log_write(f'默认股票数据已创建并保存到 {file_path}，共 {len(stock_data)} 支股票')
    else:
        #加载stock数据到内存
        with open(file_path, 'r', encoding='utf-8') as f:
            stock_data = json.load(f)
            logCore.log_write(f'stock数据从 {file_path} 加载到内存，共 {len(stock_data)} 支股票')
    

@timeCore.TaskScheduler.interval_task(minutes=30)  # 每30分钟执行一次
def save_stock_data(file_path=None):
    """保存内存中的stock数据到文件"""
    global stock_data
    
    if file_path is None:
        file_path = STOCK_DATA_FILE
    
    # 如果stock_data为空，说明数据还未加载，不执行保存
    if not stock_data:
        logCore.log_write(f'stock数据为空，跳过保存操作', logCore.LogLevel.WARNING)
        return
    
    # 确保目录存在
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(stock_data, f, ensure_ascii=False, indent=4)
        logCore.log_write(f'stock数据保存到 {file_path}，共 {len(stock_data)} 支股票')

# 获取stock信息
def get_stock_by_id(stock_id: str) -> Stock:
    """根据stock ID获取stock信息"""
    global stock_data
    stock_info = stock_data.get(str(stock_id))
    if stock_info:
        return Stock(
            stock_id=stock_info['stock_id'],
            stock_name=stock_info['stock_name'],
            stock_price=int(stock_info['stock_price']),  # 强制转换为整数
            stock_type=stock_info['stock_type'],
            stock_owner=stock_info['stock_owner'],
            stock_base_price=stock_info['stock_base_price'],
            price_fluctuation_positive=stock_info.get('price_fluctuation_positive', 0.05),
            price_fluctuation_negative=stock_info.get('price_fluctuation_negative', 0.05),
            price_fluctuation_reserve=stock_info.get('price_fluctuation_reserve', 0.00),
            price_fluctuation_max=stock_info.get('price_fluctuation_max', 0.20),
            price_history=stock_info.get('price_history', [])   
        )
    return None

#根据id获取stoc——kname
def get_stock_name_by_id(stock_id: str) -> str:
    """根据stock ID获取stock名称"""
    global stock_data
    stock_info = stock_data.get(str(stock_id))
    if stock_info:
        return stock_info.get('stock_name', '未知股票')
    return '未知股票'

# 更新stock价格，并储存上一条价格记录,储存格式为: *月**日*时*分 价格,最多存储10条记录
def update_stock_price(stock_id: str, new_price: float,nowtime: datetime):
    """更新stock价格"""
    global stock_data
    stock_info = stock_data.get(str(stock_id))
    if stock_info:
        #储存上一条价格记录
        timestamp = nowtime.strftime('%m月%d日%H时%M分')
        price_record = f"{timestamp} {stock_info['stock_price']}$"
        price_history = stock_info.get('price_history', [])
        price_history.append(price_record)
        #最多存储10条记录
        if len(price_history) > 10:
            price_history = price_history[-10:]
        stock_info['price_history'] = price_history
        
        #更新价格
        stock_info['stock_price'] = new_price
        logCore.log_write(f'stock ID {stock_id} 价格更新: {new_price}$')
        return True
    return False


# 获取stock价格历史记录
def get_stock_price_history(stock_id: str) -> list:
    """获取stock价格历史记录"""
    global stock_data
    stock_info = stock_data.get(str(stock_id))
    if stock_info:
        return stock_info.get('price_history', [])
    return []

# 添加新stock
def add_new_stock(stock_id: str, stock_name: str, stock_price: float,stock_type: str,stock_owner: str,stock_base_price: float):
    """添加新stock"""
    global stock_data
    if str(stock_id) in stock_data:
        logCore.log_write(f'stock ID {stock_id} 已存在，无法添加新stock', logCore.LogLevel.ERROR)
        return False
    stock_data[str(stock_id)] = {
        'stock_id': stock_id,
        'stock_name': stock_name,
        'stock_price': stock_price,
        'stock_type': stock_type,
        'stock_owner': stock_owner,
        'stock_base_price': stock_base_price,
        'price_fluctuation_positive': 0.05,
        'price_fluctuation_negative': 0.05,
        'price_fluctuation_reserve': 0.00,
        'price_fluctuation_max': 0.20,
        'price_history': []
    }
    logCore.log_write(f'新stock添加成功: {stock_id} {stock_name}')
    return True