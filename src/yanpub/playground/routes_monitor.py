"""Playground 路由 — 性能监控、实时协作"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

logger = logging.getLogger("yanpub.playground")

# 静态文件目录（与 server.py 共享）
_STATIC_DIR = Path(__file__).parent / "static"


def register_monitor_routes(app: FastAPI) -> None:
    """注册性能监控路由"""
    from yanpub.core.perf.monitor import get_monitor

    @app.get("/monitor")
    async def monitor_page():
        """性能监控仪表板页面"""
        return FileResponse(_STATIC_DIR / "monitor.html")

    @app.get("/api/monitor/metrics")
    async def get_metrics(adapter_id: str | None = None):
        """获取性能指标数据"""
        monitor = get_monitor()
        return monitor.get_dashboard_data(adapter_id=adapter_id)

    @app.get("/api/monitor/trend/{adapter_id}")
    async def get_trend(adapter_id: str, metric: str = "eval_duration", points: int = 20):
        """获取趋势数据"""
        monitor = get_monitor()
        trend = monitor.get_trend(adapter_id, metric, points)
        regression = monitor.detect_regression(adapter_id, metric)
        return {
            "adapter_id": adapter_id,
            "metric": metric,
            "trend": trend,
            "regression": regression,
        }

    @app.websocket("/ws/monitor")
    async def monitor_ws(websocket: WebSocket):
        """性能监控实时推送"""
        await websocket.accept()
        monitor = get_monitor()
        monitor.subscribe(websocket)

        try:
            # 保持连接，接收客户端消息（如订阅过滤）
            while True:
                data = await websocket.receive_json()
                # 支持客户端动态切换订阅的适配器
                if "adapter_id" in data:
                    monitor.unsubscribe(websocket)
                    monitor.subscribe(websocket, adapter_id=data["adapter_id"])
        except WebSocketDisconnect:
            pass
        finally:
            monitor.unsubscribe(websocket)


def register_collab(app: FastAPI) -> None:
    """注册实时协作路由（延迟导入避免循环依赖）"""
    try:
        from yanpub.playground.collab import register_collab_routes

        register_collab_routes(app)
    except ImportError:
        logger.warning("实时协作模块不可用")
