import redis
import json
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import re
import os

# Connect to Redis
r = redis.Redis(host='localhost', port=6379, db=0)

# Fetch all keys
keys = r.keys('*')

records = []

for key in keys:
    raw = r.get(key)
    if not raw:
        continue

    try:
        data = json.loads(raw)

        category = data.get("category")
        filename = data.get("filename")
        content = data.get("content", {})

        # Extract timestamp
        ts_match = re.search(r"(\d{8})-(\d{6})Z", filename)
        if not ts_match:
            continue
        date_str = ts_match.group(1) + ts_match.group(2)
        start_time = datetime.strptime(date_str, "%Y%m%d%H%M%S")

        # Extract tool
        parts = filename.split("_")
        tool = parts[1] if len(parts) > 2 else "unknown"

        if category == "throughput":
            intervals = content.get("intervals", [])
            if not intervals and "summary" in content:
                summary = content["summary"].get("summary") or content["summary"]
                t_offset = summary.get("start", 0)
                throughput = summary.get("throughput-bits")
                if throughput is not None:
                    timestamp = start_time + timedelta(seconds=t_offset)
                    records.append({
                        "tool": tool,
                        "category": category,
                        "timestamp": timestamp,
                        "value": throughput / 1e6,
                        "unit": "Mbps"
                    })
            else:
                for interval in intervals:
                    t_offset = interval["summary"]["start"]
                    throughput = interval["summary"].get("throughput-bits")
                    if throughput is None:
                        continue
                    timestamp = start_time + timedelta(seconds=t_offset)
                    records.append({
                        "tool": tool,
                        "category": category,
                        "timestamp": timestamp,
                        "value": throughput / 1e6,
                        "unit": "Mbps"
                    })

        elif category == "latency":
            hist = content.get("histogram-latency", {})
            if hist:
                total_count = sum(hist.values())
                avg_latency = sum(float(k) * v for k, v in hist.items()) / total_count
                records.append({
                    "tool": tool,
                    "category": category,
                    "timestamp": start_time,
                    "value": avg_latency,
                    "unit": "ms"
                })

        elif category == "rtt":
            mean_rtt = content.get("mean")
            if mean_rtt:
                rtt_val = float(re.sub(r"[^\d.]", "", mean_rtt))
                records.append({
                    "tool": tool,
                    "category": category,
                    "timestamp": start_time,
                    "value": rtt_val * 1000,  # seconds to ms
                    "unit": "ms"
                })

        elif category == "trace":
            paths = content.get("paths", [])
            if paths and content.get("succeeded", False):
                hop_count = len([hop for hop in paths[0] if hop])  # filter empty dicts
                records.append({
                    "tool": tool,
                    "category": category,
                    "timestamp": start_time,
                    "value": hop_count,
                    "unit": "hops"
                })

        elif category == "mtu":
            mtu = content.get("mtu")
            if mtu is not None:
                records.append({
                    "tool": tool,
                    "category": category,
                    "timestamp": start_time,
                    "value": mtu,
                    "unit": "bytes"
                })

    except Exception as e:
        print(f"Error processing {key}: {e}")

# Create output directory
output_dir = "plots"
os.makedirs(output_dir, exist_ok=True)

# Convert to DataFrame
df = pd.DataFrame(records)
df = df.sort_values(by="timestamp")

# Plot per category/tool
for category in df['category'].unique():
    df_cat = df[df['category'] == category]
    units = df_cat['unit'].unique()
    unit = units[0] if len(units) == 1 else ""

    plt.figure(figsize=(12, 6))
    for tool in df_cat['tool'].unique():
        subset = df_cat[df_cat['tool'] == tool]
        if not subset.empty:
            plt.plot(subset['timestamp'], subset['value'], label=tool, marker='o')

    plt.title(f"{category.capitalize()} Over Time by Tool")
    plt.xlabel("Time")
    ylabel = f"{category.upper()} ({unit})" if unit else category.upper()
    plt.ylabel(ylabel)
    plt.grid(True)
    plt.legend()
    plt.tight_layout()

    timestamp_str = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"{category}_by_tool_{timestamp_str}.png"
    filepath = os.path.join(output_dir, filename)
    plt.savefig(filepath)
    plt.close()

    print(f"Saved plot to: {filepath}")
