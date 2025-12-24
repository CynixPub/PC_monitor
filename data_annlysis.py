import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.gridspec import GridSpec
import sqlite3
import warnings
warnings.filterwarnings('ignore')

# 设置图表样式和中文字体
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']  # 微软雅黑或黑体
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.figsize'] = (16, 12)
plt.rcParams['font.size'] = 10
plt.rcParams['axes.linewidth'] = 0.8


# 从 SQLite 数据库读取数据
db_path = 'history.db'  # 数据库文件路径
conn = sqlite3.connect(db_path)

# 执行查询，获取所有健康数据
query = """
SELECT 
    created_at AS 采集时间,
    heartrate AS 心率,
    spo2 AS 血氧,
    bk AS 微循环,
    fatigue AS 疲劳指数,
    systolic AS 收缩压,
    diastolic AS 舒张压,
    CAST(cardiac AS REAL) / 10.0 AS 心输出,
    resistance AS 外周阻力
FROM health_data
ORDER BY id DESC
"""

df = pd.read_sql_query(query, conn)
conn.close()

# 处理采集时间
df['采集时间'] = pd.to_datetime(df['采集时间'], errors='coerce')

# 数据清洗：剔除无效数据
# 定义主要健康指标，这些指标为0的记录视为无效
main_indicators = ['心率', '血氧', '疲劳指数']

# 方法1：剔除主要指标全部为0的记录
df_clean = df[~((df[main_indicators] == 0).all(axis=1))].copy()

# 方法2：对于部分指标为0的记录，用该指标的非0均值填充（保持数据完整性）
for col in df_clean.columns:
    if col not in ['采集时间'] and df_clean[col].dtype in [np.int64, np.float64]:
        # 计算非0均值
        non_zero_mean = df_clean[df_clean[col] != 0][col].mean()
        # 用非0均值填充0值
        df_clean[col] = df_clean[col].replace(0, round(non_zero_mean, 1))

# 按时间排序
df_clean = df_clean.sort_values('采集时间').reset_index(drop=True)

print("数据清洗结果：")
print(f"原始数据量：{len(df)} 条")
print(f"清洗后数据量：{len(df_clean)} 条")
print(f"剔除无效数据：{len(df) - len(df_clean)} 条")

print("\n清洗后数据预览：")
print(df_clean.head())

print("\n清洗后各指标统计信息：")
stats_df = df_clean.drop('采集时间', axis=1).describe().round(2)
print(stats_df)





# 使用清洗后的数据直接进行可视化，无需保存中间文件


# 确保数据按时间排序
df_clean = df_clean.sort_values('采集时间').reset_index(drop=True)

# 定义专业配色方案
colors = {
    '心率': '#E74C3C',      # 红色
    '血氧': '#27AE60',      # 绿色  
    '疲劳指数': '#F39C12',  # 橙色
    '收缩压': '#3498DB',    # 蓝色
    '舒张压': '#9B59B6',    # 紫色
    '心输出': '#1ABC9C',    # 青色
    '外周阻力': '#E67E22'   # 橙色
}

# ============ 图表1：心率、血氧、疲劳指数趋势 ============
fig1, ax1 = plt.subplots(figsize=(14, 6))
ax1_twin = ax1.twinx()

# 绘制心率和血氧
line1 = ax1.plot(df_clean['采集时间'], df_clean['心率'], 
                 color=colors['心率'], marker='o', linewidth=2, 
                 markersize=4, label='心率', alpha=0.8)
line2 = ax1.plot(df_clean['采集时间'], df_clean['血氧'], 
                 color=colors['血氧'], marker='s', linewidth=2, 
                 markersize=4, label='血氧', alpha=0.8)
# 绘制疲劳指数（右轴）
line3 = ax1_twin.plot(df_clean['采集时间'], df_clean['疲劳指数'], 
                      color=colors['疲劳指数'], marker='^', linewidth=2, 
                      markersize=4, label='疲劳指数', alpha=0.8)

ax1.set_xlabel('采集时间', fontsize=12, fontweight='bold')
ax1.set_ylabel('心率(次/分) / 血氧(%)', fontsize=11, fontweight='bold')
ax1_twin.set_ylabel('疲劳指数', fontsize=11, fontweight='bold', color=colors['疲劳指数'])
ax1.tick_params(axis='x', rotation=45, labelsize=10)
ax1.grid(True, alpha=0.3)
ax1.set_title('心率、血氧及疲劳指数变化趋势', fontsize=14, fontweight='bold', pad=20)

lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax1_twin.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left', fontsize=10, framealpha=0.9)

plt.tight_layout()
plt.savefig('1_心率血氧疲劳趋势.png', dpi=200, bbox_inches='tight', facecolor='white')
plt.close()
print("✅ 图表1已生成: 1_心率血氧疲劳趋势.png")

# ============ 图表2：血压变化趋势 ============
fig2, ax2 = plt.subplots(figsize=(14, 6))
ax2.plot(df_clean['采集时间'], df_clean['收缩压'], 
         color=colors['收缩压'], marker='o', linewidth=2.5, 
         markersize=5, label='收缩压', alpha=0.8)
ax2.plot(df_clean['采集时间'], df_clean['舒张压'], 
         color=colors['舒张压'], marker='s', linewidth=2.5, 
         markersize=5, label='舒张压', alpha=0.8)

# 添加正常血压参考线
ax2.axhline(y=120, color='red', linestyle='--', alpha=0.4, linewidth=1.5, label='收缩压正常上限')
ax2.axhline(y=80, color='darkred', linestyle='--', alpha=0.4, linewidth=1.5, label='舒张压正常上限')

ax2.set_xlabel('采集时间', fontsize=12, fontweight='bold')
ax2.set_ylabel('血压 (mmHg)', fontsize=11, fontweight='bold')
ax2.tick_params(axis='x', rotation=45, labelsize=10)
ax2.grid(True, alpha=0.3)
ax2.legend(loc='upper left', fontsize=10, framealpha=0.9)
ax2.set_title('收缩压与舒张压变化趋势', fontsize=14, fontweight='bold', pad=20)

plt.tight_layout()
plt.savefig('2_血压变化趋势.png', dpi=200, bbox_inches='tight', facecolor='white')
plt.close()
print("✅ 图表2已生成: 2_血压变化趋势.png")

# ============ 图表3：心输出与外周阻力 ============
fig3, ax3 = plt.subplots(figsize=(10, 7))
scatter = ax3.scatter(df_clean['心输出'], df_clean['外周阻力'], 
                     c=df_clean['心率'], cmap='RdYlBu_r', 
                     s=100, alpha=0.7, edgecolors='black', linewidth=0.8)

ax3.set_xlabel('心输出', fontsize=12, fontweight='bold')
ax3.set_ylabel('外周阻力', fontsize=12, fontweight='bold')
ax3.grid(True, alpha=0.3)

cbar = plt.colorbar(scatter, ax=ax3)
cbar.set_label('心率 (次/分)', fontsize=11, fontweight='bold')

ax3.set_title('心输出与外周阻力关系（颜色表示心率）', fontsize=14, fontweight='bold', pad=20)

plt.tight_layout()
plt.savefig('3_心输出与外周阻力.png', dpi=200, bbox_inches='tight', facecolor='white')
plt.close()
print("✅ 图表3已生成: 3_心输出与外周阻力.png")

# ============ 图表4：各指标分布箱线图 ============
fig4, ax4 = plt.subplots(figsize=(12, 6))
indicators = ['心率', '血氧', '疲劳指数', '收缩压', '舒张压', '心输出', '外周阻力']
data_to_plot = [df_clean[ind] for ind in indicators]

box_plot = ax4.boxplot(data_to_plot, labels=indicators, patch_artist=True,
                       boxprops=dict(alpha=0.7), medianprops=dict(color='red', linewidth=2.5))

for patch, color in zip(box_plot['boxes'], [colors.get(ind, '#7f8c8d') for ind in indicators]):
    patch.set_facecolor(color)
    patch.set_alpha(0.7)

ax4.set_ylabel('数值', fontsize=12, fontweight='bold')
ax4.tick_params(axis='x', labelsize=11)
ax4.grid(True, alpha=0.3, axis='y')
ax4.set_title('主要健康指标分布情况', fontsize=14, fontweight='bold', pad=20)

plt.tight_layout()
plt.savefig('4_健康指标分布.png', dpi=200, bbox_inches='tight', facecolor='white')
plt.close()
print("✅ 图表4已生成: 4_健康指标分布.png")

