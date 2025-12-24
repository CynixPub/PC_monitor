

import os
import json
import time
import sqlite3
from openai import OpenAI
import configparser
from utils import user_data_path


# 1.读取配置文件
from config_handler import ConfigHandler
config = ConfigHandler()

# 2. 平台配置表 (只需修改这里即可切换)
PLATFORM_CONFIG = {
    "deepseek": {
        "config_key": "deepseek",  # 对应 config.conf 中 [API_KEYS] 下的 key
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat"
    },
    "volcengine": {
        "config_key": "volcengine",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "model": "ep-20251224114653-z55vt", # 替换为你的火山引擎 Endpoint ID
    },
    "aliyun": {
        "config_key": "aliyun",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus"# qwen-plus, qwen-max, qwen-turbo
    },
    "openai": {
        "config_key": "openai",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4-1106-preview"
    }
}

# ================= 配置区域 =================
CURRENT_PLATFORM = "deepseek"  # 在这里切换: deepseek, volcengine, aliyun
# ===========================================

def get_api_key_from_config(key_name):
    """从配置文件读取 API Key"""
    try:
        conf = configparser.ConfigParser()
        config_path = user_data_path('config.conf')
        conf.read(config_path, encoding='utf-8')
        
        if 'API_KEYS' not in conf:
            raise ValueError("配置文件中未找到 [API_KEYS] 节")
        
        api_key = conf.get('API_KEYS', key_name).strip()
        if not api_key :
            raise ValueError(f"API Key '{key_name}' 未配置或为占位符")
        
        return api_key
    except configparser.NoOptionError:
        raise ValueError(f"配置文件中未找到 '{key_name}'")
    except Exception as e:
        raise ValueError(f"读取配置文件失败: {e}")

def get_client(platform_name):
    """通用客户端工厂函数"""
    if platform_name not in PLATFORM_CONFIG:
        raise ValueError(f"未知平台: {platform_name}")
    
    platform_config = PLATFORM_CONFIG[platform_name]
    api_key = get_api_key_from_config(platform_config["config_key"])
    
    if not api_key:
        raise ValueError(f"缺少 API Key: {platform_config['config_key']}")
        
    return OpenAI(api_key=api_key, base_url=platform_config["base_url"]), platform_config["model"]

