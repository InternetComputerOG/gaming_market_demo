from typing import Dict, Any
import json
from supabase import Client

from app.config import get_supabase_client
from app.db.queries import fetch_engine_state, get_current_tick
from app.utils import serialize_state, get_current_ms

def get_realtime_client() -> Client:
    """Get Supabase client for realtime operations."""
    return get_supabase_client()

def publish_event(channel: str, event_type: str, payload: Dict[str, Any]) -> None:
    """Publish an event to a Supabase Realtime channel."""
    client = get_realtime_client()
    broadcast_payload = {
        "type": "broadcast",
        "event": event_type,
        "payload": payload
    }
    try:
        client.channel(channel).send(broadcast_payload)
    except Exception as e:
        # Basic logging; demo-level
        print(f"Error publishing to {channel}: {e}")

def make_tick_payload(tick_id: int) -> Dict[str, Any]:
    """Create payload for TickEvent from current state and tick."""
    state = fetch_engine_state()
    tick_data = get_current_tick()
    
    # Serialize state summary
    state_summary = serialize_state(state)
    
    # Compute prices per binary
    prices = {}
    for binary in state['binaries']:
        outcome_i = binary['outcome_i']
        prices[outcome_i] = {
            'p_yes': binary['q_yes'] / binary['L'] if binary['L'] > 0 else 0.0,
            'p_no': binary['q_no'] / binary['L'] if binary['L'] > 0 else 0.0
        }
    
    # Placeholder for volumes, stats (fetch or compute as needed; keep simple)
    volumes = sum(binary['V'] for binary in state['binaries'])
    mm_risk = sum(binary.get('subsidy', 0.0) for binary in state['binaries'])
    mm_profit = sum(binary.get('seigniorage', 0.0) for binary in state['binaries'])
    
    # Deltas: fills, positions, top-of-book, leaderboard (placeholders; expand in UI queries)
    payload = {
        "tick_id": tick_id,
        "ts_ms": tick_data.get('ts_ms', 0),
        "prices": prices,
        "volumes": volumes,
        "mm_risk": mm_risk,
        "mm_profit": mm_profit,
        "state_summary": state_summary  # JSON-compatible dict
    }
    return payload

def publish_tick_update(tick_id: int) -> None:
    """Publish TickEvent to 'demo' channel."""
    payload = make_tick_payload(tick_id)
    publish_event("demo", "tick_update", payload)

def publish_resolution_update(is_final: bool, elim_outcomes: Any) -> None:
    """Publish resolution event to 'demo' channel."""
    payload = {
        "is_final": is_final,
        "elim_outcomes": elim_outcomes,
        "timestamp": get_current_ms()
    }
    publish_event("demo", "resolution_update", payload)

def publish_demo_status_update(status: str, message: str = None) -> None:
    """Publish demo status change event to 'demo' channel."""
    payload = {
        "status": status,
        "message": message or f"Demo status changed to {status}",
        "timestamp": get_current_ms()
    }
    publish_event("demo", "status_update", payload)