# ============ 图表5：微循环相关性分析 ============
fig5, ax5 = plt.subplots(figsize=(12, 6))
corr_indicators = ['心率', '血氧', '疲劳指数', '收缩压', '舒张压', '心输出', '外周阻力']
correlations = [df_clean['微循环'].corr(df_clean[ind]) for ind in corr_indicators]

bars = ax5.bar(corr_indicators, correlations, 
               color=[colors.get(ind, '#7f8c8d') for ind in corr_indicators],
               alpha=0.7, edgecolor='black', linewidth=1)

ax5.axhline(y=0, color='black', linestyle='-', linewidth=1.5)
ax5.axhline(y=0.5, color='green', linestyle='--', alpha=0.5, linewidth=1.5, label='中等正相关')
ax5.axhline(y=-0.5, color='red', linestyle='--', alpha=0.5, linewidth=1.5, label='中等负相关')

ax5.set_ylabel('相关系数', fontsize=12, fontweight='bold')
ax5.set_ylim(-1.2, 1.2)
ax5.tick_params(axis='x', labelsize=11)
ax5.grid(True, alpha=0.3, axis='y')
ax5.legend(loc='upper right', fontsize=10, framealpha=0.9)
ax5.set_title('微循环与其他健康指标的相关性分析', fontsize=14, fontweight='bold', pad=20)

for bar, corr in zip(bars, correlations):
    height = bar.get_height()
    ax5.text(bar.get_x() + bar.get_width()/2., height + (0.03 if height >= 0 else -0.06),
             f'{corr:.2f}', ha='center', va='bottom' if height >= 0 else 'top',
             fontweight='bold', fontsize=10)

plt.tight_layout()
plt.savefig('5_微循环相关性.png', dpi=200, bbox_inches='tight', facecolor='white')
plt.close()
print("✅ 图表5已生成: 5_微循环相关性.png")

print("\n✅ 所有健康数据分析图表已生成完毕！")

# 计算关键健康指标统计
def get_health_status(value, normal_range):
    """判断健康指标状态"""
    min_val, max_val = normal_range
    if value < min_val:
        return "偏低"
    elif value > max_val:
        return "偏高"
    else:
        return "正常"

health_stats = {
    '心率': {
        '均值': df_clean['心率'].mean(),
        '标准差': df_clean['心率'].std(),
        '正常范围': (60, 100),
        '单位': '次/分钟'
    },
    '血氧': {
        '均值': df_clean['血氧'].mean(),
        '标准差': df_clean['血氧'].std(),
        '正常范围': (95, 100),
        '单位': '%'
    },
    '收缩压': {
        '均值': df_clean['收缩压'].mean(),
        '标准差': df_clean['收缩压'].std(),
        '正常范围': (90, 120),
        '单位': 'mmHg'
    },
    '舒张压': {
        '均值': df_clean['舒张压'].mean(),
        '标准差': df_clean['舒张压'].std(),
        '正常范围': (60, 80),
        '单位': 'mmHg'
    },
    '疲劳指数': {
        '均值': df_clean['疲劳指数'].mean(),
        '标准差': df_clean['疲劳指数'].std(),
        '正常范围': (0, 40),
        '单位': ''
    },
    '微循环': {
        '均值': df_clean['微循环'].mean(),
        '标准差': df_clean['微循环'].std(),
        '正常范围': (70, 90),
        '单位': ''
    },
    '心输出': {
        '均值': df_clean['心输出'].mean(),
        '标准差': df_clean['心输出'].std(),
        '正常范围': (3.5, 5.5),
        '单位': ''
    },
    '外周阻力': {
        '均值': df_clean['外周阻力'].mean(),
        '标准差': df_clean['外周阻力'].std(),
        '正常范围': (180, 250),
        '单位': ''
    }
}

# 添加状态判断
for indicator, stats in health_stats.items():
    stats['状态'] = get_health_status(stats['均值'], stats['正常范围'])

print("\n📊 关键健康指标统计摘要：")
for indicator, stats in health_stats.items():
    print(f"{indicator}: 均值 {stats['均值']:.1f} {stats['单位']} (±{stats['标准差']:.1f}), "
          f"正常范围 {stats['正常范围'][0]}-{stats['正常范围'][1]} {stats['单位']}, "
          f"状态: {stats['状态']}")

# 计算相关性矩阵
corr_matrix = df_clean.drop('采集时间', axis=1).corr().round(2)
print("\n🔗 健康指标相关性矩阵（前5行5列）：")
print(corr_matrix.iloc[:5, :5])