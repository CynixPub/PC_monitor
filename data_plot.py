import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import io
import warnings

warnings.filterwarnings('ignore')

def generate_plots(df):
    """
    根据提供的 DataFrame 生成图表。
    返回一个字典，key为文件名，value为图片的二进制数据(bytes)。
    """
    # 设置图表样式和中文字体
    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']  # 微软雅黑或黑体
    plt.rcParams['axes.unicode_minus'] = False
    plt.rcParams['figure.figsize'] = (16, 12)
    plt.rcParams['font.size'] = 10
    plt.rcParams['axes.linewidth'] = 0.8

    # 处理采集时间
    if '采集时间' in df.columns:
        df['采集时间'] = pd.to_datetime(df['采集时间'], errors='coerce')
    elif 'created_at' in df.columns:
        df['采集时间'] = pd.to_datetime(df['created_at'], errors='coerce')
    
    # 确保列名匹配
    column_map = {
        'heartrate': '心率',
        'spo2': '血氧',
        'bk': '微循环',
        'fatigue': '疲劳指数',
        'systolic': '收缩压',
        'diastolic': '舒张压',
        'cardiac': '心输出', # 需要特殊处理
        'resistance': '外周阻力'
    }
    
    # 如果列名是英文，重命名为中文
    df_renamed = df.rename(columns=column_map)
    
    # 特殊处理心输出 (如果还是原始值)
    if '心输出' in df_renamed.columns and df_renamed['心输出'].mean() > 100: # 假设原始值较大
         df_renamed['心输出'] = df_renamed['心输出'] / 10.0

    # 数据清洗：剔除无效数据
    main_indicators = ['心率', '血氧', '疲劳指数']
    # 确保列存在
    existing_indicators = [col for col in main_indicators if col in df_renamed.columns]
    
    if existing_indicators:
        df_clean = df_renamed[~((df_renamed[existing_indicators] == 0).all(axis=1))].copy()
    else:
        df_clean = df_renamed.copy()

    # 填充0值
    for col in df_clean.columns:
        if col != '采集时间' and df_clean[col].dtype in [np.int64, np.float64]:
            non_zero_mean = df_clean[df_clean[col] != 0][col].mean()
            if pd.notna(non_zero_mean):
                df_clean[col] = df_clean[col].replace(0, round(non_zero_mean, 1))

    # 按时间排序
    if '采集时间' in df_clean.columns:
        df_clean = df_clean.sort_values('采集时间').reset_index(drop=True)

    # 定义专业配色方案
    colors = {
        '心率': '#E74C3C',      # 红色
        '血氧': '#27AE60',      # 绿色  
        '疲劳指数': '#F39C12',  # 橙色
        '收缩压': '#3498DB',    # 蓝色
        '舒张压': '#9B59B6',    # 紫色
        '心输出': '#1ABC9C',    # 青色
        '外周阻力': '#E67E22',   # 橙色
        '微循环': '#8E44AD'     # 紫色
    }

    generated_images = {}

    def save_plot_to_bytes(filename):
        buf = io.BytesIO()
        plt.tight_layout()
        plt.savefig(buf, format='png', dpi=200, bbox_inches='tight', facecolor='white')
        plt.close()
        buf.seek(0)
        generated_images[filename] = buf.getvalue()

    # ============ 图表1：心率、血氧、疲劳指数趋势 ============
    try:
        fig1, ax1 = plt.subplots(figsize=(14, 6))
        ax1_twin = ax1.twinx()

        if '心率' in df_clean.columns:
            ax1.plot(df_clean['采集时间'], df_clean['心率'], 
                    color=colors['心率'], marker='o', linewidth=2, 
                    markersize=4, label='心率', alpha=0.8)
        if '血氧' in df_clean.columns:
            ax1.plot(df_clean['采集时间'], df_clean['血氧'], 
                    color=colors['血氧'], marker='s', linewidth=2, 
                    markersize=4, label='血氧', alpha=0.8)
        if '疲劳指数' in df_clean.columns:
            ax1_twin.plot(df_clean['采集时间'], df_clean['疲劳指数'], 
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

        save_plot_to_bytes('1_心率血氧疲劳趋势.png')
    except Exception as e:
        print(f"❌ 图表1生成失败: {e}")

    # ============ 图表2：血压变化趋势 ============
    try:
        fig2, ax2 = plt.subplots(figsize=(14, 6))
        if '收缩压' in df_clean.columns:
            ax2.plot(df_clean['采集时间'], df_clean['收缩压'], 
                    color=colors['收缩压'], marker='o', linewidth=2.5, 
                    markersize=5, label='收缩压', alpha=0.8)
        if '舒张压' in df_clean.columns:
            ax2.plot(df_clean['采集时间'], df_clean['舒张压'], 
                    color=colors['舒张压'], marker='s', linewidth=2.5, 
                    markersize=5, label='舒张压', alpha=0.8)

        ax2.axhline(y=120, color='red', linestyle='--', alpha=0.4, linewidth=1.5, label='收缩压正常上限')
        ax2.axhline(y=80, color='darkred', linestyle='--', alpha=0.4, linewidth=1.5, label='舒张压正常上限')

        ax2.set_xlabel('采集时间', fontsize=12, fontweight='bold')
        ax2.set_ylabel('血压 (mmHg)', fontsize=11, fontweight='bold')
        ax2.tick_params(axis='x', rotation=45, labelsize=10)
        ax2.grid(True, alpha=0.3)
        ax2.legend(loc='upper left', fontsize=10, framealpha=0.9)
        ax2.set_title('收缩压与舒张压变化趋势', fontsize=14, fontweight='bold', pad=20)

        save_plot_to_bytes('2_血压变化趋势.png')
    except Exception as e:
        print(f"❌ 图表2生成失败: {e}")

    # ============ 图表3：心输出与外周阻力 ============
    try:
        if '心输出' in df_clean.columns and '外周阻力' in df_clean.columns and '心率' in df_clean.columns:
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

            save_plot_to_bytes('3_心输出与外周阻力.png')
    except Exception as e:
        print(f"❌ 图表3生成失败: {e}")

    # ============ 图表4：各指标分布箱线图 ============
    try:
        fig4, ax4 = plt.subplots(figsize=(12, 6))
        indicators = ['心率', '血氧', '疲劳指数', '收缩压', '舒张压', '心输出', '外周阻力']
        valid_indicators = [ind for ind in indicators if ind in df_clean.columns]
        data_to_plot = [df_clean[ind] for ind in valid_indicators]

        box_plot = ax4.boxplot(data_to_plot, labels=valid_indicators, patch_artist=True,
                            boxprops=dict(alpha=0.7), medianprops=dict(color='red', linewidth=2.5))

        for patch, color in zip(box_plot['boxes'], [colors.get(ind, '#7f8c8d') for ind in valid_indicators]):
            patch.set_facecolor(color)
            patch.set_alpha(0.7)

        ax4.set_ylabel('数值', fontsize=12, fontweight='bold')
        ax4.tick_params(axis='x', labelsize=11)
        ax4.grid(True, alpha=0.3, axis='y')
        ax4.set_title('主要健康指标分布情况', fontsize=14, fontweight='bold', pad=20)

        save_plot_to_bytes('4_健康指标分布.png')
    except Exception as e:
        print(f"❌ 图表4生成失败: {e}")

    # ============ 图表5：微循环相关性分析 ============
    try:
        if '微循环' in df_clean.columns:
            fig5, ax5 = plt.subplots(figsize=(12, 6))
            corr_indicators = ['心率', '血氧', '疲劳指数', '收缩压', '舒张压', '心输出', '外周阻力']
            valid_corr_indicators = [ind for ind in corr_indicators if ind in df_clean.columns]
            correlations = [df_clean['微循环'].corr(df_clean[ind]) for ind in valid_corr_indicators]

            bars = ax5.bar(valid_corr_indicators, correlations, 
                        color=[colors.get(ind, '#7f8c8d') for ind in valid_corr_indicators],
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

            save_plot_to_bytes('5_微循环相关性.png')
    except Exception as e:
        print(f"❌ 图表5生成失败: {e}")

    return generated_images

