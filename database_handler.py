import sqlite3
import os
from datetime import datetime
from utils import user_data_path

class DatabaseHandler:
    """
    用于处理 SQLite 数据库操作的类。
    """
    def __init__(self, db_file='history.db', metric_keys=None):
        """
        初始化数据库处理器。
        
        Args:
            db_file (str): 数据库文件名。
            metric_keys (list): 健康数据指标的键列表（不含 created_at）。
        """
        self.db_file = user_data_path(db_file)
        self.metric_keys = metric_keys if metric_keys is not None else []
        self._init_db()

    def _init_db(self):
        """检查并初始化数据库和表。"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            columns_sql = ", ".join([f'"{key}" INTEGER' for key in self.metric_keys])
            if columns_sql:
                columns_sql = ", " + columns_sql
            
            create_table_sql = f"""
            CREATE TABLE IF NOT EXISTS health_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL{columns_sql}
            );
            """
            cursor.execute(create_table_sql)
            
            # 鼠标累计数据表：仅维护一行（id 固定为 1），保存最新累计值
            create_mouse_sql = """
            CREATE TABLE IF NOT EXISTS mouse_data (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                created_at TEXT NOT NULL,
                distance INTEGER NOT NULL DEFAULT 0,
                left_click INTEGER NOT NULL DEFAULT 0,
                mid_click INTEGER NOT NULL DEFAULT 0,
                right_click INTEGER NOT NULL DEFAULT 0
            );
            """
            cursor.execute(create_mouse_sql)
            
            # 报告数据表
            create_reports_sql = """
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                report_json TEXT,
                images_data TEXT
            );
            """
            cursor.execute(create_reports_sql)

            conn.commit()
            conn.close()
            print(f"数据库 '{self.db_file}' 初始化成功。")
        except sqlite3.Error as e:
            print(f"数据库初始化失败: {e}")
            raise # 向上抛出异常，让主程序知道

    def load_last_record(self) -> dict | None:
        """从数据库读取并返回最后一条历史数据"""
        if not os.path.exists(self.db_file):
            print(f"未找到数据库文件 '{self.db_file}'。")
            return None
            
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            columns_to_select = ['created_at'] + self.metric_keys
            cursor.execute(f"SELECT {', '.join(columns_to_select)} FROM health_data ORDER BY id DESC LIMIT 1")
            last_row = cursor.fetchone()
            conn.close()
            
            if last_row:
                # 将结果打包成字典
                all_keys = ['created_at'] + self.metric_keys
                return dict(zip(all_keys, last_row))
            else:
                return None
                
        except sqlite3.Error as e:
            print(f"从数据库读取失败: {e}")
            return None

    def save_record_if_new(self, new_data: list) -> bool:
        """
        比较新数据与数据库中的最后一条记录。
        仅在数据不同时才保存。返回是否保存了新数据。
        """
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute(f"SELECT {', '.join(self.metric_keys)} FROM health_data ORDER BY id DESC LIMIT 1")
            last_row = cursor.fetchone()
            conn.close()
            
            should_save = True
            if last_row:
                last_saved_values = list(last_row)
                if new_data == last_saved_values:
                    print("数据与上一条记录相同，跳过保存。")
                    should_save = False
            
            if should_save:
                self._save_to_history(new_data)
                return True
            return False
            
        except sqlite3.Error as e:
            print(f"比较历史数据时出错: {e}。将直接保存。")
            self._save_to_history(new_data)
            return True

    def _save_to_history(self, values: list):
        """将数据保存到数据库"""
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        columns = ['created_at'] + self.metric_keys
        placeholders = ', '.join(['?'] * (len(values) + 1))
        
        insert_sql = f"INSERT INTO health_data ({', '.join(columns)}) VALUES ({placeholders})"
        
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute(insert_sql, [now] + values)
            conn.commit()
            conn.close()
            print("数据已保存到数据库。")
        except sqlite3.Error as e:
            print(f"保存数据到数据库失败: {e}")

    # --- 鼠标数据相关 ---
    def save_or_update_mouse_data(self, distance: int, left_click: int, mid_click: int, right_click: int) -> None:
        """
        保存或更新鼠标累计数据（设备侧为累计值，这里只需同步最新值）。
        表设计为仅一行（id=1）。
        """
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO mouse_data (id, created_at, distance, left_click, mid_click, right_click)
                VALUES (1, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    created_at=excluded.created_at,
                    distance=excluded.distance,
                    left_click=excluded.left_click,
                    mid_click=excluded.mid_click,
                    right_click=excluded.right_click
                """,
                [now, distance, left_click, mid_click, right_click]
            )
            conn.commit()
            conn.close()
            print("鼠标累计数据已更新到数据库。")
        except sqlite3.Error as e:
            print(f"保存鼠标数据失败: {e}")

    def load_mouse_data(self) -> dict | None:
        """读取并返回保存的鼠标累计数据（单行）。"""
        if not os.path.exists(self.db_file):
            print(f"未找到数据库文件 '{self.db_file}'。")
            return None
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT created_at, distance, left_click, mid_click, right_click
                FROM mouse_data WHERE id = 1
                """
            )
            row = cursor.fetchone()
            conn.close()
            if row:
                created_at, distance, left_click, mid_click, right_click = row
                return {
                    'created_at': created_at,
                    'distance': distance,
                    'left_click': left_click,
                    'mid_click': mid_click,
                    'right_click': right_click,
                }
            return None
        except sqlite3.Error as e:
            print(f"读取鼠标数据失败: {e}")
            return None
