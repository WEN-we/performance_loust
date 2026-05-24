import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from database.db_manager import DatabaseManager


def insert_test_data() -> None:
    db = DatabaseManager()

    existing = db.get_task_count()
    if existing > 0:
        print(f"数据库已有 {existing} 个任务，跳过测试数据插入")
        return

    print("正在插入测试数据...")

    tasks_data = [
        {
            "name": "百度首页压力测试",
            "type": "HTTP",
            "method": "GET",
            "url": "https://www.baidu.com",
            "users": 50,
            "spawn_rate": 5.0,
            "run_time": "5m",
            "timeout": 30,
        },
        {
            "name": "知乎API接口测试",
            "type": "HTTPS",
            "method": "GET",
            "url": "https://www.zhihu.com/api/v3/feed/topstory/recommend",
            "users": 100,
            "spawn_rate": 10.0,
            "run_time": "10m",
            "timeout": 30,
        },
        {
            "name": "淘宝搜索接口压测",
            "type": "HTTPS",
            "method": "POST",
            "url": "https://s.taobao.com/search",
            "headers": {"Content-Type": "application/json"},
            "body": {"q": "手机", "sort": "sale-desc"},
            "body_type": "json",
            "users": 200,
            "spawn_rate": 20.0,
            "run_time": "15m",
            "timeout": 60,
        },
        {
            "name": "GitHub API稳定性测试",
            "type": "HTTPS",
            "method": "GET",
            "url": "https://api.github.com/repos/python/cpython",
            "headers": {"Accept": "application/vnd.github.v3+json"},
            "users": 30,
            "spawn_rate": 2.0,
            "run_time": "3m",
            "timeout": 30,
        },
        {
            "name": "微博热搜接口测试",
            "type": "HTTP",
            "method": "GET",
            "url": "https://weibo.com/ajax/side/hotSearch",
            "users": 80,
            "spawn_rate": 8.0,
            "run_time": "5m",
            "timeout": 30,
        },
        {
            "name": "B站视频列表接口压测",
            "type": "HTTPS",
            "method": "GET",
            "url": "https://api.bilibili.com/x/web-interface/popular",
            "users": 150,
            "spawn_rate": 15.0,
            "run_time": "1h30m",
            "timeout": 45,
        },
        {
            "name": "京东商品详情接口测试",
            "type": "HTTPS",
            "method": "POST",
            "url": "https://api.m.jd.com/client.action",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "body": {"functionId": "detail", "skuId": "100012043978"},
            "body_type": "form",
            "users": 120,
            "spawn_rate": 12.0,
            "run_time": "10m",
            "timeout": 30,
        },
        {
            "name": "网易云音乐API测试",
            "type": "HTTPS",
            "method": "GET",
            "url": "https://music.163.com/api/playlist/detail",
            "params": {"id": "3778678"},
            "users": 60,
            "spawn_rate": 6.0,
            "run_time": "5m",
            "timeout": 30,
        },
    ]

    task_ids = []
    for td in tasks_data:
        task_id = db.create_task(td)
        task_ids.append(task_id)
        print(f"  创建任务: {td['name']} (ID: {task_id})")

    now = datetime.now()

    result_configs = [
        {"status": "stopped", "hours_ago": 2, "duration": 300,
         "total_requests": 15234, "fail_count": 23,
         "avg_rt": 45.2, "max_rt": 890.5, "min_rt": 3.1, "p95_rt": 120.3},
        {"status": "stopped", "hours_ago": 5, "duration": 600,
         "total_requests": 58912, "fail_count": 156,
         "avg_rt": 78.6, "max_rt": 2340.1, "min_rt": 5.2, "p95_rt": 210.8},
        {"status": "stopped", "hours_ago": 8, "duration": 900,
         "total_requests": 125678, "fail_count": 892,
         "avg_rt": 156.3, "max_rt": 5670.2, "min_rt": 8.7, "p95_rt": 450.6},
        {"status": "stopped", "hours_ago": 12, "duration": 180,
         "total_requests": 8923, "fail_count": 12,
         "avg_rt": 32.1, "max_rt": 456.7, "min_rt": 2.8, "p95_rt": 89.4},
        {"status": "stopped", "hours_ago": 24, "duration": 300,
         "total_requests": 45672, "fail_count": 345,
         "avg_rt": 67.8, "max_rt": 1890.3, "min_rt": 4.5, "p95_rt": 178.9},
        {"status": "stopped", "hours_ago": 36, "duration": 5400,
         "total_requests": 234567, "fail_count": 1234,
         "avg_rt": 123.4, "max_rt": 3456.7, "min_rt": 6.3, "p95_rt": 345.2},
        {"status": "stopped", "hours_ago": 48, "duration": 600,
         "total_requests": 67890, "fail_count": 567,
         "avg_rt": 89.5, "max_rt": 2100.8, "min_rt": 5.1, "p95_rt": 256.7},
        {"status": "stopped", "hours_ago": 72, "duration": 300,
         "total_requests": 34521, "fail_count": 89,
         "avg_rt": 52.3, "max_rt": 1230.4, "min_rt": 3.9, "p95_rt": 145.6},
    ]

    for i, task_id in enumerate(task_ids):
        config = result_configs[i]
        start_time = now - timedelta(hours=config["hours_ago"])
        end_time = start_time + timedelta(seconds=config["duration"])
        success_count = config["total_requests"] - config["fail_count"]
        fail_rate = config["fail_count"] / max(config["total_requests"], 1)
        rps = config["total_requests"] / max(config["duration"], 1)
        tps = success_count / max(config["duration"], 1)

        stats_json = {
            "total_requests": config["total_requests"],
            "total_failures": config["fail_count"],
            "avg_response_time": config["avg_rt"],
            "max_response_time": config["max_rt"],
            "min_response_time": config["min_rt"],
            "p95_response_time": config["p95_rt"],
            "failure_rate": fail_rate,
            "rps": rps,
            "user_count": tasks_data[i]["users"],
            "elapsed_seconds": config["duration"],
            "requests_per_method": {
                tasks_data[i]["method"]: {
                    "num_requests": config["total_requests"],
                    "num_failures": config["fail_count"],
                    "avg_response_time": config["avg_rt"],
                    "p95_response_time": config["p95_rt"],
                }
            },
            "errors": [
                {
                    "method": tasks_data[i]["method"],
                    "name": tasks_data[i]["url"],
                    "error": "ConnectionTimeout",
                    "occurrences": min(config["fail_count"], 5),
                }
            ] if config["fail_count"] > 0 else [],
        }

        result_data = {
            "task_id": task_id,
            "status": config["status"],
            "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": end_time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_requests": config["total_requests"],
            "success_count": success_count,
            "fail_count": config["fail_count"],
            "avg_response_time": config["avg_rt"],
            "max_response_time": config["max_rt"],
            "min_response_time": config["min_rt"],
            "p95_response_time": config["p95_rt"],
            "qps": round(rps, 3),
            "tps": round(tps, 3),
            "rps": round(rps, 3),
            "fail_rate": round(fail_rate, 4),
            "current_users": tasks_data[i]["users"],
            "stats_json": stats_json,
        }
        result_id = db.create_task_result(result_data)
        print(f"  创建任务结果: task_id={task_id}, result_id={result_id}")

        result_summary = (
            f"总请求: {config['total_requests']}, "
            f"成功: {success_count}, "
            f"失败: {config['fail_count']}, "
            f"失败率: {fail_rate:.2%}, "
            f"平均响应时间: {config['avg_rt']:.2f}ms, "
            f"耗时: {config['duration']}秒"
        )

        history_data = {
            "task_id": task_id,
            "task_name": tasks_data[i]["name"],
            "execute_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "duration": float(config["duration"]),
            "result_summary": result_summary,
            "stats_json": stats_json,
            "report_path": "",
        }
        history_id = db.create_history(history_data)
        print(f"  创建历史记录: task_id={task_id}, history_id={history_id}")

    extra_history_count = 4
    for j in range(extra_history_count):
        idx = j % len(task_ids)
        task_id = task_ids[idx]
        task = db.get_task(task_id)
        hours_ago = 96 + j * 48
        duration = random.randint(120, 900)
        total_requests = random.randint(5000, 200000)
        fail_count = random.randint(0, int(total_requests * 0.05))
        success_count = total_requests - fail_count
        fail_rate = fail_count / max(total_requests, 1)
        avg_rt = round(random.uniform(20, 200), 2)
        max_rt = round(avg_rt * random.uniform(5, 30), 2)
        min_rt = round(random.uniform(1, 10), 2)
        p95_rt = round(avg_rt * random.uniform(1.5, 4), 2)
        rps = total_requests / max(duration, 1)
        tps = success_count / max(duration, 1)

        start_time = now - timedelta(hours=hours_ago)
        end_time = start_time + timedelta(seconds=duration)

        stats_json = {
            "total_requests": total_requests,
            "total_failures": fail_count,
            "avg_response_time": avg_rt,
            "max_response_time": max_rt,
            "min_response_time": min_rt,
            "p95_response_time": p95_rt,
            "failure_rate": fail_rate,
            "rps": rps,
            "user_count": task.get("users", 10) if task else 10,
            "elapsed_seconds": duration,
        }

        result_data = {
            "task_id": task_id,
            "status": "stopped",
            "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": end_time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_requests": total_requests,
            "success_count": success_count,
            "fail_count": fail_count,
            "avg_response_time": avg_rt,
            "max_response_time": max_rt,
            "min_response_time": min_rt,
            "p95_response_time": p95_rt,
            "qps": round(rps, 3),
            "tps": round(tps, 3),
            "rps": round(rps, 3),
            "fail_rate": round(fail_rate, 4),
            "current_users": task.get("users", 10) if task else 10,
            "stats_json": stats_json,
        }
        db.create_task_result(result_data)

        result_summary = (
            f"总请求: {total_requests}, "
            f"成功: {success_count}, "
            f"失败: {fail_count}, "
            f"失败率: {fail_rate:.2%}, "
            f"平均响应时间: {avg_rt:.2f}ms, "
            f"耗时: {duration}秒"
        )

        history_data = {
            "task_id": task_id,
            "task_name": task.get("name", "") if task else "",
            "execute_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "duration": float(duration),
            "result_summary": result_summary,
            "stats_json": stats_json,
            "report_path": "",
        }
        db.create_history(history_data)
        print(f"  创建额外历史记录: task_id={task_id}")

    print(f"测试数据插入完成！共创建 {len(task_ids)} 个任务，{len(task_ids) + extra_history_count} 条历史记录")


if __name__ == "__main__":
    insert_test_data()
