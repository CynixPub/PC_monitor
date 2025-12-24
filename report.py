import sys
import os
import json
import sqlite3
import base64
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget, 
                               QTextBrowser, QSplitter, QMenu, QMessageBox, 
                               QListWidgetItem, QLabel, QScrollArea, QFrame, 
                               QProgressDialog, QDialog, QProgressBar, 
                               QStyledItemDelegate, QStyle, QPushButton)
from PySide6.QtCore import Qt, QThread, Signal, QSize, QByteArray, QTimer
from PySide6.QtGui import QAction, QPixmap, QFont, QIcon

from utils import user_data_path, resource_path, create_emoji_icon
from database_handler import DatabaseHandler

class ReportListDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        
        # 检查是否有错误标记
        is_error = index.data(Qt.UserRole + 1)
        if is_error:
            # 获取标准警告图标 (通常是黄色三角叹号，但在暗色主题下比较显眼)
            # 如果需要红色，可以使用 QPainter 绘制或加载特定资源
            icon = option.widget.style().standardIcon(QStyle.SP_MessageBoxWarning)
            
            icon_size = 16
            r = option.rect
            # 在右侧绘制图标
            x = r.right() - icon_size - 10
            y = r.top() + (r.height() - icon_size) // 2
            
            icon.paint(painter, x, y, icon_size, icon_size)

class GenerationProgressDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("生成报告")
        self.setFixedSize(400, 120)
        self.setWindowModality(Qt.WindowModal)
        # 去掉关闭按钮，防止用户意外关闭
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowCloseButtonHint)
        # 设置左上角图标
        self.setWindowIcon(create_emoji_icon('❤️'))

        layout = QVBoxLayout(self)
        
        self.status_label = QLabel("正在初始化...", self)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        font = QFont()
        font.setPointSize(10)
        self.status_label.setFont(font)
        layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 0) # 初始为忙碌模式
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

    def update_status(self, text, progress=-1):
        self.status_label.setText(text)
        if progress >= 0:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(progress)
        else:
            self.progress_bar.setRange(0, 0) # 忙碌模式

class ReportGeneratorThread(QThread):
    finished_signal = Signal(bool, str, dict) # success, message, report_data
    progress_signal = Signal(str, int) # message, progress_value

    def __init__(self, db_path):
        super().__init__()
        self.db_path = db_path
        self.seen_keys = set()

    def ai_progress_callback(self, content):
        # 简单的关键词检测来更新状态
        status_map = {
            '"report_meta"': "开始接收分析结果...",
            '"cardiovascular"': "正在接收 心血管分析结果...",
            '"respiratory"': "正在接收 呼吸系统分析结果...",
            '"microcirculation"': "正在接收 微循环分析结果...",
            '"fatigue_state"': "正在接收 疲劳状态分析结果...",
            '"trends_and_correlations"': "正在接收 趋势和相关性分析结果...",
            '"health_evaluation"': "正在接收 健康评估结果...",
            '"conclusion"': "正在接收 总体结论..."
        }
        
        for key, message in status_map.items():
            if key in content and key not in self.seen_keys:
                self.seen_keys.add(key)
                # 估算进度：AI 分析阶段从 40% 到 90%
                current_progress = 40 + len(self.seen_keys) * 6
                self.progress_signal.emit(message, min(current_progress, 90))
                break

    def run(self):
        # 延迟导入，避免阻塞主窗口加载
        import pandas as pd
        import data_plot
        import data_ai_analysis

        try:
            self.progress_signal.emit("正在读取健康数据...", 10)
            # 1. 读取健康检测数据，数据范围为最近50行
            conn = sqlite3.connect(self.db_path)
            query = """
            SELECT * FROM health_data ORDER BY id DESC LIMIT 50
            """
            df = pd.read_sql_query(query, conn)
            conn.close()

            if df.empty:
                self.finished_signal.emit(False, "没有找到健康数据", {})
                return

            # 2. 清洗数据，剔除数据中为0的数据行
            main_indicators = ['heartrate', 'spo2', 'fatigue']
            valid_indicators = [col for col in main_indicators if col in df.columns]
            
            if valid_indicators:
                # 剔除主要指标全为0的行
                df_clean = df[~((df[valid_indicators] == 0).all(axis=1))].copy()
            else:
                df_clean = df.copy()

            # 检查有效数据行比例
            if len(df) > 0:
                valid_ratio = len(df_clean) / len(df)
                if valid_ratio < 0.9:
                    self.finished_signal.emit(False, f"有效数据不足 90% (当前: {valid_ratio:.1%})，无法生成报告", {})
                    return
            
            self.progress_signal.emit("正在生成图表...", 30)
            # 3. 调用 data_plot.py 生成图片 (返回二进制数据)
            generated_images_bytes = data_plot.generate_plots(df_clean)
            
            if not generated_images_bytes:
                self.finished_signal.emit(False, "生成图表失败", {})
                return

            self.progress_signal.emit("已提交，正在等待分析结果...", 40)
            # 4. 调用 data_ai_analysis.py 提交健康数据进行分析
            self.seen_keys.clear()
            report_json = data_ai_analysis.generate_analysis_report(df_clean, progress_callback=self.ai_progress_callback)
            
            if not report_json:
                self.finished_signal.emit(False, "AI 分析失败", {})
                return

            self.progress_signal.emit("正在保存报告...", 95)
            # 5. 将生成图片，和分析结果全部保存到数据库中
            # 将图片二进制数据转换为 base64 字符串
            images_data_base64 = {}
            for filename, img_bytes in generated_images_bytes.items():
                images_data_base64[filename] = base64.b64encode(img_bytes).decode('utf-8')

            images_data_json = json.dumps(images_data_base64)
            report_json_str = json.dumps(report_json, ensure_ascii=False)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO reports (created_at, report_json, images_data) VALUES (?, ?, ?)",
                (pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"), report_json_str, images_data_json)
            )
            report_id = cursor.lastrowid
            conn.commit()
            conn.close()

            self.finished_signal.emit(True, "报告生成成功", {"id": report_id})

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.finished_signal.emit(False, f"生成报告过程中发生错误: {str(e)}", {})

class ReportWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("健康报告管理")
        self.resize(1200, 700)
        # 设置左上角图标
        self.setWindowIcon(create_emoji_icon('❤️'))
        
        # 初始化数据库表结构 (确保 reports 表存在)
        try:
            DatabaseHandler(db_file='history.db')
        except Exception as e:
            print(f"Database init warning: {e}")

        self.db_path = user_data_path('history.db')
        self.setup_ui()
        
        # 异步加载数据，避免阻塞窗口显示
        QTimer.singleShot(50, self.load_reports)

    def setup_ui(self):
        # 应用暗色主题样式
        self.setStyleSheet("""
            QWidget {
                background-color: #1e1e2e;
                color: #cdd6f4;
                font-family: "Microsoft YaHei";
            }
            QListWidget {
                background-color: #181825;
                border: 1px solid #313244;
                border-radius: 5px;
                outline: none;
            }
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid #313244;
            }
            QListWidget::item:selected {
                background-color: #45475a;
                color: #ffffff;
            }
            QListWidget::item:hover {
                background-color: #313244;
            }
            QScrollArea {
                border: none;
                background-color: #1e1e2e;
            }
            QScrollBar:vertical {
                border: none;
                background: #181825;
                width: 10px;
                margin: 0px 0px 0px 0px;
            }
            QScrollBar::handle:vertical {
                background: #45475a;
                min-height: 20px;
                border-radius: 5px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QSplitter::handle {
                background-color: #313244;
            }
        """)

        layout = QHBoxLayout(self)
        
        # 分割器
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)

        # 左侧列表
        self.report_list = QListWidget()
        self.report_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.report_list.customContextMenuRequested.connect(self.show_context_menu)
        self.report_list.itemClicked.connect(self.display_report)
        self.report_list.setMaximumWidth(250)
        # 设置自定义委托以显示图标
        self.report_list.setItemDelegate(ReportListDelegate(self.report_list))
        splitter.addWidget(self.report_list)

        # 右侧内容显示区
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.scroll_area.setWidget(self.content_widget)
        splitter.addWidget(self.scroll_area)
        
        # 设置分割比例
        splitter.setStretchFactor(0, 1)
        # 添加初始加载提示
        self.loading_label = QLabel("正在加载数据...", self.content_widget)
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setStyleSheet("color: #89b4fa; font-size: 16px;")
        self.content_layout.addWidget(self.loading_label)

        splitter.setStretchFactor(1, 3)

    def clear_content_area(self):
        """彻底清空右侧内容区域，包括子布局"""
        if self.content_layout is not None:
            while self.content_layout.count():
                item = self.content_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
                elif item.layout() is not None:
                    self._clear_layout_recursive(item.layout())
    
    def _clear_layout_recursive(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            elif item.layout() is not None:
                self._clear_layout_recursive(item.layout())

    def load_reports(self):
        self.report_list.clear()
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            # 倒序查询，同时获取 report_json 以检查状态
            cursor.execute("SELECT id, created_at, report_json FROM reports ORDER BY id DESC")
            reports = cursor.fetchall()
            conn.close()

            for report_id, created_at, report_json_str in reports:
                item = QListWidgetItem(f"报告 - {created_at}")
                item.setData(Qt.UserRole, report_id)
                
                # 检查报告是否包含错误信息
                try:
                    data = json.loads(report_json_str)
                    # 检查 rating 是否为 "配置错误" 或其他错误标识
                    if data.get('health_evaluation', {}).get('rating') == '配置错误':
                        item.setData(Qt.UserRole + 1, True) # 标记为错误
                except:
                    pass
                
                self.report_list.addItem(item)

            # 默认选中最新的报告
            if self.report_list.count() > 0:
                self.report_list.setCurrentRow(0)
                self.display_report(self.report_list.item(0))
            else:
                # 如果没有报告，清空加载提示并显示暂无数据
                self.clear_content_area()
                
                no_data_label = QLabel("暂无历史报告")
                no_data_label.setAlignment(Qt.AlignCenter)
                no_data_label.setStyleSheet("color: #6c7086; font-size: 16px;")
                self.content_layout.addWidget(no_data_label)

                # 添加生成报告按钮
                btn_create = QPushButton("立即生成报告")
                btn_create.setFixedSize(150, 40)
                btn_create.setStyleSheet("""
                    QPushButton {
                        background-color: #89b4fa;
                        color: #1e1e2e;
                        border-radius: 5px;
                        font-weight: bold;
                        font-size: 14px;
                    }
                    QPushButton:hover {
                        background-color: #b4befe;
                    }
                """)
                btn_create.setCursor(Qt.PointingHandCursor)
                btn_create.clicked.connect(self.check_and_create_report)
                
                # 居中按钮
                h_layout = QHBoxLayout()
                h_layout.addStretch()
                h_layout.addWidget(btn_create)
                h_layout.addStretch()
                
                self.content_layout.addSpacing(20)
                self.content_layout.addLayout(h_layout)
                self.content_layout.addStretch()

        except sqlite3.Error as e:
            print(f"加载报告列表失败: {e}")

    def display_report(self, item):
        if not item:
            return
            
        report_id = item.data(Qt.UserRole)
        
        # 清空当前显示
        self.clear_content_area()

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM reports WHERE id = ?", (report_id,))
            # 获取列名
            column_names = [description[0] for description in cursor.description]
            row = cursor.fetchone()
            conn.close()

            if row:
                row_dict = dict(zip(column_names, row))
                report_json_str = row_dict.get('report_json')
                
                images_data = {}
                if 'images_data' in row_dict and row_dict['images_data']:
                    try:
                        images_data = json.loads(row_dict['images_data'])
                    except json.JSONDecodeError:
                        pass
                try:
                    report_data = json.loads(report_json_str)
                except json.JSONDecodeError:
                    self.content_layout.addWidget(QLabel("报告数据损坏"))
                    return

                # 显示报告内容
                self.render_report_content(report_data, images_data)
        except sqlite3.Error as e:
            print(f"读取报告详情失败: {e}")

    def render_report_content(self, data, images_data):
        # 样式表 (适配暗色主题)
        style_sheet = """
            QWidget {
                background-color: transparent;
            }
            QLabel {
                font-family: "Microsoft YaHei";
                font-size: 14px;
                line-height: 1.5;
                color: #cdd6f4;
                background-color: transparent;
            }
            .title {
                font-size: 24px;
                font-weight: bold;
                color: #89b4fa;
                margin-bottom: 10px;
            }
            .subtitle {
                font-size: 18px;
                font-weight: bold;
                color: #f5c2e7;
                margin-top: 20px;
                margin-bottom: 10px;
                border-bottom: 2px solid #45475a;
                padding-bottom: 5px;
            }
            .meta {
                color: #a6adc8;
                font-size: 12px;
                margin-bottom: 20px;
            }
            .score-box {
                background-color: #181825;
                border: 1px solid #313244;
                border-radius: 8px;
                padding: 15px;
                margin-bottom: 20px;
            }
            .score-val {
                font-size: 36px;
                font-weight: bold;
                color: #a6e3a1;
            }
            .score-label {
                font-size: 16px;
                color: #bac2de;
            }
            .card {
                background-color: #181825;
                border: 1px solid #313244;
                border-radius: 6px;
                padding: 15px;
                margin-bottom: 10px;
            }
            .card-title {
                font-weight: bold;
                font-size: 15px;
                color: #89b4fa;
                margin-bottom: 5px;
            }
        """
        self.content_widget.setStyleSheet(style_sheet)

        # 标题
        title = QLabel("健康分析报告")
        title.setProperty("class", "title")
        title.setAlignment(Qt.AlignCenter)
        self.content_layout.addWidget(title)

        # 报告元数据
        if "report_meta" in data:
            meta = data["report_meta"]
            meta_text = f"有效样本: {meta.get('valid_samples_count', 'N/A')}"
            
            # 引擎统计信息
            if "engine_stats" in meta:
                stats = meta["engine_stats"]
                meta_text += f" | AI引擎: {stats.get('platform', 'Unknown')} (耗时: {stats.get('process_time', 0)}s)"
            
            meta_label = QLabel(meta_text)
            meta_label.setProperty("class", "meta")
            meta_label.setAlignment(Qt.AlignCenter)
            self.content_layout.addWidget(meta_label)

        # 健康评分 (新增)
        if "health_evaluation" in data:
            eval_data = data["health_evaluation"]
            score = eval_data.get("overall_score", "N/A")
            rating = eval_data.get("rating", "N/A")
            
            score_frame = QFrame()
            score_frame.setProperty("class", "score-box")
            score_layout = QHBoxLayout(score_frame)
            
            score_val_label = QLabel(f"{score}")
            score_val_label.setProperty("class", "score-val")
            score_val_label.setAlignment(Qt.AlignCenter)
            
            score_desc_label = QLabel(f"健康评分\n评级: {rating}")
            score_desc_label.setProperty("class", "score-label")
            score_desc_label.setAlignment(Qt.AlignCenter)
            
            score_layout.addStretch()
            score_layout.addWidget(score_val_label)
            score_layout.addSpacing(20)
            score_layout.addWidget(score_desc_label)
            score_layout.addStretch()
            
            self.content_layout.addWidget(score_frame)

        # 报告总结
        if "conclusion" in data:
            self.add_section_title("报告总结")
            
            conclusion_group = QFrame()
            conclusion_group.setProperty("class", "card")
            
            # 检查是否为错误报告
            is_error = data.get("health_evaluation", {}).get("rating") == "配置错误"
            if is_error:
                # 错误报告样式
                conclusion_group.setStyleSheet("""
                    .card { 
                        border: 1px solid #f38ba8; 
                        background-color: #311b25; 
                    }
                    QLabel { color: #f38ba8; }
                """)
                text_prefix = "⚠️ <b>分析中断</b><br>"
            else:
                text_prefix = ""

            c_layout = QVBoxLayout(conclusion_group)
            c_label = QLabel(text_prefix + data["conclusion"])
            c_label.setWordWrap(True)
            c_layout.addWidget(c_label)
            self.content_layout.addWidget(conclusion_group)


        # 图片展示
        if images_data:
            #self.add_section_title("图表分析")
            
            # 图片说明映射
            image_descriptions = {
                "1_心率血氧疲劳趋势": "展示了心率、血氧和疲劳指数随时间的变化趋势。观察曲线波动可以了解身体状态的稳定性。",
                "2_血压变化趋势": "收缩压和舒张压的对比分析，用于评估心血管系统的压力负荷。",
                "3_心输出与外周阻力": "心输出量与外周阻力的关系，反映心脏泵血效率与血管阻力情况。",
                "4_健康指标分布": "各项主要健康指标的数值分布范围，箱线图展示了数据的集中趋势和离散程度。",
                "5_微循环相关性": "微循环与其他生理指标的相关性分析，正相关表示同步变化，负相关表示反向变化。"
            }

            for filename, b64_data in images_data.items():
                try:
                    img_bytes = base64.b64decode(b64_data)
                    pixmap = QPixmap()
                    if pixmap.loadFromData(QByteArray(img_bytes)):
                        lbl = QLabel()
                        # 稍微调大一点图片显示
                        lbl.setPixmap(pixmap.scaled(700, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                        lbl.setAlignment(Qt.AlignCenter)
                        lbl.setStyleSheet("border: 1px solid #ddd; padding: 5px; border-radius: 4px;")
                        self.content_layout.addWidget(lbl)
                        
                        key = filename.replace(".png", "")
                        
                        # 图片标题
                        caption = QLabel(key)
                        caption.setAlignment(Qt.AlignCenter)
                        caption.setStyleSheet("color: #89b4fa; font-size: 14px; font-weight: bold; margin-top: 5px;")
                        self.content_layout.addWidget(caption)

                        # 图片说明
                        desc_text = image_descriptions.get(key, "")
                        if desc_text:
                            desc_label = QLabel(desc_text)
                            desc_label.setAlignment(Qt.AlignCenter)
                            desc_label.setWordWrap(True)
                            desc_label.setStyleSheet("color: #a6adc8; font-size: 12px; margin-bottom: 20px;")
                            self.content_layout.addWidget(desc_label)
                        else:
                            # 如果没有说明，仅添加下边距
                            caption.setStyleSheet("color: #89b4fa; font-size: 14px; font-weight: bold; margin-bottom: 20px;")

                    else:
                        self.content_layout.addWidget(QLabel(f"图片加载失败: {filename}"))
                except Exception as e:
                    self.content_layout.addWidget(QLabel(f"图片解码错误: {filename}"))

        self.content_layout.addStretch()



        # 系统分析
        if "system_analysis" in data:
            self.add_section_title("系统分析")
            
            sys_data = data["system_analysis"]
            # 翻译映射
            sys_name_map = {
                "cardiovascular": "心血管系统",
                "respiratory": "呼吸系统",
                "microcirculation": "微循环系统",
                "fatigue_state": "疲劳状态"
            }
            
            for sys_key, metrics in sys_data.items():
                sys_group = QFrame()
                sys_group.setProperty("class", "card")
                s_layout = QVBoxLayout(sys_group)
                
                sys_name_cn = sys_name_map.get(sys_key, sys_key.capitalize())
                title_lbl = QLabel(sys_name_cn)
                title_lbl.setProperty("class", "card-title")
                s_layout.addWidget(title_lbl)
                
                content_text = ""
                for k, v in metrics.items():
                    # 简单的键名美化，如果需要更详细的映射可以添加
                    content_text += f"• {v}\n"
                
                content_lbl = QLabel(content_text.strip())
                content_lbl.setWordWrap(True)
                s_layout.addWidget(content_lbl)
                
                self.content_layout.addWidget(sys_group)

        # 趋势与相关性
        if "trends_and_correlations" in data:
            self.add_section_title("趋势与相关性分析")
            trends_data = data["trends_and_correlations"]
            
            if "key_findings" in trends_data:
                findings = trends_data["key_findings"]
                
                trend_group = QFrame()
                trend_group.setProperty("class", "card")
                t_layout = QVBoxLayout(trend_group)
                
                if "trends" in findings and findings["trends"]:
                    t_layout.addWidget(QLabel("<b>📈 关键趋势:</b>"))
                    for t in findings["trends"]:
                        t_layout.addWidget(QLabel(f"  • {t}"))
                    t_layout.addSpacing(10)
                
                if "correlations" in findings and findings["correlations"]:
                    t_layout.addWidget(QLabel("<b>🔗 关联发现:</b>"))
                    for c in findings["correlations"]:
                        t_layout.addWidget(QLabel(f"  • {c}"))
                
                self.content_layout.addWidget(trend_group)

        # 建议
        if "health_evaluation" in data:
            eval_data = data["health_evaluation"]
            
            # 优势与隐患
            if "strengths" in eval_data or "concerns" in eval_data:
                self.add_section_title("健康评估")
                
                eval_group = QFrame()
                eval_group.setProperty("class", "card")
                e_layout = QVBoxLayout(eval_group)
                
                if "strengths" in eval_data and eval_data["strengths"]:
                    e_layout.addWidget(QLabel("<b>💪 优势:</b>"))
                    for s in eval_data["strengths"]:
                        e_layout.addWidget(QLabel(f"  • {s}"))
                    e_layout.addSpacing(10)
                
                if "concerns" in eval_data and eval_data["concerns"]:
                    e_layout.addWidget(QLabel("<b>⚠️ 隐患:</b>"))
                    for c in eval_data["concerns"]:
                        e_layout.addWidget(QLabel(f"  • {c}"))
                
                self.content_layout.addWidget(eval_group)

            # 建议
            if "recommendations" in eval_data:
                self.add_section_title("健康建议")
                
                rec_group = QFrame()
                rec_group.setProperty("class", "card")
                r_layout = QVBoxLayout(rec_group)
                
                recs = eval_data["recommendations"]
                for rec in recs:
                    r_layout.addWidget(QLabel(f"💡 {rec}"))
                
                self.content_layout.addWidget(rec_group)



    def add_section_title(self, text):
        label = QLabel(text)
        label.setProperty("class", "subtitle")
        self.content_layout.addWidget(label)

    def show_context_menu(self, pos):
        menu = QMenu()
        new_action = QAction("新增报告", self)
        new_action.triggered.connect(self.check_and_create_report)
        menu.addAction(new_action)

        item = self.report_list.itemAt(pos)
        if item:
            delete_action = QAction("删除报告", self)
            delete_action.triggered.connect(lambda: self.delete_report(item))
            menu.addAction(delete_action)

        menu.exec(self.report_list.mapToGlobal(pos))

    def delete_report(self, item):
        reply = QMessageBox.question(self, '确认删除', 
                                     '确定要删除这份报告吗？此操作不可恢复。',
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            report_id = item.data(Qt.UserRole)
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM reports WHERE id = ?", (report_id,))
                conn.commit()
                conn.close()
                
                # 从列表中移除
                row = self.report_list.row(item)
                self.report_list.takeItem(row)
                
                # 清空右侧
                self.clear_content_area()
                
                # 如果删除后列表为空，重新加载以显示"暂无数据"界面
                if self.report_list.count() == 0:
                    self.load_reports()
                else:
                    # 否则选中第一项
                    self.report_list.setCurrentRow(0)
                    self.display_report(self.report_list.item(0))
                    
            except sqlite3.Error as e:
                QMessageBox.critical(self, "错误", f"删除失败: {e}")

    def check_and_create_report(self):
        # 检查是否有新数据
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 获取最新报告时间
            cursor.execute("SELECT MAX(created_at) FROM reports")
            last_report_time = cursor.fetchone()[0]
            
            # 获取最新数据时间
            cursor.execute("SELECT MAX(created_at) FROM health_data")
            last_data_time = cursor.fetchone()[0]
            
            conn.close()

            if last_report_time and last_data_time and last_data_time <= last_report_time:
                QMessageBox.information(self, "提示", "上次报告后没有新增健康数据，无需生成新报告。")
                return
            
            # 开始生成报告
            self.start_report_generation()

        except sqlite3.Error as e:
            QMessageBox.critical(self, "错误", f"数据库检查失败: {e}")

    def start_report_generation(self):
        self.progress = GenerationProgressDialog(self)
        self.progress.show()

        self.thread = ReportGeneratorThread(self.db_path)
        self.thread.finished_signal.connect(self.on_report_generated)
        self.thread.progress_signal.connect(self.progress.update_status)
        self.thread.start()

    def on_report_generated(self, success, message, data):
        self.progress.close()
        if success:
            self.load_reports() # 刷新列表
        else:
            QMessageBox.warning(self, "失败", message)

