#!/usr/bin/env python3
"""Demo script: 5-agent LA evacuation simulation with a wildfire at tick 3.

Usage:
    python scripts/run_demo_simulation.py

Requires the backend server to be running at http://127.0.0.1:8000.
"""

import json
import time
import requests

BASE = "http://127.0.0.1:8000/api/v1/simulation"


def main() -> None:
    # 1. Create simulation
    config = {
        "num_evacuees": 5,
        "bbox_min_lat": 34.0,
        "bbox_max_lat": 34.08,
        "bbox_min_lng": -118.35,
        "bbox_max_lng": -118.20,
        "destination_lat": 34.05,
        "destination_lng": -118.10,
        "tick_interval_seconds": 2.0,
        "virtual_seconds_per_tick": 120.0,
        "max_ticks": 20,
        "hazard_schedule": [
            {
                "tick": 3,
                "hazard_type": "wildfire",
                "lat": 34.04,
                "lng": -118.28,
                "radius_meters": 2000,
                "description": "Demo wildfire near downtown LA",
            }
        ],
        "watsonx_model_id": "meta-llama/llama-3-3-70b-instruct",
    }

    print("Creating simulation...")
    resp = requests.post(f"{BASE}/create", json=config)
    resp.raise_for_status()
    create_data = resp.json()
    sim_id = create_data["sim_id"]
    print(f"  Created: {sim_id} with {create_data['num_agents']} agents")

    # 2. Start simulation
    print("Starting simulation...")
    resp = requests.post(f"{BASE}/{sim_id}/start")
    resp.raise_for_status()
    print(f"  State: {resp.json()['state']}")

    # 3. Poll status
    print("\nPolling status every 3 seconds...\n")
    for _ in range(40):
        time.sleep(3)
        resp = requests.get(f"{BASE}/{sim_id}/status")
        resp.raise_for_status()
        status = resp.json()

        tick = status["current_tick"]
        state = status["state"]
        metrics = status.get("latest_metrics") or {}

        print(f"  Tick {tick:3d} | State: {state:10s} | "
              f"idle={metrics.get('agents_idle', '?')} "
              f"evac={metrics.get('agents_evacuating', '?')} "
              f"arrived={metrics.get('agents_arrived', '?')} "
              f"shelter={metrics.get('agents_sheltering', '?')} "
              f"reroutes={metrics.get('reroutes_this_tick', '?')} "
              f"hazards={metrics.get('active_hazards', '?')}")

        if state in ("completed", "stopped"):
            break

    # 4. Wait for completion then get summary
    print("\nWaiting for simulation to complete...")
    for _ in range(30):
        time.sleep(3)
        st = requests.get(f"{BASE}/{sim_id}/status").json()["state"]
        if st in ("completed", "stopped"):
            break

    print("Fetching summary...")
    resp = requests.get(f"{BASE}/{sim_id}/summary")
    if resp.status_code == 200:
        summary = resp.json()
        print(f"\n{'='*50}")
        print(f"Simulation {summary['sim_id']} — {summary['state']}")
        print(f"  Total ticks:    {summary['total_ticks']}")
        print(f"  Total agents:   {summary['total_agents']}")
        print(f"  Arrived:        {summary['agents_arrived']}")
        print(f"  Sheltering:     {summary['agents_sheltering']}")
        print(f"  Total reroutes: {summary['total_reroutes']}")
        print(f"{'='*50}")
    else:
        print(f"  Summary not available yet: {resp.status_code}")


if __name__ == "__main__":
    main()
