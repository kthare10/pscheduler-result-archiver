import numpy as np
import os
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter
import redis
import json
import re
from datetime import datetime, timedelta
from collections import Counter


def get_yaxis_granularity(values):
    max_val = max(values) if values else 10
    step = 0.5 if max_val < 10 else 5
    return max_val, step


def plot_time_series(df, ylabel, title, output_path, min_time, max_time):
    plt.figure(figsize=(12, 6))
    for label in df['tool'].unique():
        df_label = df[df['tool'] == label]
        plt.plot(df_label['timestamp'], df_label['value'], marker='o', linestyle='-', label=label)

    plt.xlabel("Time")
    plt.ylabel(ylabel)
    plt.title(title)
    plt.grid(True)
    plt.xlim(min_time, max_time)
    plt.gca().xaxis.set_major_formatter(DateFormatter('%Y-%m-%d'))
    plt.xticks(rotation=45)

    '''
    max_val, step = get_yaxis_granularity(df['value'].tolist())
    plt.ylim(0, max_val + step)
    plt.yticks(np.arange(0, max_val + step, step))
    '''

    plt.legend()
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()
    print(f"Saved plot: {output_path}")


def plot_upload_download_per_tool(df_throughput, min_time, max_time, output_dir):
    tools = {
        tool.replace("_upload", "").replace("_download", "")
        for tool in df_throughput['tool'].unique()
    }

    for base_tool in sorted(tools):
        df_upload = df_throughput[
            (df_throughput['tool'] == f"{base_tool}_upload") & (df_throughput['metric'] == 'throughput')
        ]
        df_download = df_throughput[
            (df_throughput['tool'] == f"{base_tool}_download") & (df_throughput['metric'] == 'throughput')
        ]

        if df_upload.empty and df_download.empty:
            continue

        all_vals = df_upload['value'].tolist() + df_download['value'].tolist()
        max_val, step = get_yaxis_granularity(all_vals)

        plt.figure(figsize=(12, 6))
        if not df_upload.empty:
            plt.plot(df_upload['timestamp'], df_upload['value'], marker='o', linestyle='-', label='Upload')
        if not df_download.empty:
            plt.plot(df_download['timestamp'], df_download['value'], marker='^', linestyle='-', label='Download')

        plt.xlabel("Time")
        plt.ylabel("Throughput (Mbps)")
        plt.title(f"Upload vs Download Throughput Over Time ({base_tool})")
        plt.grid(True)
        plt.ylim(0, max_val + step)
        plt.yticks(np.arange(0, max_val + step, step))
        plt.xlim(min_time, max_time)
        plt.gca().xaxis.set_major_formatter(DateFormatter('%Y-%m-%d'))
        plt.xticks(rotation=45)
        plt.legend()
        filepath = os.path.join(output_dir, f"{base_tool}_upload_download_timeplot.png")
        plt.tight_layout()
        plt.savefig(filepath)
        plt.close()
        print(f"Saved upload/download plot: {filepath}")


