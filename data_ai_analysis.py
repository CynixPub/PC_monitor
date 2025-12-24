import json
import time
from openai import OpenAI



# 1.读取配置文件
from config_handler import ConfigHandler
config = ConfigHandler()



def get_client(platform_name):
    """通用客户端工厂函数"""
    platform_config = config.get_platform_config(platform_name)
    
    if not platform_config:
        raise ValueError(f"未知平台或配置缺失: {platform_name}")
    
    api_key = platform_config.get("api_key")
    
    if not api_key or "xxxx" in api_key:
        raise ValueError(f"API Key 无效或未配置 ({platform_name})")
        
    return OpenAI(api_key=api_key, base_url=platform_config["base_url"]), platform_config["model"]

def analyze_health_data_stream(csv_data, platform=None, progress_callback=None):
    """
    通用流式分析函数
    :param csv_data: CSV格式的健康数据
    :param platform: 平台名称，默认使用 config.conf 中的配置
    :param progress_callback: 进度回调函数，接收 (full_content)
    :return: 解析后的 JSON 对象 或 None
    """
    # 如果未指定平台，使用全局配置
    if platform is None:
        platform = config.get_ai_platform()
    
    try:
        client, model_name = get_client(platform)
    except ValueError as e:
        error_msg = f"配置错误: {str(e)}\n请检查 config.conf 中的 API Key 配置。"
        print(error_msg)
        return {
            "report_meta": {"valid_samples_count": 0},
            "conclusion": error_msg,
            "health_evaluation": {"overall_score": 0, "rating": "配置错误"}
        }
    
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
            response_format={"type": "json_object"} # 强制输出 JSON 格式，防止结构错误
        )

        print("📝 生成中: ", end="", flush=True)

        # 实时处理流数据
        for chunk in stream:
            # 1. 捕获内容差量
            if chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_content += content
                
                if progress_callback:
                    progress_callback(full_content)

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


def generate_analysis_report(df, progress_callback=None):
    """
    根据 DataFrame 生成 AI 分析报告
    :param df: 包含健康数据的 DataFrame
    :param progress_callback: 进度回调函数
    :return: 解析后的 JSON 对象 或 None
    """
    if df is None or df.empty:
        print("⚠️ DataFrame 为空，无法生成报告")
        return None
    
    # 简单的列名映射
    column_map = {
        'created_at': '采集时间',
        'heartrate': '心率',
        'spo2': '血氧',
        'bk': '微循环',
        'fatigue': '疲劳指数',
        'systolic': '收缩压',
        'diastolic': '舒张压',
        'cardiac': '心输出',
        'resistance': '外周阻力'
    }
    df_renamed = df.rename(columns=column_map)
    
    csv_data = df_renamed.to_csv(index=False)
    return analyze_health_data_stream(csv_data, progress_callback=progress_callback)