def analyze_health_data_stream(csv_data, platform=None):
    """
    通用流式分析函数
    :param csv_data: CSV格式的健康数据
    :param platform: 平台名称，默认使用 CURRENT_PLATFORM
    :return: 解析后的 JSON 对象 或 None
    """
    # 如果未指定平台，使用全局配置
    if platform is None:
        platform = CURRENT_PLATFORM
    
    client, model_name = get_client(platform)
    
    # System Prompt (保持您的原始设定)
    system_prompt = """

# Role
你是一个专业的健康数据分析引擎。你的任务是接收 CSV 格式的健康监测数据，并输出严格的 JSON 格式分析报告。

# Constraints (关键约束)
1. **数据清洗**：必须忽略所有数值为 0 或空的无效记录。仅基于非零有效数据进行统计。
2. **输出格式**：必须且只能输出标准的 JSON 字符串。
   - 严禁包含 Markdown 标记（如 ```json ... ```）。
   - 严禁包含任何 JSON 以外的解释性文字（如 "好的，这是报告..."）。
3. **语言**：JSON 的 Key 保持英文，Value 使用中文。

# Output Schema (JSON 结构)
你的输出必须符合以下 Schema，不得更改 Key 名称：

{
  "report_meta": {
    "report_date": "YYYY-MM-DD",
    "valid_samples_count": "Integer (有效样本数)"
  },
  "system_analysis": {
    "cardiovascular": {
      "heart_rate_status": "String (含均值及评价)",
      "blood_pressure_status": "String (含收缩/舒张压均值及评价)",
      "cardiac_function": "String"
    },
    "respiratory": {
      "spo2_status": "String (含均值及评价)",
      "spo2_stability": "String"
    },
    "microcirculation": {
      "function_status": "String",
      "stability_status": "String"
    },
    "fatigue_state": {
      "fatigue_index": "String (含均值及评价)",
      "fluctuation": "String"
    }
  },
  "trends_and_correlations": {
    "key_findings": {
      "trends": ["String", "String"],
      "correlations": ["String", "String"]
    }
  },
  "health_evaluation": {
    "overall_score": "Integer (0-100)",
    "rating": "String (一般/良好/优秀)",
    "strengths": ["String", "String"],
    "concerns": ["String", "String"],
    "recommendations": [
      "作息：String",
      "运动：String",
      "饮食：String",
      "习惯：String"
    ]
  },
  "conclusion": "String"
}

# Logic for Recommendations (建议逻辑)
- 若疲劳指数 > 40：增加睡眠与休息策略建议。
- 若血压 > 130/85：增加低盐饮食与有氧运动建议。
- 若血氧 < 95%：建议呼吸训练或就医。
"""

    print(f"🚀 [{platform}] 正在启动流式分析...")
    start_time = time.time()
    first_token_time = None
    full_content = ""
    usage_stats = None

    try:
        # 发起流式请求
        stream = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"分析数据:\n{csv_data}"}
            ],
            temperature=0.1,
            stream=True, # <--- 开启流式
            stream_options={"include_usage": True}, # <--- 关键：请求在流最后返回 Token 统计
            # response_format={"type": "json_object"} # 建议开启，但部分旧模型可能不支持，若报错请注释
        )

        print("📝 生成中: ", end="", flush=True)

        # 实时处理流数据
        for chunk in stream:
            # 1. 捕获内容差量
            if chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_content += content
                
                # 记录首字延迟 (TTFT)
                if first_token_time is None:
                    first_token_time = time.time()
                    print(f"\n⚡ 首字延迟: {first_token_time - start_time:.2f}s")
                    print(content, end="", flush=True)
                else:
                    print(content, end="", flush=True)

            # 2. 捕获 Token 统计 (通常在最后一个 Chunk)
            if hasattr(chunk, 'usage') and chunk.usage:
                usage_stats = chunk.usage

        total_time = time.time() - start_time
        print(f"\n\n✅ 生成结束 (耗时: {total_time:.2f}s)")

        # 3. 后处理：解析 JSON
        try:
            # 清洗可能存在的 Markdown 标记 (如 ```json ... ```) 增加容错
            clean_text = full_content.replace("```json", "").replace("```", "").strip()
            report_json = json.loads(clean_text)

            # 4. 注入性能统计数据
            if "report_meta" in report_json:
                stats = {
                    "platform": platform,
                    "process_time": round(total_time, 2),
                    "ttft": round(first_token_time - start_time, 2) if first_token_time else 0
                }
                # 如果 API 返回了 Token 数，则记录
                if usage_stats:
                    stats["tokens"] = {
                        "prompt": usage_stats.prompt_tokens,
                        "completion": usage_stats.completion_tokens,
                        "total": usage_stats.total_tokens
                    }
                report_json["report_meta"]["engine_stats"] = stats
            
            return report_json

        except json.JSONDecodeError:
            print("❌ JSON 解析失败，完整内容如下:")
            print(clean_text)
            return None

    except Exception as e:
        print(f"\n❌ API 请求中断: {e}")
        return None


def load_health_data_from_db(db_path='history.db'):
    """从 history.db 读取健康数据并转换为 CSV 格式字符串"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 查询健康数据，心率需要除以10转换为实际值
        query = """
            SELECT 
                created_at,
                CAST(heartrate AS REAL) / 10.0 AS heartrate,
                spo2,
                bk,
                fatigue,
                systolic,
                diastolic
            FROM health_data
            ORDER BY created_at DESC
        """
        
        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            print("⚠️ 数据库中没有找到健康数据")
            return None
        
        # 构建 CSV 格式字符串
        csv_lines = ["采集时间,心率,血氧,微循环,疲劳指数,收缩压,舒张压"]
        
        for row in rows:
            created_at, heartrate, spo2, bk, fatigue, systolic, diastolic = row
            csv_lines.append(f"{created_at},{heartrate},{spo2},{bk},{fatigue},{systolic},{diastolic}")
        
        csv_data = "\n".join(csv_lines)
        print(f"✅ 成功从数据库读取 {len(rows)} 条健康数据记录")
        return csv_data
        
    except sqlite3.Error as e:
        print(f"❌ 数据库读取错误: {e}")
        return None
    except FileNotFoundError:
        print(f"❌ 未找到数据库文件: {db_path}")
        return None

if __name__ == "__main__":
    # 从数据库读取健康数据
    sample_csv = load_health_data_from_db('history.db')
    
    if not sample_csv:
        print("❌ 无法读取数据，程序退出")
        exit(1)

    # 执行分析（自动使用 CURRENT_PLATFORM 配置）
    final_report = analyze_health_data_stream(sample_csv)

    if final_report:
        print("\n=== 最终 JSON 报告 ===")
        print(json.dumps(final_report, ensure_ascii=False, indent=2))