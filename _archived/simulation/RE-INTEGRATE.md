# Simulation Module — Re-integration Guide

This directory contains the multi-agent evacuation simulation system, archived for future re-integration.

## Files

| Archived path | Original path |
|---|---|
| `services/simulation_orchestrator.py` | `backend/app/services/simulation_orchestrator.py` |
| `services/simulation_clock.py` | `backend/app/services/simulation_clock.py` |
| `services/evacuee_agent.py` | `backend/app/services/evacuee_agent.py` |
| `services/metrics_collector.py` | `backend/app/services/metrics_collector.py` |
| `endpoints/simulation.py` | `backend/app/api/v1/endpoints/simulation.py` |
| `schemas/simulation_models.py` | `backend/app/schemas/simulation_models.py` |
| `tests/test_simulation.py` | `backend/tests/test_simulation.py` |
| `scripts/run_demo_simulation.py` | `scripts/run_demo_simulation.py` |

## Steps to re-integrate

1. Move files back to their original paths.
2. Add `simulation` to the import list in `backend/app/api/v1/api.py`.
3. Add `api_router.include_router(simulation.router)` in the same file.
4. Verify `watsonx_client.generate_decision()` still exists (used by `evacuee_agent.py`).
5. Run `pytest tests/test_simulation.py` to confirm everything works.
