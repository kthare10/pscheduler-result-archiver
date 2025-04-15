import redis
import json
import pandas as pd
from datetime import datetime
import re
import argparse

# Parse command-line arguments
parser = argparse.ArgumentParser(description="Dump Redis entries with full JSON, optionally filtered by category and tool")
parser.add_argument('--category', required=False, help="Category to filter (e.g., throughput, latency, rtt, mtu, trace)")
parser.add_argument('--tool', required=False, help="Tool name to filter (e.g., iperf3, ping)")
parser.add_argument('--output', default="filtered_full_entries.jsonl", help="Output filename (.jsonl or .csv)")
args = parser.parse_args()

# Connect to Redis
r = redis.Redis(host='localhost', port=6379, db=0)

# Fetch all keys
keys = r.keys('*')
records = []

for key in keys:
    raw = r.get(key)
    if not raw:
        continue

    if b"23.134.232.243" in raw:
        continue

    try:
        data = json.loads(raw)
        category = data.get("category")
        filename = data.get("filename")

        # Apply category filter if specified
        if args.category and category != args.category:
            continue

        if not filename:
            continue

        # Extract timestamp
        ts_match = re.search(r"(\d{8})-(\d{6})Z", filename)
        if not ts_match:
            continue
        date_str = ts_match.group(1) + ts_match.group(2)
        start_time = datetime.strptime(date_str, "%Y%m%d%H%M%S")

        # Extract tool name
        parts = filename.split("_")
        tool = parts[1] if len(parts) > 2 else "unknown"

        # Apply tool filter if specified
        if args.tool and tool != args.tool:
            continue

        # Save full record with metadata
        records.append({
            "redis_key": key.decode("utf-8") if isinstance(key, bytes) else key,
            "timestamp": start_time.isoformat(),
            "start_time": start_time,
            "category": category,
            "tool": tool,
            "full_json": data
        })

    except Exception as e:
        print(f"Error processing {key}: {e}")

# Sort records by timestamp
records.sort(key=lambda x: x["start_time"])

# Remove the sorting field from output
for record in records:
    record.pop("start_time", None)

# Dump output
if not records:
    print(f"No records found for the given filters.")
else:
    if args.output.endswith(".jsonl"):
        with open(args.output, "w") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")
        print(f"Saved {len(records)} entries to {args.output} (JSON Lines)")
    elif args.output.endswith(".csv"):
        df = pd.DataFrame(records)
        df.to_csv(args.output, index=False)
        print(f"Saved {len(records)} entries to {args.output} (CSV)")
    else:
        print("Please use .jsonl or .csv as the output file extension.")
