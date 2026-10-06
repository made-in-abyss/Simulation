"""
FastAPI Server backend for the Real-Time Market Simulator Glass Terminal.
Provides REST and WebSocket APIs for 1-second ticks, live open candle updates,
event streaming, replay history, and interactive configuration.
"""

import os
import asyncio
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from simulation.engine import MarketConfig, SimulationEngine


class ConfigPayload(BaseModel):
    initial_price: float = 100.0
    tick_size: float = 0.01
    ticks_per_candle: int = 60         # Default: 60s = 1 minute candle
    tick_duration_seconds: float = 1.0
    total_ticks: int = 1200
    seed: int = 12345
    volatility_scale: float = 1.0
    momentum_scale: float = 1.0
    mean_reversion_scale: float = 1.0
    institutional_frequency: float = 1.0
    mm_activity: float = 1.0
    initial_liquidity_depth: int = 15
    initial_liquidity_size: float = 45.0
    swing_window: int = 2
    min_fvg_size: float = 0.01


app = FastAPI(title="Realistic Real-Time Market Simulator")

# Global simulation instance
current_engine: Optional[SimulationEngine] = None
current_config = MarketConfig()


def get_engine() -> SimulationEngine:
    global current_engine
    if current_engine is None:
        current_engine = SimulationEngine(current_config)
    return current_engine


@app.post("/api/init")
async def init_simulation(payload: ConfigPayload):
    global current_engine, current_config
    current_config = MarketConfig(
        initial_price=payload.initial_price,
        tick_size=payload.tick_size,
        ticks_per_candle=payload.ticks_per_candle,
        tick_duration_seconds=payload.tick_duration_seconds,
        total_ticks=payload.total_ticks,
        seed=payload.seed,
        volatility_scale=payload.volatility_scale,
        momentum_scale=payload.momentum_scale,
        mean_reversion_scale=payload.mean_reversion_scale,
        institutional_frequency=payload.institutional_frequency,
        mm_activity=payload.mm_activity,
        initial_liquidity_depth=payload.initial_liquidity_depth,
        initial_liquidity_size=payload.initial_liquidity_size,
        swing_window=payload.swing_window,
        min_fvg_size=payload.min_fvg_size,
    )
    current_engine = SimulationEngine(current_config)
    return {"status": "initialized", "config": payload.model_dump(), "state": current_engine.get_full_results()}


@app.post("/api/step")
async def step_simulation(steps: int = 1):
    engine = get_engine()
    snapshot = None
    for _ in range(max(1, steps)):
        if engine.current_tick >= engine.config.total_ticks:
            break
        snapshot = engine.step()

    return {
        "tick": engine.current_tick,
        "time_str": engine.current_time_str,
        "is_finished": engine.current_tick >= engine.config.total_ticks,
        "snapshot": snapshot.__dict__ if snapshot else None,
        "state": engine.get_full_results(),
    }


@app.post("/api/run")
async def run_simulation():
    engine = get_engine()
    results = engine.run()
    return {"status": "completed", "data": results}


@app.get("/api/state")
async def get_state():
    engine = get_engine()
    return engine.get_full_results()


@app.get("/api/replay")
async def get_replay_data():
    engine = get_engine()
    return {
        "total_ticks": engine.current_tick,
        "tick_history": engine.tick_history,
        "event_feed": [e.to_dict() for e in engine.event_feed],
        "candles": [c.to_dict() for c in engine.candle_aggregator.candles],
    }


@app.post("/api/reset")
async def reset_simulation():
    global current_engine, current_config
    current_config = MarketConfig()
    current_engine = SimulationEngine(current_config)
    return {"status": "reset", "state": current_engine.get_full_results()}


# WebSocket for high-frequency low-latency updates
@app.websocket("/ws")
async def websocket_stream(websocket: WebSocket):
    await websocket.accept()
    engine = get_engine()
    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")

            if action == "step":
                n = int(data.get("steps", 1))
                snap = None
                for _ in range(n):
                    if engine.current_tick >= engine.config.total_ticks:
                        break
                    snap = engine.step()
                await websocket.send_json({
                    "type": "tick",
                    "tick": engine.current_tick,
                    "time_str": engine.current_time_str,
                    "is_finished": engine.current_tick >= engine.config.total_ticks,
                    "snapshot": snap.__dict__ if snap else None,
                    "state": engine.get_full_results(),
                })

            elif action == "get_state":
                await websocket.send_json({
                    "type": "state",
                    "state": engine.get_full_results(),
                })

    except WebSocketDisconnect:
        pass


# Serve the UI
html_path = os.path.join(os.path.dirname(__file__), "index.html")

@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Trading Terminal UI File Not Found</h1>"
