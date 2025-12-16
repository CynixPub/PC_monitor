import math
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QTableView, QHeaderView, 
    QHBoxLayout, QPushButton, QLabel, QStyledItemDelegate, QMenu, QApplication
)
from PySide6.QtSql import QSqlDatabase, QSqlQueryModel, QSqlQuery
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction

import constants as const

class CenteredDelegate(QStyledItemDelegate):
    """用于在 QTableView 中居中对齐所有文本的委托"""
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.displayAlignment = Qt.AlignCenter

class HistoryWindow(QDialog):
    """
    一个用于显示数据库历史数据的窗口。
    - 使用 QSqlQueryModel 实现分页加载
    - 固定窗口大小
    - 表格列宽自适应
    - 隐藏了 ID 列和行号
    """
    def __init__(self, db_path='history.db', parent=None):
        super().__init__(parent)
        self.setWindowTitle("历史数据")
        self.setFixedSize(900, 555) # 固定窗口大小，禁止拖动调整

        # --- 分页变量 ---
        self.current_page = 0
        self.page_size = 15  # 每页显示20条
        self.total_rows = 0
        self.total_pages = 0

        # --- 数据库连接 ---
        self.db = QSqlDatabase.addDatabase("QSQLITE", "history_connection")
        self.db.setDatabaseName(db_path)
        if not self.db.open():
            print(f"错误: 无法打开数据库 {db_path}")
            return
            
        self._get_total_rows()
        if self.total_rows > 0:
            self.total_pages = math.ceil(self.total_rows / self.page_size)
        
        # --- UI 初始化 ---
        self._setup_ui()
        self._go_to_page(1) # 跳转到第一页
        self._center_window()

    def _center_window(self):
        """将窗口移动到屏幕中心"""
        screen = QApplication.primaryScreen()
        if screen:
            rect = screen.availableGeometry()
            x = (rect.width() - self.width()) // 2
            y = (rect.height() - self.height()) // 2
            self.move(x, y)

    def _get_total_rows(self):
        """获取总记录数"""
        query = QSqlQuery("SELECT COUNT(*) FROM health_data", self.db)
        if query.exec() and query.next():
            self.total_rows = query.value(0)
        else:
            self.total_rows = 0

    def _setup_ui(self):
        """初始化界面控件"""
        # --- 模型和视图 ---
        self.model = QSqlQueryModel(self)
        self.view = QTableView()
        self.view.setModel(self.model)
        self.view.setEditTriggers(QTableView.NoEditTriggers)
        self.view.verticalHeader().setVisible(False)  # 1. 隐藏行号
        self.view.setItemDelegate(CenteredDelegate(self))
        
        # --- 样式优化：隔行变色 ---
        self.view.setAlternatingRowColors(True)
        self.view.setStyleSheet("""
            QTableView {
                background-color: #1e1e2e;
                alternate-background-color: #2a2b3c;
                selection-background-color: #45475a;
                color: #cdd6f4;
                gridline-color: #313244;
                border: none;
            }
            QHeaderView::section {
                background-color: #181825;
                color: #89b4fa;
                padding: 5px;
                border: 1px solid #313244;
                font-weight: bold;
            }
            QTableCornerButton::section {
                background-color: #181825;
                border: 1px solid #313244;
            }
        """)

        # 1. 设置为行选中
        self.view.setSelectionBehavior(QTableView.SelectRows)
        self.view.setSelectionMode(QTableView.SingleSelection) # 可选，单行或多行

        # 2. 添加右键菜单
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._show_context_menu)

        # 设置表头为粗体
        self.view.horizontalHeader().setStyleSheet("QHeaderView::section { font-weight: bold; }")

        # --- 分页控件 ---
        self.prev_button = QPushButton("上一页")
        self.prev_button.clicked.connect(self.prev_page)
        self.next_button = QPushButton("下一页")
        self.next_button.clicked.connect(self.next_page)
        self.page_label = QLabel()

        pagination_layout = QHBoxLayout()
        pagination_layout.addStretch()
        pagination_layout.addWidget(self.prev_button)
        pagination_layout.addWidget(self.page_label)
        pagination_layout.addWidget(self.next_button)
        pagination_layout.addStretch()

        # --- 主布局 ---
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.view)
        main_layout.addLayout(pagination_layout)
        self.setLayout(main_layout)

    def _show_context_menu(self, pos):
        """显示右键菜单"""
        index = self.view.indexAt(pos)
        if not index.isValid():
            return

        menu = QMenu(self)
        delete_action = QAction("删除", self)
        delete_action.triggered.connect(self._delete_selected_row)
        menu.addAction(delete_action)
        
        # 在鼠标点击位置显示菜单
        menu.exec(self.view.viewport().mapToGlobal(pos))

    def _delete_selected_row(self):
        """删除选中的行"""
        selected_indexes = self.view.selectionModel().selectedRows()
        if not selected_indexes:
            return

        # 获取选中行的 ID
        row_to_delete = selected_indexes[0].row()
        id_col_index = self.model.record().indexOf('id')
        if id_col_index == -1:
            print("错误: 找不到 'id' 列")
            return
            
        record_id = self.model.index(row_to_delete, id_col_index).data()

        # 执行删除操作
        query = QSqlQuery(self.db)
        query.prepare("DELETE FROM health_data WHERE id = :id")
        query.bindValue(":id", record_id)
        
        if query.exec():
            print(f"成功删除记录 ID: {record_id}")
            # 刷新数据
            self._get_total_rows() # 重新获取总数
            self.total_pages = math.ceil(self.total_rows / self.page_size) if self.total_rows > 0 else 0
            
            # 如果当前页在删除后变成空的，且不是第一页，则返回上一页
            if self.current_page > 1 and self.model.rowCount() == 1:
                self._go_to_page(self.current_page - 1)
            else:
                self._go_to_page(self.current_page) # 留在当前页刷新
        else:
            print(f"删除失败: {query.lastError().text()}")


    def _go_to_page(self, page_num):
        """跳转到指定页"""
        if self.total_pages > 0 and not (1 <= page_num <= self.total_pages):
            return

        self.current_page = page_num
        offset = (self.current_page - 1) * self.page_size
        
        # 只查询需要的字段
        query_str = (
            "SELECT created_at, heartrate, spo2, bk, fatigue, systolic, "
            "diastolic, CAST(cardiac AS REAL) / 10.0 AS cardiac, resistance, id "
            "FROM health_data ORDER BY id DESC "
            f"LIMIT {self.page_size} OFFSET {offset}"
        )
        self.model.setQuery(query_str, self.db)

        # 每次查询后都需要重新设置表头和隐藏列
        self._set_headers()

        # 设置列宽：第一列根据内容调整，其他列自适应窗口
        header = self.view.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        created_at_col_index = self.model.record().indexOf('created_at')
        if created_at_col_index != -1:
            header.setSectionResizeMode(created_at_col_index, QHeaderView.ResizeToContents)
        
        id_col_index = self.model.record().indexOf('id')
        if id_col_index != -1:
            self.view.setColumnHidden(id_col_index, True) # 1. 隐藏ID列

        self._update_pagination_controls()

    def _update_pagination_controls(self):
        """更新分页按钮和标签的状态"""
        if self.total_pages > 0:
            self.page_label.setText(f"第 {self.current_page} / {self.total_pages} 页")
            self.prev_button.setEnabled(self.current_page > 1)
            self.next_button.setEnabled(self.current_page < self.total_pages)
        else:
            self.page_label.setText("无数据")
            self.prev_button.setEnabled(False)
            self.next_button.setEnabled(False)

    def prev_page(self):
        self._go_to_page(self.current_page - 1)

    def next_page(self):
        self._go_to_page(self.current_page + 1)

    def _set_headers(self):
        """将数据库字段名映射为中文表头，并添加详细的Tooltip"""
        header_map = {
            'created_at': '采集时间',
            'heartrate': '心率',
            'spo2': '血氧',
            'bk': '微循环',
            'fatigue': '疲劳指数',
            'systolic': '收缩压',
            'diastolic': '舒张压',
            'cardiac': '心输出',
            'resistance': '外周阻力',
        }
        
        record = self.model.record()
        for col in range(record.count()):
            field_name = record.fieldName(col)
            if field_name in header_map:
                self.model.setHeaderData(col, Qt.Horizontal, header_map[field_name])
            if field_name in const.HEALTH_METRICS_TOOLTIPS:
                tooltip = const.HEALTH_METRICS_TOOLTIPS[field_name]
                self.model.setHeaderData(col, Qt.Horizontal, tooltip, Qt.ToolTipRole)

    def closeEvent(self, event):
        """重写 closeEvent，在窗口关闭时断开数据库连接"""
        # 1) 清空模型查询并解绑视图，确保不再持有连接引用
        try:
            if hasattr(self, 'model') and self.model is not None:
                self.model.setQuery(QSqlQuery())
        except Exception:
            pass
        try:
            if hasattr(self, 'view') and self.view is not None:
                self.view.setModel(None)
        except Exception:
            pass

        # 2) 关闭并释放数据库连接对象，再移除连接
        conn_name = None
        try:
            if hasattr(self, 'db') and self.db.isValid():
                conn_name = self.db.connectionName()
                if self.db.isOpen():
                    self.db.close()
                # 释放对连接的最后引用
                tmp_db = self.db
                self.db = QSqlDatabase()
                del tmp_db
        except Exception:
            pass

        if conn_name:
            QSqlDatabase.removeDatabase(conn_name)
        print("历史数据窗口的数据库连接已关闭。")
        super().closeEvent(event)