if __name__ == '__main__':
    r = redis.Redis(host='localhost', port=6379, db=0)
    keys = r.keys('*')

    records = []
    succeeded_counter = Counter()

    for key in keys:
        raw = r.get(key)
        if not raw or b"23.134.232.243" in raw:
            continue
        try:
            data = json.loads(raw)
            category = data.get("category")
            filename = data.get("filename")
            content = data.get("content", {})
            succeeded = content.get("succeeded", True)

            succeeded_counter[str(succeeded)] += 1

            if not succeeded and category != "trace":
                continue

            ts_match = re.search(r"(\d{8})-(\d{6})Z", filename)
            if not ts_match:
                continue
            date_str = ts_match.group(1) + ts_match.group(2)
            start_time = datetime.strptime(date_str, "%Y%m%d%H%M%S")

            parts = filename.split("_")
            tool = parts[1] if len(parts) > 2 else "unknown"
            tool_name = f"{tool}_upload"
            if "reverse" in filename.lower():
                tool_name = f"{tool}_download"

            if start_time.month < 4:
                continue

            if category == "throughput":
                summary = content.get("summary", {}).get("summary") or content.get("summary", {})
                diags = content.get("diags", "")

                if tool == "iperf3":
                    congestion_match = re.search(r'sender_tcp_congestion": \"(.*?)\"', diags)
                    host_cpu_match = re.search(r'host_total": ([\d.]+)', diags)
                    remote_cpu_match = re.search(r'remote_total": ([\d.]+)', diags)

                    congestion = congestion_match.group(1) if congestion_match else "unknown"
                    host_cpu = float(host_cpu_match.group(1)) if host_cpu_match else None
                    remote_cpu = float(remote_cpu_match.group(1)) if remote_cpu_match else None
                else:
                    congestion = "n/a"
                    host_cpu = None
                    remote_cpu = None

                if summary:
                    t_offset = summary.get("start", 0)
                    retransmits = summary.get("retransmits") if tool in ["iperf3", "nuttcp"] else None
                    throughput = summary.get("throughput-bits")
                    if tool == "nuttcp" and int(throughput / 1e6) > 70:
                        continue
                    timestamp = start_time + timedelta(seconds=t_offset)

                    if throughput is not None:
                        records.append({
                            "tool": tool_name,
                            "category": "throughput",
                            "timestamp": timestamp,
                            "value": throughput / 1e6,
                            "unit": "Mbps",
                            "metric": "throughput",
                            "succeeded": succeeded,
                            "congestion": congestion
                        })

                    if retransmits is not None:
                        records.append({
                            "tool": tool_name,
                            "category": "throughput",
                            "timestamp": timestamp,
                            "value": retransmits,
                            "unit": "count",
                            "metric": "retransmits",
                            "succeeded": succeeded,
                            "congestion": congestion
                        })

                    if host_cpu is not None:
                        records.append({
                            "tool": tool_name,
                            "category": "throughput",
                            "timestamp": timestamp,
                            "value": host_cpu,
                            "unit": "%",
                            "metric": "host_cpu",
                            "succeeded": succeeded,
                            "congestion": congestion
                        })

                    if remote_cpu is not None:
                        records.append({
                            "tool": tool_name,
                            "category": "throughput",
                            "timestamp": timestamp,
                            "value": remote_cpu,
                            "unit": "%",
                            "metric": "remote_cpu",
                            "succeeded": succeeded,
                            "congestion": congestion
                        })

            elif category == "latency":
                hist = content.get("histogram-latency", {})
                if hist:
                    total_count = sum(hist.values())
                    avg_latency = sum(float(k) * v for k, v in hist.items()) / total_count

                    if start_time.day <= 14 and avg_latency < 50:
                        continue

                    records.append({
                        "tool": tool,
                        "category": category,
                        "timestamp": start_time,
                        "value": avg_latency,
                        "unit": "ms",
                        "metric": "avg_latency",
                        "succeeded": succeeded
                    })

            elif category == "rtt":
                mean_rtt = content.get("mean")
                if mean_rtt:
                    match = re.match(r"PT(\d+(\.\d+)?)S", mean_rtt)
                    if match:
                        rtt_val_sec = float(match.group(1))
                        if start_time.day <= 14 and (rtt_val_sec * 1000) < 50:
                            continue
                        records.append({
                            "tool": tool,
                            "category": category,
                            "timestamp": start_time,
                            "value": rtt_val_sec * 1000,  # to ms
                            "unit": "ms",
                            "metric": "mean_rtt",
                            "succeeded": succeeded
                        })

            elif category == "trace":
                paths = content.get("paths", [])
                if paths and succeeded:
                    hop_count = len([hop for hop in paths[0] if hop])
                    records.append({
                        "tool": tool,
                        "category": category,
                        "timestamp": start_time,
                        "value": hop_count,
                        "unit": "hops",
                        "metric": "hop_count",
                        "succeeded": succeeded
                    })

            elif category == "mtu":
                mtu = content.get("mtu")
                if mtu is not None:
                    records.append({
                        "tool": tool,
                        "category": category,
                        "timestamp": start_time,
                        "value": mtu,
                        "unit": "bytes",
                        "metric": "mtu",
                        "succeeded": succeeded
                    })
            elif category == "speedtest":
                ts_str = content.get("timestamp")
                if not ts_str:
                    continue
                try:
                    start_time = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ")
                except ValueError:
                    continue

                if start_time.month == 4 and start_time.day == 14 and start_time.hour == 17:
                    continue

                download = content.get("download", {})
                upload = content.get("upload", {})
                ping = content.get("ping", {})

                if download:
                    bw_mbps = download.get("bandwidth", 0) * 8 / 1e6  # Convert bytes/sec to Mbps
                    records.append({
                        "tool": "speedtest",
                        "category": "speedtest",
                        "timestamp": start_time,
                        "value": bw_mbps,
                        "unit": "Mbps",
                        "metric": "download_bandwidth",
                        "succeeded": True
                    })

                    if "latency" in download:
                        records.append({
                            "tool": "speedtest",
                            "category": "speedtest",
                            "timestamp": start_time,
                            "value": download["latency"].get("iqm"),
                            "unit": "ms",
                            "metric": "download_latency",
                            "succeeded": True
                        })

                if upload:
                    bw_mbps = upload.get("bandwidth", 0) * 8 / 1e6  # Convert bytes/sec to Mbps
                    records.append({
                        "tool": "speedtest",
                        "category": "speedtest",
                        "timestamp": start_time,
                        "value": bw_mbps,
                        "unit": "Mbps",
                        "metric": "upload_bandwidth",
                        "succeeded": True
                    })

                    if "latency" in upload:
                        records.append({
                            "tool": "speedtest",
                            "category": "speedtest",
                            "timestamp": start_time,
                            "value": upload["latency"].get("iqm"),
                            "unit": "ms",
                            "metric": "upload_latency",
                            "succeeded": True
                        })

                if ping:
                    records.append({
                        "tool": "speedtest",
                        "category": "speedtest",
                        "timestamp": start_time,
                        "value": ping.get("latency"),
                        "unit": "ms",
                        "metric": "ping_latency",
                        "succeeded": True
                    })
                    records.append({
                        "tool": "speedtest",
                        "category": "speedtest",
                        "timestamp": start_time,
                        "value": ping.get("jitter"),
                        "unit": "ms",
                        "metric": "ping_jitter",
                        "succeeded": True
                    })
        except Exception as e:
            print(f"Error processing {key}: {e}")

    output_dir = "plots"
    os.makedirs(output_dir, exist_ok=True)

    if not records:
        print("No valid records found. Exiting.")
        exit(0)

    df = pd.DataFrame(records)
    df = df.sort_values(by="timestamp")
    df['date'] = df['timestamp'].dt.date

    min_time = df['timestamp'].min()
    max_time = df['timestamp'].max()

    df_throughput = df[(df['category'] == 'throughput') & (df['succeeded'] == True)]
    df_rtt = df[(df['category'] == 'rtt') & (df['succeeded'] == True)]
    df_latency = df[(df['category'] == 'latency') & (df['succeeded'] == True)]
    df_speed = df[(df['category'] == 'speedtest') & (df['succeeded'] == True)]

    plot_upload_download_per_tool(df_throughput, min_time, max_time, output_dir)

    if not df_rtt.empty:
        plot_time_series(
            df_rtt,
            ylabel="RTT (ms)",
            title="Round Trip Time (RTT) Over Time",
            output_path=os.path.join(output_dir, "rtt_all_tools_timeplot.png"),
            min_time=min_time,
            max_time=max_time
        )

    if not df_latency.empty:
        plot_time_series(
            df_latency,
            ylabel="Latency (ms)",
            title="Latency Over Time",
            output_path=os.path.join(output_dir, "latency_all_tools_timeplot.png"),
            min_time=min_time,
            max_time=max_time
        )
    if not df_speed.empty:
        plt.figure(figsize=(10, 5))
        for metric in ["download_bandwidth", "upload_bandwidth"]:
            df_m = df_speed[df_speed['metric'] == metric]
            if not df_m.empty:
                plt.plot(df_m['timestamp'], df_m['value'], marker='o', linestyle='-', label=metric.replace('_', ' ').title())

        plt.xlabel("Time")
        plt.ylabel("Bandwidth (Mbps)")
        plt.title("Speedtest: Bandwidth Over Time")
        plt.grid(True)
        plt.xlim(min_time, max_time)  # Uniform time range across all plots
        plt.gca().xaxis.set_major_formatter(DateFormatter('%Y-%m-%d'))  # Optional: Date formatting
        plt.xticks(rotation=45)  # Optional: Rotate date labels
        plt.legend()
        plt.tight_layout()
        filepath = os.path.join(output_dir, "speedtest_bandwidth_timeplot.png")
        plt.savefig(filepath)
        plt.close()
        print(f"Saved Speedtest bandwidth plot: {filepath}")

        plt.figure(figsize=(10, 5))
        for metric in ["ping_latency", "ping_jitter", "download_latency", "upload_latency"]:
            df_m = df_speed[df_speed['metric'] == metric]
            if not df_m.empty:
                plt.plot(df_m['timestamp'], df_m['value'], marker='s', linestyle='-', label=metric.replace('_', ' ').title())

        plt.xlabel("Time")
        plt.ylabel("Latency (ms)")
        plt.title("Speedtest: Latency and Jitter Over Time")
        plt.grid(True)
        plt.xlim(min_time, max_time)  # Uniform time range across all plots
        plt.gca().xaxis.set_major_formatter(DateFormatter('%Y-%m-%d'))  # Optional: Date formatting
        plt.xticks(rotation=45)  # Optional: Rotate date labels
        plt.legend()
        plt.tight_layout()
        filepath = os.path.join(output_dir, "speedtest_latency_timeplot.png")
        plt.savefig(filepath)
        plt.close()
        print(f"Saved Speedtest latency plot: {filepath}")
