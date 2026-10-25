#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified Scanner for Antigravity (AGY) & OpenAI Codex
Extracts token usage, caching, models, conversations, daily & hourly timelines.
Pure Python standard library (no third-party dependencies).
"""

import os
import re
import glob
import json
import shutil
import sqlite3
import datetime
from collections import defaultdict

try:
    import zstandard as zstd
except ImportError:
    zstd = None

UUID_PATTERN = re.compile(r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})")

AGY_MODEL_MAP = {
    1016: "Gemini 1.5 Pro",
    1026: "Gemini 1.5 Flash",
    1036: "Gemini 2.0 Flash",
    1050: "Gemini 2.0 Pro",
    1298: "Gemini 3.7 Flash",
    1299: "Gemini 3.7 Flash",
    1300: "Gemini 3.7 Pro",
    1318: "Gemini 3.8 Flash",
    1319: "Gemini 3.8 Flash",
    1320: "Gemini 3.8 Pro",
    1417: "Gemini 4 Argon",
    1418: "Gemini 4 Argon",
    1419: "Gemini 4 Argon",
    1420: "Gemini 4 Argon",
    1421: "Gemini 4 Argon",
}

USD_TO_CNY = 7.25

def normalize_model_name(name: str) -> str:
    """归一化模型名称，剔除思考强度后缀与日期戳并规范化命名 (支持 Gemini, Claude 等)"""
    if not name:
        return ""
    s = str(name).strip()
    s_lower = s.lower()

    # --- Google Gemini 系列 ---
    if "argon" in s_lower or "gemini-4" in s_lower or "gemini 4" in s_lower:
        return "Gemini 4 Argon"
    if "3.8" in s and "flash" in s_lower:
        return "Gemini 3.8 Flash"
    if "3.8" in s and "pro" in s_lower:
        return "Gemini 3.8 Pro"
    if "3.7" in s and "flash" in s_lower:
        return "Gemini 3.7 Flash"
    if "3.7" in s and "pro" in s_lower:
        return "Gemini 3.7 Pro"
    if s in ("Gemini 3.8 Flash (High)", "Gemini 3.8 Flash (Low)"):
        return "Gemini 3.8 Flash"
    if s in ("Gemini 3.7 Flash (High)", "Gemini 3.7 Flash (Low)"):
        return "Gemini 3.7 Flash"

    # --- Anthropic Claude 系列 (剔除日期后缀避免误判如 2024、2025 年份中的数字) ---
    s_clean = re.sub(r'[-_]202\d{5}', '', s_lower)
    if "fable" in s_clean:
        if "5.1" in s_clean or "5-1" in s_clean:
            return "Claude Fable 5.1"
        return "Claude Fable 5"
    if "opus" in s_clean:
        if "5.5" in s_clean or "5-5" in s_clean:
            return "Claude Opus 5.5"
        if "5" in s_clean:
            return "Claude Opus 5"
        if "4.7" in s_clean or "4-7" in s_clean or "4" in s_clean:
            return "Claude Opus 4.7"
        if "3" in s_clean:
            return "Claude 3 Opus"
        return "Claude Opus 5.5"
    if "sonnet" in s_clean:
        if "5.5" in s_clean or "5-5" in s_clean or "5" in s_clean:
            if "3" not in s_clean:
                return "Claude Sonnet 5.5"
        if "3.7" in s_clean or "3-7" in s_clean:
            return "Claude 3.7 Sonnet"
        if "3.5" in s_clean or "3-5" in s_clean:
            return "Claude 3.5 Sonnet"
        if "3" in s_clean:
            return "Claude 3 Sonnet"
        return "Claude 3.7 Sonnet"
    if "haiku" in s_clean:
        if "5.5" in s_clean or "5-5" in s_clean or "5" in s_clean:
            if "3" not in s_clean:
                return "Claude Haiku 5.5"
        if "3.5" in s_clean or "3-5" in s_clean:
            return "Claude 3.5 Haiku"
        if "3" in s_clean:
            return "Claude 3 Haiku"
        return "Claude 3.5 Haiku"
    if "instant" in s_clean:
        return "Claude Instant 1.2"
    if "claude-2" in s_clean or "claude 2" in s_clean:
        return "Claude 2.1"
    if s_clean == "claude":
        return "Claude 3.7 Sonnet"

    return s

# 官方公开标准 API 单价 (单位: 美元 / 每 1,000,000 Tokens)
# uncached: 未缓存输入单价, cached: 缓存命中输入单价, output: 输出单价 (含思考Token)
MODEL_PRICING = {
    # --- Google Gemini 系列 (Antigravity & OpenCode) ---
    "Gemini 4 Argon":          {"uncached": 2.00, "cached": 0.10, "output": 10.00, "currency": "USD"},
    "gemini-4-argon":          {"uncached": 2.00, "cached": 0.10, "output": 10.00, "currency": "USD"},
    "Gemini 3.8 Pro":          {"uncached": 1.25, "cached": 0.3125, "output": 5.00, "currency": "USD"},
    "Gemini 3.8 Flash":        {"uncached": 0.10, "cached": 0.025, "output": 0.40, "currency": "USD"},
    "Gemini 3.7 Flash":        {"uncached": 0.10, "cached": 0.025, "output": 0.40, "currency": "USD"},
    "Gemini 2.0 Flash":        {"uncached": 0.10, "cached": 0.025, "output": 0.40, "currency": "USD"},
    "Gemini 1.5 Flash":        {"uncached": 0.075, "cached": 0.01875, "output": 0.30, "currency": "USD"},
    "Gemini 3.7 Pro":          {"uncached": 1.25, "cached": 0.3125, "output": 5.00, "currency": "USD"},
    "Gemini 2.0 Pro":          {"uncached": 1.25, "cached": 0.3125, "output": 5.00, "currency": "USD"},
    "Gemini 1.5 Pro":          {"uncached": 1.25, "cached": 0.3125, "output": 5.00, "currency": "USD"},
    # 兼容历史缓存数据的旧键
    "Gemini 4 Argon (High)":   {"uncached": 2.00, "cached": 0.10, "output": 10.00, "currency": "USD"},
    "Gemini 4 Argon (Medium)": {"uncached": 2.00, "cached": 0.10, "output": 10.00, "currency": "USD"},
    "Gemini 4 Argon (Low)":    {"uncached": 2.00, "cached": 0.10, "output": 10.00, "currency": "USD"},
    "gemini-4-argon-high":     {"uncached": 2.00, "cached": 0.10, "output": 10.00, "currency": "USD"},
    "gemini-4-argon-medium":   {"uncached": 2.00, "cached": 0.10, "output": 10.00, "currency": "USD"},
    "gemini-4-argon-low":      {"uncached": 2.00, "cached": 0.10, "output": 10.00, "currency": "USD"},
    "Gemini 3.8 Flash (High)": {"uncached": 0.10, "cached": 0.025, "output": 0.40, "currency": "USD"},
    "Gemini 3.8 Flash (Low)":  {"uncached": 0.10, "cached": 0.025, "output": 0.40, "currency": "USD"},
    "Gemini 3.7 Flash (High)": {"uncached": 0.10, "cached": 0.025, "output": 0.40, "currency": "USD"},
    "Gemini 3.7 Flash (Low)":  {"uncached": 0.10, "cached": 0.025, "output": 0.40, "currency": "USD"},

    # --- OpenAI Codex 系列 ---
    "gpt-6-astra":   {"uncached": 5.00, "cached": 2.50, "output": 20.00, "currency": "USD"},
    "gpt-6.1-sol":   {"uncached": 2.50, "cached": 1.25, "output": 10.00, "currency": "USD"},
    "gpt-6-sol":     {"uncached": 2.50, "cached": 1.25, "output": 10.00, "currency": "USD"},
    "gpt-5.6-sol":   {"uncached": 2.50, "cached": 1.25, "output": 10.00, "currency": "USD"},
    "gpt-5.6-terra": {"uncached": 1.00, "cached": 0.50, "output": 4.00, "currency": "USD"},
    "gpt-6-luna":    {"uncached": 0.15, "cached": 0.075, "output": 0.60, "currency": "USD"},
    "gpt-5.6-luna":  {"uncached": 0.15, "cached": 0.075, "output": 0.60, "currency": "USD"},
    "gpt-4o":        {"uncached": 2.50, "cached": 1.25, "output": 10.00, "currency": "USD"},
    "gpt-4o-mini":   {"uncached": 0.15, "cached": 0.075, "output": 0.60, "currency": "USD"},
    "o1":            {"uncached": 15.00, "cached": 7.50, "output": 60.00, "currency": "USD"},
    "o3-mini":       {"uncached": 1.10, "cached": 0.55, "output": 4.40, "currency": "USD"},

    # --- DeepSeek 系列 ---
    "deepseek-flash":    {"uncached": 0.14, "cached": 0.014, "output": 0.28, "currency": "USD"},
    "deepseek-v4-flash": {"uncached": 0.14, "cached": 0.014, "output": 0.28, "currency": "USD"},
    "deepseek-chat":     {"uncached": 0.14, "cached": 0.014, "output": 0.28, "currency": "USD"},
    "deepseek-v4-pro":   {"uncached": 0.55, "cached": 0.14, "output": 2.19, "currency": "USD"},
    "deepseek-reasoner": {"uncached": 0.55, "cached": 0.14, "output": 2.19, "currency": "USD"},
    "deepseek-r1":       {"uncached": 0.55, "cached": 0.14, "output": 2.19, "currency": "USD"},

    # --- OpenCode / 通用国产旗舰 ---
    "glm-5.2":           {"uncached": 1.00, "cached": 0.20, "output": 2.00, "currency": "USD"},
    "qwen3.7-max":       {"uncached": 2.50, "cached": 0.60, "output": 10.00, "currency": "USD"},
    "minimax-m3":        {"uncached": 1.00, "cached": 0.25, "output": 4.00, "currency": "USD"},

    # --- Anthropic Claude 系列 (全代际完整官方阶梯单价) ---
    # Fable 系列 (顶级前沿长思维链推理与智能体旗舰)
    "Claude Fable 5.1":        {"uncached": 10.00, "cached": 0.25,  "output": 50.00, "currency": "USD"},
    "claude-fable-5.1":        {"uncached": 10.00, "cached": 0.25,  "output": 50.00, "currency": "USD"},
    "claude-fable-5-1":        {"uncached": 10.00, "cached": 0.25,  "output": 50.00, "currency": "USD"},
    "Claude Fable 5":          {"uncached": 10.00, "cached": 1.00,  "output": 50.00, "currency": "USD"},
    "claude-fable-5":          {"uncached": 10.00, "cached": 1.00,  "output": 50.00, "currency": "USD"},
    "claude-fable":            {"uncached": 10.00, "cached": 1.00,  "output": 50.00, "currency": "USD"},

    # Opus 系列 (顶尖架构设计、深度推演与代码重构旗舰)
    "Claude Opus 5.5":         {"uncached": 4.00,  "cached": 0.20,  "output": 20.00, "currency": "USD"},
    "claude-opus-5.5":         {"uncached": 4.00,  "cached": 0.20,  "output": 20.00, "currency": "USD"},
    "claude-opus-5-5":         {"uncached": 4.00,  "cached": 0.20,  "output": 20.00, "currency": "USD"},
    "Claude Opus 5":           {"uncached": 5.00,  "cached": 0.50,  "output": 25.00, "currency": "USD"},
    "claude-opus-5":           {"uncached": 5.00,  "cached": 0.50,  "output": 25.00, "currency": "USD"},
    "Claude Opus 4.7":         {"uncached": 15.00, "cached": 1.50,  "output": 75.00, "currency": "USD"},
    "claude-opus-4-7":         {"uncached": 15.00, "cached": 1.50,  "output": 75.00, "currency": "USD"},
    "claude-opus-4.7":         {"uncached": 15.00, "cached": 1.50,  "output": 75.00, "currency": "USD"},
    "Claude 3 Opus":           {"uncached": 15.00, "cached": 1.50,  "output": 75.00, "currency": "USD"},
    "claude-3-opus":           {"uncached": 15.00, "cached": 1.50,  "output": 75.00, "currency": "USD"},
    "claude-3-opus-20240229":  {"uncached": 15.00, "cached": 1.50,  "output": 75.00, "currency": "USD"},

    # Sonnet 系列 (主力均衡与代码基准旗舰)
    "Claude Sonnet 5.5":       {"uncached": 2.00,  "cached": 0.10,  "output": 10.00, "currency": "USD"},
    "claude-sonnet-5.5":       {"uncached": 2.00,  "cached": 0.10,  "output": 10.00, "currency": "USD"},
    "claude-sonnet-5-5":       {"uncached": 2.00,  "cached": 0.10,  "output": 10.00, "currency": "USD"},
    "Claude 3.7 Sonnet":       {"uncached": 3.00,  "cached": 0.30,  "output": 15.00, "currency": "USD"},
    "claude-3-7-sonnet":       {"uncached": 3.00,  "cached": 0.30,  "output": 15.00, "currency": "USD"},
    "claude-3.7-sonnet":       {"uncached": 3.00,  "cached": 0.30,  "output": 15.00, "currency": "USD"},
    "claude-3-7-sonnet-20250219": {"uncached": 3.00, "cached": 0.30, "output": 15.00, "currency": "USD"},
    "Claude 3.5 Sonnet":       {"uncached": 3.00,  "cached": 0.30,  "output": 15.00, "currency": "USD"},
    "claude-3-5-sonnet":       {"uncached": 3.00,  "cached": 0.30,  "output": 15.00, "currency": "USD"},
    "claude-3.5-sonnet":       {"uncached": 3.00,  "cached": 0.30,  "output": 15.00, "currency": "USD"},
    "claude-3-5-sonnet-20241022": {"uncached": 3.00, "cached": 0.30, "output": 15.00, "currency": "USD"},
    "claude-3-5-sonnet-20240620": {"uncached": 3.00, "cached": 0.30, "output": 15.00, "currency": "USD"},
    "Claude 3 Sonnet":         {"uncached": 3.00,  "cached": 0.30,  "output": 15.00, "currency": "USD"},
    "claude-3-sonnet":         {"uncached": 3.00,  "cached": 0.30,  "output": 15.00, "currency": "USD"},
    "claude-3-sonnet-20240229": {"uncached": 3.00, "cached": 0.30, "output": 15.00, "currency": "USD"},

    # Haiku 系列 (极速轻量吞吐)
    "Claude Haiku 5.5":        {"uncached": 0.10,  "cached": 0.01,  "output": 0.50,  "currency": "USD"},
    "claude-haiku-5.5":        {"uncached": 0.10,  "cached": 0.01,  "output": 0.50,  "currency": "USD"},
    "claude-haiku-5-5":        {"uncached": 0.10,  "cached": 0.01,  "output": 0.50,  "currency": "USD"},
    "Claude 3.5 Haiku":        {"uncached": 0.80,  "cached": 0.08,  "output": 4.00,  "currency": "USD"},
    "claude-3-5-haiku":        {"uncached": 0.80,  "cached": 0.08,  "output": 4.00,  "currency": "USD"},
    "claude-3.5-haiku":        {"uncached": 0.80,  "cached": 0.08,  "output": 4.00,  "currency": "USD"},
    "claude-3-5-haiku-20241022": {"uncached": 0.80, "cached": 0.08, "output": 4.00, "currency": "USD"},
    "Claude 3 Haiku":          {"uncached": 0.25,  "cached": 0.025, "output": 1.25,  "currency": "USD"},
    "claude-3-haiku":          {"uncached": 0.25,  "cached": 0.025, "output": 1.25,  "currency": "USD"},
    "claude-3-haiku-20240307": {"uncached": 0.25,  "cached": 0.025, "output": 1.25,  "currency": "USD"},

    # 经典与轻量历史版本
    "Claude 2.1":              {"uncached": 8.00,  "cached": 2.00,  "output": 24.00, "currency": "USD"},
    "claude-2.1":              {"uncached": 8.00,  "cached": 2.00,  "output": 24.00, "currency": "USD"},
    "Claude Instant 1.2":      {"uncached": 0.80,  "cached": 0.20,  "output": 2.40,  "currency": "USD"},
    "claude-instant-1.2":      {"uncached": 0.80,  "cached": 0.20,  "output": 2.40,  "currency": "USD"},
}

def get_pricing_for_model(model_name: str) -> dict:
    if not model_name:
        return {"uncached": 1.00, "cached": 0.25, "output": 4.00, "currency": "USD"}
    model_name = normalize_model_name(model_name)
    if model_name in MODEL_PRICING:
        return MODEL_PRICING[model_name]
    
    m_lower = model_name.lower()
    if "fable" in m_lower:
        return {"uncached": 10.00, "cached": 0.25, "output": 50.00, "currency": "USD"}
    elif "opus" in m_lower:
        if "5" in m_lower:
            return {"uncached": 4.00, "cached": 0.20, "output": 20.00, "currency": "USD"}
        return {"uncached": 15.00, "cached": 1.50, "output": 75.00, "currency": "USD"}
    elif "sonnet" in m_lower:
        if "5" in m_lower:
            return {"uncached": 2.00, "cached": 0.10, "output": 10.00, "currency": "USD"}
        return {"uncached": 3.00, "cached": 0.30, "output": 15.00, "currency": "USD"}
    elif "haiku" in m_lower:
        if "5" in m_lower:
            return {"uncached": 0.10, "cached": 0.01, "output": 0.50, "currency": "USD"}
        return {"uncached": 0.80, "cached": 0.08, "output": 4.00, "currency": "USD"}
    elif "argon" in m_lower:
        return {"uncached": 2.00, "cached": 0.10, "output": 10.00, "currency": "USD"}
    elif "flash" in m_lower or "luna" in m_lower or "mini" in m_lower:
        return {"uncached": 0.10, "cached": 0.025, "output": 0.40, "currency": "USD"}
    elif "pro" in m_lower or "astra" in m_lower or "reasoner" in m_lower or "r1" in m_lower:
        return {"uncached": 2.50, "cached": 0.625, "output": 10.00, "currency": "USD"}
    else:
        return {"uncached": 1.00, "cached": 0.25, "output": 4.00, "currency": "USD"}

def calc_cost(uncached_in: int, cached_in: int, output_tokens: int, model_name: str) -> float:
    p = get_pricing_for_model(model_name)
    cost = (uncached_in * p["uncached"] + cached_in * p["cached"] + output_tokens * p["output"]) / 1_000_000.0
    return cost

def decode_protobuf(data: bytes) -> dict:
    i = 0
    res = {}
    length_data = len(data)
    while i < length_data:
        shift = 0
        key = 0
        while True:
            if i >= length_data: return res
            b = data[i]
            i += 1
            key |= (b & 0x7F) << shift
            shift += 7
            if not (b & 0x80): break
        field_num = key >> 3
        wire_type = key & 7

        if wire_type == 0:  # varint
            val = 0
            shift = 0
            while True:
                if i >= length_data: break
                b = data[i]
                i += 1
                val |= (b & 0x7F) << shift
                shift += 7
                if not (b & 0x80): break
            res[field_num] = val
        elif wire_type == 2:  # length-delimited
            length = 0
            shift = 0
            while True:
                if i >= length_data: break
                b = data[i]
                i += 1
                length |= (b & 0x7F) << shift
                shift += 7
                if not (b & 0x80): break
            subdata = data[i : i + length]
            i += length
            res[field_num] = subdata
        elif wire_type == 1:  # 64-bit
            i += 8
        elif wire_type == 5:  # 32-bit
            i += 4
        else:
            break
    return res

def scan_antigravity(gemini_dir: str, start_ts: float, end_ts: float):
    dbs = glob.glob(os.path.join(gemini_dir, "*", "conversations", "*.db"))
    records = []
    convo_stats = defaultdict(lambda: {
        "calls": 0, "uncached_in": 0, "cached_in": 0, "total_in": 0,
        "cand_out": 0, "thinking": 0, "text_out": 0, "app": "", "client": "Antigravity", "title": "", "model": "", "cost_usd": 0.0
    })
    seen_step_signatures = set()

    for db_path in dbs:
        try:
            mtime = os.path.getmtime(db_path)
            wal_path = db_path + "-wal"
            if os.path.exists(wal_path):
                try:
                    wal_m = os.path.getmtime(wal_path)
                    mtime = max(mtime, wal_m)
                except Exception:
                    pass
            if start_ts > 0 and mtime < (start_ts - 300):
                continue

            app = "CLI" if "antigravity-cli" in db_path else ("IDE" if "antigravity-ide" in db_path else "Desktop")
            convo_id = os.path.splitext(os.path.basename(db_path))[0]

            # 尝试提取会话标题
            title = convo_id
            annot_path = os.path.join(os.path.dirname(os.path.dirname(db_path)), "annotations", f"{convo_id}.pbtxt")
            if os.path.isfile(annot_path):
                try:
                    with open(annot_path, "r", encoding="utf-8", errors="ignore") as afp:
                        m = re.search(r'title:\s*"([^"]+)"', afp.read())
                        if m and m.group(1).strip():
                            title = m.group(1).strip()
                except Exception:
                    pass

            conn = sqlite3.connect(f"file:{os.path.abspath(db_path)}?mode=ro", uri=True)
            cursor = conn.cursor()

            # 过滤 Side Question / 分叉会话克隆的父会话历史步骤
            min_idx = 0
            try:
                pref_rows = cursor.execute("SELECT * FROM parent_references").fetchall()
                for pr in pref_rows:
                    p = decode_protobuf(pr[1])
                    pid = p.get(6, b'').decode('utf-8', errors='ignore') if isinstance(p.get(6), bytes) else p.get(6)
                    fidx = p.get(2, 0)
                    if pid and pid != convo_id:
                        min_idx = max(min_idx, fidx + 1)
                        if title == convo_id:
                            title = f"(Side Question) {convo_id[:8]}"
            except Exception:
                pass

            rows = cursor.execute("SELECT idx, metadata FROM steps WHERE metadata IS NOT NULL AND idx >= ?", (min_idx,)).fetchall()
            for r in rows:
                meta_bytes = r[1]
                if not meta_bytes: continue
                p = decode_protobuf(meta_bytes)
                ts = None
                if 1 in p and isinstance(p[1], bytes):
                    ts_p = decode_protobuf(p[1])
                    if 1 in ts_p: ts = ts_p[1]

                if not ts or ts < start_ts or ts > end_ts:
                    continue

                if 9 in p and isinstance(p[9], bytes):
                    sub_p = decode_protobuf(p[9])
                    model_id = sub_p.get(1, 0)
                    uncached_in = sub_p.get(2, 0)
                    cand_out = sub_p.get(3, 0)
                    cached_in = sub_p.get(5, 0)
                    thinking = sub_p.get(9, 0)
                    text_out = sub_p.get(10, 0)

                    # 全局步骤签名去重，彻底阻断数据库镜像或分叉克隆的重复统计
                    sig = (round(ts, 1), uncached_in, cached_in, cand_out)
                    if sig in seen_step_signatures:
                        continue
                    seen_step_signatures.add(sig)

                    model_name = AGY_MODEL_MAP.get(model_id, f"Model-{model_id}")
                    cost_usd = calc_cost(uncached_in, cached_in, cand_out, model_name)
                    dt_obj = datetime.datetime.fromtimestamp(ts)
                    rec = {
                        "ts": ts,
                        "dt_str": dt_obj.strftime("%Y-%m-%d %H:%M:%S"),
                        "day": dt_obj.strftime("%Y-%m-%d"),
                        "hour": dt_obj.strftime("%Y-%m-%d %H:00"),
                        "client": "Antigravity",
                        "app": app,
                        "convo_id": convo_id,
                        "title": title,
                        "model": model_name,
                        "uncached_in": uncached_in,
                        "cached_in": cached_in,
                        "total_in": uncached_in + cached_in,
                        "cand_out": cand_out,
                        "thinking": thinking,
                        "text_out": text_out,
                        "total": uncached_in + cached_in + cand_out,
                        "cost_usd": cost_usd,
                    }
                    records.append(rec)

                    cs = convo_stats[convo_id]
                    cs["calls"] += 1
                    cs["uncached_in"] += uncached_in
                    cs["cached_in"] += cached_in
                    cs["total_in"] += (uncached_in + cached_in)
                    cs["cand_out"] += cand_out
                    cs["thinking"] += thinking
                    cs["text_out"] += text_out
                    cs["client"] = "Antigravity"
                    cs["app"] = app
                    cs["title"] = title
                    cs["model"] = model_name
                    cs["cost_usd"] += cost_usd
            conn.close()
        except Exception:
            pass

    return records, convo_stats

def scan_codex(codex_dir: str, start_ts: float, end_ts: float):
    thread_map = {}
    db_candidates = glob.glob(os.path.join(codex_dir, "state_*.sqlite"))
    if db_candidates:
        db_candidates.sort(reverse=True)
        try:
            conn = sqlite3.connect(f"file:{os.path.abspath(db_candidates[0])}?mode=ro", uri=True)
            cursor = conn.cursor()
            for r in cursor.execute("SELECT id, title, model, tokens_used, created_at, updated_at FROM threads").fetchall():
                title = r[1] if (r[1] and r[1].strip()) else "(无标题会话)"
                title = " ".join(title.split())
                thread_map[r[0]] = {"title": title, "model": r[2] if r[2] else "unknown", "updated_at": r[5] or 0}
            conn.close()
        except Exception:
            pass

    session_dirs = [os.path.join(codex_dir, "sessions"), os.path.join(codex_dir, "archived_sessions")]
    all_files = []
    for sdir in session_dirs:
        if os.path.isdir(sdir):
            all_files.extend(glob.glob(os.path.join(sdir, "**", "*.jsonl"), recursive=True))

    records = []
    convo_stats = defaultdict(lambda: {
        "calls": 0, "uncached_in": 0, "cached_in": 0, "total_in": 0,
        "cand_out": 0, "thinking": 0, "text_out": 0, "model": "", "title": "", "client": "Codex", "app": "CLI", "cost_usd": 0.0
    })
    rate_limits = None

    for f_path in all_files:
        try:
            mtime = os.path.getmtime(f_path)
            fname = os.path.basename(f_path)
            m = UUID_PATTERN.search(fname)
            thread_id = m.group(1) if m else fname
            t_info = thread_map.get(thread_id, {})
            current_model = t_info.get("model", "unknown")
            current_title = t_info.get("title", "(无标题会话)")
            thread_updated = t_info.get("updated_at", 0)

            # 关键修复：Windows NTFS 在文件持续打开写入时，LastWriteTime 经常滞后未写回目录项；
            # 且用户跨天续聊时，文件创建于历史日期，但最新追加写入依然活跃。
            # 因此使用 state_*.sqlite 的 updated_at 与文件 mtime 两者最大值作为有效时间；
            # 且当会话文件总数较少时（<= 200 个），直接全量进入精确时间戳解析，彻底防止漏统！
            effective_mtime = max(mtime, thread_updated)
            if start_ts > 0 and effective_mtime < (start_ts - 300):
                continue

            is_subagent = False
            child_trigger_passed = True

            with open(f_path, "r", encoding="utf-8", errors="ignore") as f:
                first_line = f.readline()
                if first_line:
                    try:
                        m0 = json.loads(first_line)
                        if m0.get("type") == "session_meta":
                            p0 = m0.get("payload", {})
                            if p0.get("parent_thread_id") or ("subagent" in p0.get("source", {})):
                                is_subagent = True
                                child_trigger_passed = False
                                nickname = p0.get("agent_nickname")
                                if nickname and f"({nickname})" not in current_title:
                                    current_title = f"{current_title} ({nickname})"
                    except Exception:
                        pass

                f.seek(0)
                for line in f:
                    if not line.strip():
                        continue

                    # 子智能体会话：跳过激活前的父会话全量克隆历史
                    if is_subagent and not child_trigger_passed:
                        if "inter_agent_communication_metadata" in line:
                            child_trigger_passed = True
                        continue

                    if "token_count" not in line and "thread_settings_applied" not in line:
                        continue

                    try:
                        data = json.loads(line)
                    except Exception:
                        continue

                    t = data.get("type")
                    if t != "event_msg": continue
                    payload = data.get("payload", {})
                    p_type = payload.get("type")

                    if p_type == "thread_settings_applied":
                        sm = payload.get("thread_settings", {}).get("model")
                        if sm: current_model = sm
                    elif p_type == "token_count":
                        info = payload.get("info", {})
                        last = info.get("last_token_usage")
                        if not last: continue

                        ts_str = data.get("timestamp")
                        dt = None
                        if ts_str:
                            try:
                                dt = datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00")).astimezone()
                            except Exception:
                                pass
                        if dt:
                            ts = dt.timestamp()
                        else:
                            ts = mtime
                            dt = datetime.datetime.fromtimestamp(ts)

                        if ts < start_ts or ts > end_ts:
                            continue

                        rl = payload.get("rate_limits")
                        if rl: rate_limits = rl

                        input_tokens = last.get("input_tokens", 0)
                        cached_in = last.get("cached_input_tokens", 0)
                        uncached_in = max(0, input_tokens - cached_in)
                        output_tokens = last.get("output_tokens", 0)
                        thinking = last.get("reasoning_output_tokens", 0)
                        text_out = max(0, output_tokens - thinking)
                        total_step = last.get("total_tokens", input_tokens + output_tokens)

                        cost_usd = calc_cost(uncached_in, cached_in, output_tokens, current_model)

                        rec = {
                            "ts": ts,
                            "dt_str": dt.strftime("%Y-%m-%d %H:%M:%S"),
                            "day": dt.strftime("%Y-%m-%d"),
                            "hour": dt.strftime("%Y-%m-%d %H:00"),
                            "client": "Codex",
                            "app": "CLI",
                            "convo_id": thread_id,
                            "title": current_title,
                            "model": current_model,
                            "uncached_in": uncached_in,
                            "cached_in": cached_in,
                            "total_in": input_tokens,
                            "cand_out": output_tokens,
                            "thinking": thinking,
                            "text_out": text_out,
                            "total": total_step,
                            "cost_usd": cost_usd,
                        }
                        records.append(rec)

                        cs = convo_stats[thread_id]
                        cs["calls"] += 1
                        cs["uncached_in"] += uncached_in
                        cs["cached_in"] += cached_in
                        cs["total_in"] += input_tokens
                        cs["cand_out"] += output_tokens
                        cs["thinking"] += thinking
                        cs["text_out"] += text_out
                        cs["client"] = "Codex"
                        cs["app"] = "CLI"
                        cs["model"] = current_model
                        cs["title"] = current_title
                        cs["cost_usd"] += cost_usd
        except Exception:
            pass

    return records, convo_stats, rate_limits

def scan_deepseek(dsh_dir: str, start_ts: float, end_ts: float):
    if not os.path.isdir(dsh_dir):
        return [], defaultdict(lambda: {
            "calls": 0, "uncached_in": 0, "cached_in": 0, "total_in": 0,
            "cand_out": 0, "thinking": 0, "text_out": 0, "client": "DeepSeek", "app": "Harness", "model": "", "title": "",
            "cost_usd": 0.0
        })

    # 1. 预加载 session_projcache 映射标题与基础元数据
    title_map = {}
    proj_totals = {}
    projcache_pattern = os.path.join(dsh_dir, "storages", "session_projcache", "sessions", "*.json")
    for ppath in glob.glob(projcache_pattern):
        sid = os.path.splitext(os.path.basename(ppath))[0]
        try:
            with open(ppath, "r", encoding="utf-8", errors="ignore") as f:
                pdata = json.load(f)
                rows = pdata.get("record", {}).get("rows", {})
                title = rows.get("title", {}).get("val")
                if not title:
                    t_in = rows.get("titleInput", {}).get("val", {}).get("first", {}).get("text")
                    if t_in: title = t_in[:30]
                if title:
                    title_map[sid] = title

                created_at = pdata.get("record", {}).get("identity", {}).get("createdAt")
                model = rows.get("modelSelection", {}).get("val", {}).get("lastUsed", {}).get("model", "deepseek-chat")
                token_usage = rows.get("tokenUsage", {}).get("val", {}).get("totals", {})
                proj_totals[sid] = {
                    "title": title or "(无标题会话)",
                    "createdAt": created_at,
                    "model": model,
                    "tokenUsage": token_usage
                }
        except Exception:
            pass

    records = []
    convo_stats = defaultdict(lambda: {
        "calls": 0, "uncached_in": 0, "cached_in": 0, "total_in": 0,
        "cand_out": 0, "thinking": 0, "text_out": 0, "client": "DeepSeek", "app": "Harness", "model": "", "title": "",
        "cost_usd": 0.0
    })

    session_root = os.path.join(dsh_dir, "sessions")
    if not os.path.isdir(session_root):
        return records, convo_stats

    # 递归查找所有会话文件
    session_files = []
    for root, dirs, files in os.walk(session_root):
        for f in files:
            if f.endswith((".jsonl.zstd", ".jsonl")):
                session_files.append(os.path.join(root, f))

    dctx = zstd.ZstdDecompressor() if zstd else None
    scanned_session_ids = set()

    for fpath in session_files:
        try:
            mtime = os.path.getmtime(fpath)
            if start_ts > 0 and mtime < (start_ts - 300):
                continue

            parent_dir = os.path.basename(os.path.dirname(fpath))
            session_id = parent_dir if parent_dir.startswith("session-") else os.path.splitext(os.path.basename(fpath))[0]
            scanned_session_ids.add(session_id)
            current_title = title_map.get(session_id, "(无标题会话)")

            raw_bytes = None
            if fpath.endswith(".zstd"):
                if not dctx:
                    continue
                with open(fpath, "rb") as f:
                    with dctx.stream_reader(f) as reader:
                        raw_bytes = reader.read()
            else:
                with open(fpath, "rb") as f:
                    raw_bytes = f.read()

            if not raw_bytes:
                continue

            lines = raw_bytes.decode("utf-8", errors="ignore").splitlines()
            inherited_event_count = 0

            for line in lines:
                if not line.strip():
                    continue

                try:
                    event = json.loads(line)
                except Exception:
                    continue

                etype = event.get("type")
                if etype == "session":
                    inherited_event_count = event.get("inheritedEventCount", 0)
                    continue

                # 继承自父会话/子代理的历史步骤去重
                seq = event.get("seq", 0)
                if inherited_event_count > 0 and seq <= inherited_event_count:
                    continue

                edata = event.get("data", {})
                if etype == "session/title":
                    t = edata.get("title")
                    if t and t.strip():
                        current_title = t.strip()
                    continue

                if etype != "assistant/message":
                    continue

                etime = event.get("time")
                ts = (etime / 1000.0) if etime else mtime

                if ts < start_ts or ts > end_ts:
                    continue

                msg = edata.get("message", {})
                src = msg.get("source", {})
                model_name = src.get("model") or "deepseek-chat"

                usage = edata.get("usage", {})
                if not usage:
                    continue

                uncached_in = usage.get("inputTokens", 0)
                cached_in = usage.get("cacheReadTokens", 0)
                cache_write = usage.get("cacheWriteTokens", 0)
                total_in = uncached_in + cached_in + cache_write
                output_tokens = usage.get("outputTokens", 0)
                thinking = usage.get("reasoningTokens", 0)

                # 若 usage 中无 reasoningTokens，尝试从 content 块估算
                if thinking == 0 and "content" in msg:
                    for part in msg["content"]:
                        if isinstance(part, dict) and part.get("type") == "reasoning":
                            rtext = part.get("text", "")
                            if rtext:
                                thinking = len(rtext) // 3

                text_out = max(0, output_tokens - thinking)
                total_step = usage.get("totalTokens", total_in + output_tokens)

                cost_usd = calc_cost(uncached_in, cached_in, output_tokens, model_name)
                dt_obj = datetime.datetime.fromtimestamp(ts)
                rec = {
                    "ts": ts,
                    "dt_str": dt_obj.strftime("%Y-%m-%d %H:%M:%S"),
                    "day": dt_obj.strftime("%Y-%m-%d"),
                    "hour": dt_obj.strftime("%Y-%m-%d %H:00"),
                    "client": "DeepSeek",
                    "app": "Harness",
                    "convo_id": session_id,
                    "title": current_title,
                    "model": model_name,
                    "uncached_in": uncached_in,
                    "cached_in": cached_in,
                    "total_in": total_in,
                    "cand_out": output_tokens,
                    "thinking": thinking,
                    "text_out": text_out,
                    "total": total_step,
                    "cost_usd": cost_usd,
                }
                records.append(rec)

                cs = convo_stats[session_id]
                cs["calls"] += 1
                cs["uncached_in"] += uncached_in
                cs["cached_in"] += cached_in
                cs["total_in"] += total_in
                cs["cand_out"] += output_tokens
                cs["thinking"] += thinking
                cs["text_out"] += text_out
                cs["model"] = model_name
                cs["title"] = current_title
                cs["client"] = "DeepSeek"
                cs["app"] = "Harness"
                cs["cost_usd"] += cost_usd

        except Exception:
            pass

    # 备选回退方案：若未能通过 session.v4.jsonl.zstd 解析出数据，读取 session_projcache
    if not records and proj_totals:
        for sid, pmeta in proj_totals.items():
            if sid in scanned_session_ids and records:
                continue
            cat = pmeta.get("createdAt")
            if not cat: continue
            ts = cat / 1000.0
            if ts < start_ts or ts > end_ts: continue

            tu = pmeta.get("tokenUsage", {})
            uncached_in = tu.get("uncachedInputTokens", 0)
            cached_in = tu.get("cacheReadTokens", 0)
            cache_write = tu.get("cacheWriteTokens", 0)
            total_in = uncached_in + cached_in + cache_write
            output_tokens = tu.get("outputTokens", 0)
            total_step = total_in + output_tokens

            if total_step == 0: continue

            cost_usd = calc_cost(uncached_in, cached_in, output_tokens, pmeta.get("model", "deepseek-chat"))
            dt_obj = datetime.datetime.fromtimestamp(ts)
            rec = {
                "ts": ts,
                "dt_str": dt_obj.strftime("%Y-%m-%d %H:%M:%S"),
                "day": dt_obj.strftime("%Y-%m-%d"),
                "hour": dt_obj.strftime("%Y-%m-%d %H:00"),
                "client": "DeepSeek",
                "app": "Harness",
                "convo_id": sid,
                "title": pmeta.get("title", sid),
                "model": pmeta.get("model", "deepseek-chat"),
                "uncached_in": uncached_in,
                "cached_in": cached_in,
                "total_in": total_in,
                "cand_out": output_tokens,
                "thinking": 0,
                "text_out": output_tokens,
                "total": total_step,
                "cost_usd": cost_usd,
            }
            records.append(rec)

            cs = convo_stats[sid]
            cs["calls"] += 1
            cs["uncached_in"] += uncached_in
            cs["cached_in"] += cached_in
            cs["total_in"] += total_in
            cs["cand_out"] += output_tokens
            cs["text_out"] += output_tokens
            cs["model"] = pmeta.get("model", "deepseek-chat")
            cs["title"] = pmeta.get("title", sid)
            cs["client"] = "DeepSeek"
            cs["app"] = "Harness"
            cs["cost_usd"] += cost_usd

    return records, convo_stats

def scan_opencode(opencode_db=None, start_ts=0, end_ts=9999999999):
    if not opencode_db:
        opencode_db = os.path.expanduser(os.path.join("~", ".local", "share", "opencode", "opencode.db"))
    if not os.path.isfile(opencode_db):
        return [], defaultdict(dict)

    records = []
    convo_stats = defaultdict(lambda: {
        "calls": 0, "uncached_in": 0, "cached_in": 0, "total_in": 0,
        "cand_out": 0, "thinking": 0, "text_out": 0, "model": "", "title": "",
        "client": "OpenCode", "app": "OpenCode", "cost_usd": 0.0
    })

    try:
        conn = sqlite3.connect(f"file:{os.path.abspath(opencode_db)}?mode=ro", uri=True)
        cursor = conn.cursor()

        session_map = {}
        for r in cursor.execute("SELECT id, title, model FROM session").fetchall():
            m_info = json.loads(r[2]) if r[2] and r[2].startswith('{') else {"id": r[2] or "unknown"}
            session_map[r[0]] = {"title": r[1] or "(无标题会话)", "model": m_info.get("id", "unknown")}

        start_ms = start_ts * 1000.0 if start_ts > 0 else 0
        end_ms = end_ts * 1000.0 if end_ts < 9999999999 else 9999999999999

        rows = cursor.execute(
            "SELECT m.id, m.session_id, m.time_created, m.data FROM message m WHERE m.time_created >= ? AND m.time_created <= ?",
            (start_ms, end_ms)
        ).fetchall()

        for r in rows:
            try:
                if not r[3]: continue
                d = json.loads(r[3])
                tok = d.get("tokens")
                if not tok: continue
                u_in = tok.get("input", 0)
                c_in = tok.get("cache", {}).get("read", 0)
                c_out = tok.get("output", 0)
                thinking = tok.get("reasoning", 0)
                if (u_in + c_in + c_out) == 0: continue

                ts = r[2] / 1000.0
                dt = datetime.datetime.fromtimestamp(ts)
                s_info = session_map.get(r[1], {"title": "(未知会话)", "model": "unknown"})
                m_name = s_info["model"]
                cost_usd = calc_cost(u_in, c_in, c_out, m_name)

                rec = {
                    "ts": ts,
                    "dt_str": dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "day": dt.strftime("%Y-%m-%d"),
                    "hour": dt.strftime("%Y-%m-%d %H:00"),
                    "client": "OpenCode",
                    "app": "OpenCode",
                    "convo_id": r[1],
                    "title": s_info["title"],
                    "model": m_name,
                    "uncached_in": u_in,
                    "cached_in": c_in,
                    "total_in": u_in + c_in,
                    "cand_out": c_out,
                    "thinking": thinking,
                    "text_out": c_out,
                    "total": u_in + c_in + c_out,
                    "cost_usd": cost_usd
                }
                records.append(rec)

                cs = convo_stats[r[1]]
                cs["calls"] += 1
                cs["uncached_in"] += u_in
                cs["cached_in"] += c_in
                cs["total_in"] += (u_in + c_in)
                cs["cand_out"] += c_out
                cs["thinking"] += thinking
                cs["text_out"] += c_out
                cs["client"] = "OpenCode"
                cs["app"] = "OpenCode"
                cs["model"] = m_name
                cs["title"] = s_info["title"]
                cs["cost_usd"] += cost_usd
            except Exception:
                pass
        conn.close()
    except Exception:
        pass

    return records, convo_stats

def aggregate_data(records, convo_stats, default_client=""):
    tot_calls = len(records)
    tot_uncached_in = sum(r["uncached_in"] for r in records)
    tot_cached_in = sum(r["cached_in"] for r in records)
    tot_in = tot_uncached_in + tot_cached_in
    tot_out = sum(r["cand_out"] for r in records)
    tot_thinking = sum(r["thinking"] for r in records)
    tot_text_out = sum(r["text_out"] for r in records)
    tot_tokens = tot_in + tot_out
    tot_cost_usd = sum(r.get("cost_usd", 0.0) for r in records)
    tot_cost_cny = round(tot_cost_usd * USD_TO_CNY, 4)
    cache_ratio = round(tot_cached_in / tot_in * 100, 2) if tot_in > 0 else 0.0

    by_day = defaultdict(lambda: {"calls": 0, "total": 0, "in": 0, "cached": 0, "uncached": 0, "out": 0, "thinking": 0, "cost_usd": 0.0, "cost_cny": 0.0})
    by_hour = defaultdict(lambda: {"calls": 0, "total": 0, "in": 0, "cached": 0, "uncached": 0, "out": 0, "thinking": 0, "cost_usd": 0.0, "cost_cny": 0.0})
    for r in records:
        c_usd = r.get("cost_usd", 0.0)
        c_cny = c_usd * USD_TO_CNY

        d = r["day"]
        by_day[d]["calls"] += 1
        by_day[d]["total"] += r["total"]
        by_day[d]["in"] += r["total_in"]
        by_day[d]["cached"] += r["cached_in"]
        by_day[d]["uncached"] += r["uncached_in"]
        by_day[d]["out"] += r["cand_out"]
        by_day[d]["thinking"] += r["thinking"]
        by_day[d]["cost_usd"] += c_usd
        by_day[d]["cost_cny"] += c_cny

        h = r["hour"]
        by_hour[h]["calls"] += 1
        by_hour[h]["total"] += r["total"]
        by_hour[h]["in"] += r["total_in"]
        by_hour[h]["cached"] += r["cached_in"]
        by_hour[h]["uncached"] += r["uncached_in"]
        by_hour[h]["out"] += r["cand_out"]
        by_hour[h]["thinking"] += r["thinking"]
        by_hour[h]["cost_usd"] += c_usd
        by_hour[h]["cost_cny"] += c_cny

    for d in by_day:
        by_day[d]["cost_usd"] = round(by_day[d]["cost_usd"], 4)
        by_day[d]["cost_cny"] = round(by_day[d]["cost_cny"], 4)
    for h in by_hour:
        by_hour[h]["cost_usd"] = round(by_hour[h]["cost_usd"], 4)
        by_hour[h]["cost_cny"] = round(by_hour[h]["cost_cny"], 4)

    by_model = defaultdict(lambda: {
        "calls": 0, "total": 0, "in": 0, "cached": 0, "uncached": 0, "out": 0, "thinking": 0,
        "cost_usd": 0.0, "cost_cny": 0.0, "pricing": {}
    })
    for r in records:
        m = normalize_model_name(r["model"])
        r["model"] = m
        c_usd = r.get("cost_usd", 0.0)
        c_cny = c_usd * USD_TO_CNY
        by_model[m]["calls"] += 1
        by_model[m]["total"] += r["total"]
        by_model[m]["in"] += r["total_in"]
        by_model[m]["cached"] += r["cached_in"]
        by_model[m]["uncached"] += r["uncached_in"]
        by_model[m]["out"] += r["cand_out"]
        by_model[m]["thinking"] += r["thinking"]
        by_model[m]["cost_usd"] += c_usd
        by_model[m]["cost_cny"] += c_cny
        if not by_model[m]["pricing"]:
            p = get_pricing_for_model(m)
            by_model[m]["pricing"] = {
                "uncached_usd": p["uncached"],
                "cached_usd": p["cached"],
                "output_usd": p["output"],
                "uncached_cny": round(p["uncached"] * USD_TO_CNY, 3),
                "cached_cny": round(p["cached"] * USD_TO_CNY, 3),
                "output_cny": round(p["output"] * USD_TO_CNY, 3),
            }

    for m in by_model:
        by_model[m]["cost_usd"] = round(by_model[m]["cost_usd"], 4)
        by_model[m]["cost_cny"] = round(by_model[m]["cost_cny"], 4)

    top_convos = []
    for cid, s in sorted(convo_stats.items(), key=lambda x: x[1]["total_in"] + x[1]["cand_out"], reverse=True)[:10]:
        c_usd = s.get("cost_usd", 0.0)
        client = s.get("client") or default_client
        if not client:
            app_val = s.get("app", "")
            if app_val in ("Desktop", "CLI", "IDE") or "antigravity" in str(app_val).lower():
                client = "Antigravity"
            elif "codex" in str(app_val).lower():
                client = "Codex"
            elif "deepseek" in str(app_val).lower() or "dsh" in str(app_val).lower():
                client = "DeepSeek"
            else:
                client = app_val or "未知"

        item = {
            "id": cid,
            "title": s.get("title", cid),
            "model": normalize_model_name(s.get("model", "")),
            "app": s.get("app", ""),
            "client": client,
            "calls": s["calls"],
            "total_tokens": s["total_in"] + s["cand_out"],
            "cached_tokens": s["cached_in"],
            "cost_usd": round(c_usd, 4),
            "cost_cny": round(c_usd * USD_TO_CNY, 4),
        }
        top_convos.append(item)

    return {
        "summary": {
            "total_tokens": tot_tokens,
            "total_calls": tot_calls,
            "input_tokens": tot_in,
            "cached_tokens": tot_cached_in,
            "uncached_tokens": tot_uncached_in,
            "cache_ratio": cache_ratio,
            "output_tokens": tot_out,
            "thinking_tokens": tot_thinking,
            "text_tokens": tot_text_out,
            "cost_usd": round(tot_cost_usd, 4),
            "cost_cny": tot_cost_cny,
        },
        "by_day": dict(sorted(by_day.items())),
        "by_hour": dict(sorted(by_hour.items())),
        "by_model": dict(sorted(by_model.items(), key=lambda x: x[1]["total"], reverse=True)),
        "top_convos": top_convos,
    }

def get_cache_file():
    """
    获取全局缓存文件路径。
    优先使用标准的独立软件主目录 ~/.omnitoken/，并自动兼容迁移历史旧路径 (~/.gemini/antigravity)。
    """
    omni_dir = os.path.expanduser(os.path.join("~", ".omnitoken"))
    omni_cache = os.path.join(omni_dir, "token_history_cache.json")
    if os.path.isfile(omni_cache):
        return omni_cache

    # 兼容检查旧路径 (~/.gemini/antigravity/token_history_cache.json)
    legacy_cache = os.path.expanduser(os.path.join("~", ".gemini", "antigravity", "token_history_cache.json"))
    if os.path.isfile(legacy_cache):
        try:
            os.makedirs(omni_dir, exist_ok=True)
            shutil.copy2(legacy_cache, omni_cache)
            return omni_cache
        except Exception:
            return legacy_cache

    # 默认创建独立目录 ~/.omnitoken
    try:
        os.makedirs(omni_dir, exist_ok=True)
        return omni_cache
    except Exception:
        return os.path.join(os.path.expanduser("~"), "token_history_cache.json")

def load_history_cache(yesterday_str: str):
    cache_path = get_cache_file()
    if not os.path.isfile(cache_path):
        return None
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if data.get("version") == 1 and data.get("last_cached_day", "") >= yesterday_str:
                for r in data.get("agy_recs", []):
                    r["model"] = normalize_model_name(r.get("model"))
                for c in data.get("agy_convos", {}).values():
                    c["model"] = normalize_model_name(c.get("model"))
                return data
    except Exception:
        pass
    return None

def save_history_cache(cache_data):
    cache_path = get_cache_file()
    try:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        temp_path = cache_path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False)
        if os.path.exists(cache_path):
            try:
                os.remove(cache_path)
            except Exception:
                pass
        os.rename(temp_path, cache_path)
    except Exception:
        pass

def merge_convo_stats(hist_convos, today_convos):
    merged = defaultdict(lambda: {
        "calls": 0, "uncached_in": 0, "cached_in": 0, "total_in": 0,
        "cand_out": 0, "thinking": 0, "text_out": 0, "app": "", "client": "", "title": "", "model": "", "cost_usd": 0.0
    })
    for cid, s in (hist_convos or {}).items():
        m = merged[cid]
        m["calls"] += s.get("calls", 0)
        m["uncached_in"] += s.get("uncached_in", 0)
        m["cached_in"] += s.get("cached_in", 0)
        m["total_in"] += s.get("total_in", 0)
        m["cand_out"] += s.get("cand_out", 0)
        m["thinking"] += s.get("thinking", 0)
        m["text_out"] += s.get("text_out", 0)
        m["cost_usd"] += s.get("cost_usd", 0.0)
        if s.get("title"): m["title"] = s["title"]
        if s.get("model"): m["model"] = normalize_model_name(s["model"])
        if s.get("client"): m["client"] = s["client"]
        if s.get("app"): m["app"] = s["app"]

    for cid, s in (today_convos or {}).items():
        m = merged[cid]
        m["calls"] += s.get("calls", 0)
        m["uncached_in"] += s.get("uncached_in", 0)
        m["cached_in"] += s.get("cached_in", 0)
        m["total_in"] += s.get("total_in", 0)
        m["cand_out"] += s.get("cand_out", 0)
        m["thinking"] += s.get("thinking", 0)
        m["text_out"] += s.get("text_out", 0)
        m["cost_usd"] += s.get("cost_usd", 0.0)
        if s.get("title"): m["title"] = s["title"]
        if s.get("model"): m["model"] = normalize_model_name(s["model"])
        if s.get("client"): m["client"] = s["client"]
        if s.get("app"): m["app"] = s["app"]
    return merged

def get_combined_stats(gemini_dir=None, codex_dir=None, dsh_dir=None, opencode_db=None, start_dt=None, end_dt=None, granularity="auto", force_full=False, exchange_rate=None):
    if not gemini_dir:
        gemini_dir = os.path.expanduser(os.path.join("~", ".gemini"))
    if not codex_dir:
        codex_dir = os.path.expanduser(os.path.join("~", ".codex"))
    if not dsh_dir:
        dsh_dir = os.path.expanduser(os.path.join("~", ".dsh"))
    if not opencode_db:
        opencode_db = os.path.expanduser(os.path.join("~", ".local", "share", "opencode", "opencode.db"))

    rate = float(exchange_rate) if exchange_rate else USD_TO_CNY

    now = datetime.datetime.now()
    if not end_dt: end_dt = now
    if not start_dt: start_dt = now - datetime.timedelta(days=7)

    start_ts = start_dt.timestamp()
    end_ts = end_dt.timestamp()

    today_start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_ts = today_start_dt.timestamp()
    today_str = today_start_dt.strftime("%Y-%m-%d")
    yesterday_str = (today_start_dt - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    is_today_only = (start_ts >= today_start_ts - 1)

    if is_today_only:
        # 1. 纯今日请求：仅扫描今日活跃文件，瞬时响应 (< 20ms)
        agy_recs, agy_convos = scan_antigravity(gemini_dir, today_start_ts, end_ts)
        codex_recs, codex_convos, rate_limits = scan_codex(codex_dir, today_start_ts, end_ts)
        dsh_recs, dsh_convos = scan_deepseek(dsh_dir, today_start_ts, end_ts)
        opencode_recs, opencode_convos = scan_opencode(opencode_db, today_start_ts, end_ts)
    else:
        # 2. 跨天历史区间：读取历史缓存 + 扫描今日实时增量
        cached_data = None if force_full else load_history_cache(yesterday_str)

        if cached_data:
            # 命中历史有效缓存！
            hist_agy = [r for r in cached_data.get("agy_recs", []) if r["ts"] >= start_ts]
            hist_codex = [r for r in cached_data.get("codex_recs", []) if r["ts"] >= start_ts]
            hist_dsh = [r for r in cached_data.get("dsh_recs", []) if r["ts"] >= start_ts]
            hist_opencode = [r for r in cached_data.get("opencode_recs", []) if r["ts"] >= start_ts]

            # 扫描今日实时增量
            today_agy_recs, today_agy_convos = scan_antigravity(gemini_dir, today_start_ts, end_ts)
            today_codex_recs, today_codex_convos, rate_limits = scan_codex(codex_dir, today_start_ts, end_ts)
            today_dsh_recs, today_dsh_convos = scan_deepseek(dsh_dir, today_start_ts, end_ts)
            today_opencode_recs, today_opencode_convos = scan_opencode(opencode_db, today_start_ts, end_ts)

            # 内存秒级拼接
            agy_recs = hist_agy + today_agy_recs
            codex_recs = hist_codex + today_codex_recs
            dsh_recs = hist_dsh + today_dsh_recs
            opencode_recs = hist_opencode + today_opencode_recs

            valid_agy_cids = {r["convo_id"] for r in agy_recs}
            hist_agy_convos = {cid: s for cid, s in cached_data.get("agy_convos", {}).items() if cid in valid_agy_cids}
            agy_convos = merge_convo_stats(hist_agy_convos, today_agy_convos)

            valid_codex_cids = {r["convo_id"] for r in codex_recs}
            hist_codex_convos = {cid: s for cid, s in cached_data.get("codex_convos", {}).items() if cid in valid_codex_cids}
            codex_convos = merge_convo_stats(hist_codex_convos, today_codex_convos)

            valid_dsh_cids = {r["convo_id"] for r in dsh_recs}
            hist_dsh_convos = {cid: s for cid, s in cached_data.get("dsh_convos", {}).items() if cid in valid_dsh_cids}
            dsh_convos = merge_convo_stats(hist_dsh_convos, today_dsh_convos)

            valid_opencode_cids = {r["convo_id"] for r in opencode_recs}
            hist_opencode_convos = {cid: s for cid, s in cached_data.get("opencode_convos", {}).items() if cid in valid_opencode_cids}
            opencode_convos = merge_convo_stats(hist_opencode_convos, today_opencode_convos)
        else:
            # 缓存未命中或用户请求全局全量重建：全量深度遍历并持久化历史缓存
            full_start_ts = 0.0
            all_agy_recs, all_agy_convos = scan_antigravity(gemini_dir, full_start_ts, end_ts)
            all_codex_recs, all_codex_convos, rate_limits = scan_codex(codex_dir, full_start_ts, end_ts)
            all_dsh_recs, all_dsh_convos = scan_deepseek(dsh_dir, full_start_ts, end_ts)
            all_opencode_recs, all_opencode_convos = scan_opencode(opencode_db, full_start_ts, end_ts)

            # 持久化所有截止到昨天的不可变历史记录
            cache_to_save = {
                "version": 1,
                "last_cached_day": yesterday_str,
                "saved_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                "agy_recs": [r for r in all_agy_recs if r["day"] < today_str],
                "codex_recs": [r for r in all_codex_recs if r["day"] < today_str],
                "dsh_recs": [r for r in all_dsh_recs if r["day"] < today_str],
                "opencode_recs": [r for r in all_opencode_recs if r["day"] < today_str],
                "agy_convos": {cid: dict(s) for cid, s in all_agy_convos.items() if any(r["day"] < today_str for r in all_agy_recs if r["convo_id"] == cid)},
                "codex_convos": {cid: dict(s) for cid, s in all_codex_convos.items() if any(r["day"] < today_str for r in all_codex_recs if r["convo_id"] == cid)},
                "dsh_convos": {cid: dict(s) for cid, s in all_dsh_convos.items() if any(r["day"] < today_str for r in all_dsh_recs if r["convo_id"] == cid)},
                "opencode_convos": {cid: dict(s) for cid, s in all_opencode_convos.items() if any(r["day"] < today_str for r in all_opencode_recs if r["convo_id"] == cid)},
            }
            save_history_cache(cache_to_save)

            agy_recs = [r for r in all_agy_recs if r["ts"] >= start_ts]
            codex_recs = [r for r in all_codex_recs if r["ts"] >= start_ts]
            dsh_recs = [r for r in all_dsh_recs if r["ts"] >= start_ts]
            opencode_recs = [r for r in all_opencode_recs if r["ts"] >= start_ts]

            agy_convos = {cid: s for cid, s in all_agy_convos.items() if any(r["convo_id"] == cid for r in agy_recs)}
            codex_convos = {cid: s for cid, s in all_codex_convos.items() if any(r["convo_id"] == cid for r in codex_recs)}
            dsh_convos = {cid: s for cid, s in all_dsh_convos.items() if any(r["convo_id"] == cid for r in dsh_recs)}
            opencode_convos = {cid: s for cid, s in all_opencode_convos.items() if any(r["convo_id"] == cid for r in opencode_recs)}

    agy_stats = aggregate_data(agy_recs, agy_convos, default_client="Antigravity")
    codex_stats = aggregate_data(codex_recs, codex_convos, default_client="Codex")
    dsh_stats = aggregate_data(dsh_recs, dsh_convos, default_client="DeepSeek")
    opencode_stats = aggregate_data(opencode_recs, opencode_convos, default_client="OpenCode")

    comb_tot = agy_stats["summary"]["total_tokens"] + codex_stats["summary"]["total_tokens"] + dsh_stats["summary"]["total_tokens"] + opencode_stats["summary"]["total_tokens"]
    comb_calls = agy_stats["summary"]["total_calls"] + codex_stats["summary"]["total_calls"] + dsh_stats["summary"]["total_calls"] + opencode_stats["summary"]["total_calls"]
    comb_in = agy_stats["summary"]["input_tokens"] + codex_stats["summary"]["input_tokens"] + dsh_stats["summary"]["input_tokens"] + opencode_stats["summary"]["input_tokens"]
    comb_cached = agy_stats["summary"]["cached_tokens"] + codex_stats["summary"]["cached_tokens"] + dsh_stats["summary"]["cached_tokens"] + opencode_stats["summary"]["cached_tokens"]
    comb_uncached = agy_stats["summary"]["uncached_tokens"] + codex_stats["summary"]["uncached_tokens"] + dsh_stats["summary"]["uncached_tokens"] + opencode_stats["summary"]["uncached_tokens"]
    comb_out = agy_stats["summary"]["output_tokens"] + codex_stats["summary"]["output_tokens"] + dsh_stats["summary"]["output_tokens"] + opencode_stats["summary"]["output_tokens"]
    comb_thinking = agy_stats["summary"]["thinking_tokens"] + codex_stats["summary"]["thinking_tokens"] + dsh_stats["summary"]["thinking_tokens"] + opencode_stats["summary"]["thinking_tokens"]
    comb_ratio = round(comb_cached / comb_in * 100, 2) if comb_in > 0 else 0.0

    comb_cost_usd = round(agy_stats["summary"].get("cost_usd", 0.0) + codex_stats["summary"].get("cost_usd", 0.0) + dsh_stats["summary"].get("cost_usd", 0.0) + opencode_stats["summary"].get("cost_usd", 0.0), 4)
    comb_cost_cny = round(comb_cost_usd * rate, 4)

    # 1. 连续日级别时间线 (Daily Timeline)
    all_days = sorted(set(list(agy_stats["by_day"].keys()) + list(codex_stats["by_day"].keys()) + list(dsh_stats["by_day"].keys()) + list(opencode_stats["by_day"].keys())))
    combined_days = []
    for d in all_days:
        ad = agy_stats["by_day"].get(d, {"total": 0, "calls": 0, "in": 0, "cached": 0, "out": 0, "cost_usd": 0.0, "cost_cny": 0.0})
        cd = codex_stats["by_day"].get(d, {"total": 0, "calls": 0, "in": 0, "cached": 0, "out": 0, "cost_usd": 0.0, "cost_cny": 0.0})
        dd = dsh_stats["by_day"].get(d, {"total": 0, "calls": 0, "in": 0, "cached": 0, "out": 0, "cost_usd": 0.0, "cost_cny": 0.0})
        od = opencode_stats["by_day"].get(d, {"total": 0, "calls": 0, "in": 0, "cached": 0, "out": 0, "cost_usd": 0.0, "cost_cny": 0.0})
        tot_d_usd = round(ad.get("cost_usd", 0.0) + cd.get("cost_usd", 0.0) + dd.get("cost_usd", 0.0) + od.get("cost_usd", 0.0), 4)
        combined_days.append({
            "date": d,
            "label": d[5:], # MM-DD
            "total": ad["total"] + cd["total"] + dd["total"] + od["total"],
            "agy_total": ad["total"],
            "codex_total": cd["total"],
            "dsh_total": dd["total"],
            "opencode_total": od["total"],
            "agy_calls": ad["calls"],
            "codex_calls": cd["calls"],
            "dsh_calls": dd["calls"],
            "opencode_calls": od["calls"],
            "cost_usd": tot_d_usd,
            "cost_cny": round(tot_d_usd * rate, 4),
            "agy_cost_usd": ad.get("cost_usd", 0.0),
            "codex_cost_usd": cd.get("cost_usd", 0.0),
            "dsh_cost_usd": dd.get("cost_usd", 0.0),
            "opencode_cost_usd": od.get("cost_usd", 0.0),
        })

    # 2. 连续逐小时时间线 (Hourly Timeline)
    span_hours = (end_dt - start_dt).total_seconds() / 3600.0
    is_today_only_view = (start_dt.date() == end_dt.date() and span_hours <= 24.5)

    hourly_timeline = []
    cur_h = start_dt.replace(minute=0, second=0, microsecond=0)
    end_h = end_dt.replace(minute=0, second=0, microsecond=0)
    if is_today_only_view:
        end_h = start_dt.replace(hour=23, minute=0, second=0, microsecond=0)

    while cur_h <= end_h:
        k = cur_h.strftime("%Y-%m-%d %H:00")
        ah = agy_stats["by_hour"].get(k, {"total": 0, "calls": 0, "in": 0, "cached": 0, "out": 0, "cost_usd": 0.0, "cost_cny": 0.0})
        ch = codex_stats["by_hour"].get(k, {"total": 0, "calls": 0, "in": 0, "cached": 0, "out": 0, "cost_usd": 0.0, "cost_cny": 0.0})
        dh = dsh_stats["by_hour"].get(k, {"total": 0, "calls": 0, "in": 0, "cached": 0, "out": 0, "cost_usd": 0.0, "cost_cny": 0.0})
        oh = opencode_stats["by_hour"].get(k, {"total": 0, "calls": 0, "in": 0, "cached": 0, "out": 0, "cost_usd": 0.0, "cost_cny": 0.0})
        tot_h_usd = round(ah.get("cost_usd", 0.0) + ch.get("cost_usd", 0.0) + dh.get("cost_usd", 0.0) + oh.get("cost_usd", 0.0), 4)

        if is_today_only_view:
            label = cur_h.strftime("%H:00")
        else:
            label = cur_h.strftime("%m-%d %H:00")

        hourly_timeline.append({
            "timestamp": k,
            "date": cur_h.strftime("%Y-%m-%d"),
            "hour": cur_h.hour,
            "label": label,
            "total": ah["total"] + ch["total"] + dh["total"] + oh["total"],
            "agy_total": ah["total"],
            "codex_total": ch["total"],
            "dsh_total": dh["total"],
            "opencode_total": oh["total"],
            "agy_calls": ah["calls"],
            "codex_calls": ch["calls"],
            "dsh_calls": dh["calls"],
            "opencode_calls": oh["calls"],
            "cost_usd": tot_h_usd,
            "cost_cny": round(tot_h_usd * rate, 4),
            "agy_cost_usd": ah.get("cost_usd", 0.0),
            "codex_cost_usd": ch.get("cost_usd", 0.0),
            "dsh_cost_usd": dh.get("cost_usd", 0.0),
            "opencode_cost_usd": oh.get("cost_usd", 0.0),
        })
        cur_h += datetime.timedelta(hours=1)

    # 跨平台所有模型合并分布
    all_models = defaultdict(lambda: {
        "calls": 0, "total": 0, "in": 0, "cached": 0, "uncached": 0, "out": 0, "thinking": 0,
        "cost_usd": 0.0, "cost_cny": 0.0, "pricing": {}, "clients": set()
    })
    for m, v in agy_stats["by_model"].items():
        nm = normalize_model_name(m)
        all_models[nm]["calls"] += v["calls"]
        all_models[nm]["total"] += v["total"]
        all_models[nm]["in"] += v["in"]
        all_models[nm]["cached"] += v["cached"]
        all_models[nm]["uncached"] += v.get("uncached", 0)
        all_models[nm]["out"] += v["out"]
        all_models[nm]["thinking"] += v["thinking"]
        all_models[nm]["cost_usd"] += v.get("cost_usd", 0.0)
        all_models[nm]["cost_cny"] += v.get("cost_cny", 0.0)
        if not all_models[nm]["pricing"]:
            all_models[nm]["pricing"] = v.get("pricing", {}) or get_pricing_for_model(nm)
        all_models[nm]["clients"].add("Antigravity")

    for m, v in codex_stats["by_model"].items():
        nm = normalize_model_name(m)
        all_models[nm]["calls"] += v["calls"]
        all_models[nm]["total"] += v["total"]
        all_models[nm]["in"] += v["in"]
        all_models[nm]["cached"] += v["cached"]
        all_models[nm]["uncached"] += v.get("uncached", 0)
        all_models[nm]["out"] += v["out"]
        all_models[nm]["thinking"] += v["thinking"]
        all_models[nm]["cost_usd"] += v.get("cost_usd", 0.0)
        all_models[nm]["cost_cny"] += v.get("cost_cny", 0.0)
        if not all_models[nm]["pricing"]:
            all_models[nm]["pricing"] = v.get("pricing", {}) or get_pricing_for_model(nm)
        all_models[nm]["clients"].add("Codex")

    for m, v in dsh_stats["by_model"].items():
        nm = normalize_model_name(m)
        all_models[nm]["calls"] += v["calls"]
        all_models[nm]["total"] += v["total"]
        all_models[nm]["in"] += v["in"]
        all_models[nm]["cached"] += v["cached"]
        all_models[nm]["uncached"] += v.get("uncached", 0)
        all_models[nm]["out"] += v["out"]
        all_models[nm]["thinking"] += v["thinking"]
        all_models[nm]["cost_usd"] += v.get("cost_usd", 0.0)
        all_models[nm]["cost_cny"] += v.get("cost_cny", 0.0)
        if not all_models[nm]["pricing"]:
            all_models[nm]["pricing"] = v.get("pricing", {}) or get_pricing_for_model(nm)
        all_models[nm]["clients"].add("DeepSeek")

    for m, v in opencode_stats["by_model"].items():
        nm = normalize_model_name(m)
        all_models[nm]["calls"] += v["calls"]
        all_models[nm]["total"] += v["total"]
        all_models[nm]["in"] += v["in"]
        all_models[nm]["cached"] += v["cached"]
        all_models[nm]["uncached"] += v.get("uncached", 0)
        all_models[nm]["out"] += v["out"]
        all_models[nm]["thinking"] += v["thinking"]
        all_models[nm]["cost_usd"] += v.get("cost_usd", 0.0)
        all_models[nm]["cost_cny"] += v.get("cost_cny", 0.0)
        if not all_models[nm]["pricing"]:
            all_models[nm]["pricing"] = v.get("pricing", {}) or get_pricing_for_model(nm)
        all_models[nm]["clients"].add("OpenCode")

    all_models_dict = {}
    for m, d in sorted(all_models.items(), key=lambda x: x[1]["cost_usd"], reverse=True):
        all_models_dict[m] = {
            "calls": d["calls"],
            "total": d["total"],
            "in": d["in"],
            "cached": d["cached"],
            "uncached": d["uncached"],
            "out": d["out"],
            "thinking": d["thinking"],
            "cost_usd": round(d["cost_usd"], 4),
            "cost_cny": round(d["cost_usd"] * rate, 4),
            "pricing": d["pricing"],
            "client": "/".join(sorted(d["clients"]))
        }

    # 合并跨引擎所有高频活跃会话排行
    combined_top_convos = sorted(
        agy_stats.get("top_convos", []) + codex_stats.get("top_convos", []) + dsh_stats.get("top_convos", []) + opencode_stats.get("top_convos", []),
        key=lambda x: x["total_tokens"],
        reverse=True
    )[:15]

    # 自动判定粒度：7 天及以内默认使用逐小时
    if granularity == "auto":
        actual_granularity = "hourly" if span_hours <= (7 * 24 + 2) else "daily"
    else:
        actual_granularity = granularity

    active_timeline = hourly_timeline if actual_granularity == "hourly" else combined_days

    return {
        "range": {
            "start": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "end": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "granularity": actual_granularity,
        "span_hours": round(span_hours, 1),
        "combined_summary": {
            "total_tokens": comb_tot,
            "total_calls": comb_calls,
            "input_tokens": comb_in,
            "cached_tokens": comb_cached,
            "uncached_tokens": comb_uncached,
            "cache_ratio": comb_ratio,
            "output_tokens": comb_out,
            "thinking_tokens": comb_thinking,
            "cost_usd": comb_cost_usd,
            "cost_cny": comb_cost_cny,
            "exchange_rate": rate,
        },
        "antigravity": agy_stats,
        "codex": codex_stats,
        "deepseek": dsh_stats,
        "opencode": opencode_stats,
        "all_models": all_models_dict,
        "combined_top_convos": combined_top_convos,
        "rate_limits": rate_limits,
        "timeline": active_timeline,
        "daily_timeline": combined_days,
        "hourly_timeline": hourly_timeline,
    }
