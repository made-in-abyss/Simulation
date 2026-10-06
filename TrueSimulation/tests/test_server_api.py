import unittest
from fastapi.testclient import TestClient
from ui.server import app

class TestServerAPIs(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_serve_ui(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("REALISTIC MARKET MICROSTRUCTURE SIMULATOR", res.text.upper())
        self.assertIn("mainCanvas", res.text)
        self.assertIn("volCanvas", res.text)
        self.assertIn("timelineScrubber", res.text)

    def test_init_and_step(self):
        init_payload = {
            "initial_price": 100.0,
            "ticks_per_candle": 60,
            "seed": 12345,
            "volatility_scale": 1.0,
            "mm_activity": 1.0,
            "institutional_frequency": 1.0,
            "total_ticks": 1200,
            "initial_liquidity_size": 45.0,
            "min_fvg_size": 0.01,
        }
        res = self.client.post("/api/init", json=init_payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "initialized")
        self.assertIn("state", data)
        self.assertIn("candles", data["state"])
        self.assertIn("order_book", data["state"])

        # Step 5 ticks
        res_step = self.client.post("/api/step?steps=5")
        self.assertEqual(res_step.status_code, 200)
        step_data = res_step.json()
        self.assertEqual(step_data["tick"], 5)
        self.assertFalse(step_data["is_finished"])

        # Get state
        res_state = self.client.get("/api/state")
        self.assertEqual(res_state.status_code, 200)
        state_data = res_state.json()
        self.assertEqual(state_data["clock"]["tick"], 5)

        # Get replay
        res_replay = self.client.get("/api/replay")
        self.assertEqual(res_replay.status_code, 200)
        replay_data = res_replay.json()
        self.assertIn("tick_history", replay_data)
        self.assertEqual(len(replay_data["tick_history"]), 5)

    def test_custom_duration_and_turbo_500x_batch(self):
        # 1. Verify UI HTML includes 500x turbo button and custom duration inputs
        res_ui = self.client.get("/")
        self.assertEqual(res_ui.status_code, 200)
        self.assertIn('data-speed="500.0"', res_ui.text)
        self.assertIn('500x ⚡', res_ui.text)
        self.assertIn('id="cfgCustomTicks"', res_ui.text)
        self.assertIn('id="cfgCustomMins"', res_ui.text)
        self.assertIn('class="dur-chip', res_ui.text)

        # 2. Test initialization with custom duration (e.g. 5000 ticks)
        custom_ticks = 5000
        init_payload = {
            "initial_price": 100.0,
            "ticks_per_candle": 60,
            "seed": 99999,
            "volatility_scale": 1.0,
            "mm_activity": 1.0,
            "institutional_frequency": 1.0,
            "total_ticks": custom_ticks,
            "initial_liquidity_size": 45.0,
            "min_fvg_size": 0.01,
        }
        res_init = self.client.post("/api/init", json=init_payload)
        self.assertEqual(res_init.status_code, 200)
        data = res_init.json()
        self.assertEqual(data["config"]["total_ticks"], custom_ticks)

        # 3. Test 500x playback batch (35 ticks per call)
        res_turbo1 = self.client.post("/api/step?steps=35")
        self.assertEqual(res_turbo1.status_code, 200)
        step_data1 = res_turbo1.json()
        self.assertEqual(step_data1["tick"], 35)
        self.assertFalse(step_data1["is_finished"])

        res_turbo2 = self.client.post("/api/step?steps=35")
        self.assertEqual(res_turbo2.status_code, 200)
        step_data2 = res_turbo2.json()
        self.assertEqual(step_data2["tick"], 70)
        self.assertFalse(step_data2["is_finished"])

if __name__ == "__main__":
    unittest.main()
