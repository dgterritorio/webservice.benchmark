"""Stepped load for wms.py: hold each user count for --step-time seconds, then move to the next.

    locust -f wms.py,step_shape.py --steps 25,50,100,170 --step-time 180 --user-rps 1 --headless ...

With --user-rps 1 the user count is the target requests per second. The test ends after the last
step (-u and -t are ignored while a shape is active). Use it to find the throughput where latency or
errors break down, and to watch an autoscaler react.

Automatic stop (for production targets): --stop-p95-ms N ends the test when the p95 of the last 10 s
stays above N ms for 20 s in a row; --stop-fail-pct P ends it when more than P % of the requests of
the last 30 s failed. Both are off (0) by default.
"""

import logging
from collections import deque

from locust import LoadTestShape, events


@events.init_command_line_parser.add_listener
def _step_args(parser):
    parser.add_argument("--steps", type=str, default="", help="Comma-separated user counts, one per step, e.g. 25,50,100")
    parser.add_argument("--step-time", type=int, default=180, help="Seconds per step (default 180)")
    parser.add_argument("--stop-p95-ms", type=float, default=0, help="Stop when p95 (last 10 s) stays above this for 20 s (0 = off)")
    parser.add_argument("--stop-fail-pct", type=float, default=0, help="Stop when more than this %% of the last 30 s failed (0 = off)")


class StepShape(LoadTestShape):
    window = deque(maxlen=31)  # (requests, failures), one entry per tick (Locust ticks about once a second)
    slow_ticks = 0

    def tick(self):
        opts = self.runner.environment.parsed_options
        steps = [int(s) for s in opts.steps.split(",") if s.strip()]
        step = int(self.get_run_time() // opts.step_time)
        if step >= len(steps):
            return None  # last step done: stop the test
        users = steps[step]
        if self._should_stop(opts, users):
            return None
        return users, users  # reach the step's user count within about one second

    def _should_stop(self, opts, users):
        total = self.runner.stats.total
        self.window.append((total.num_requests, total.num_failures))
        p95 = total.get_current_response_time_percentile(0.95) or 0
        self.slow_ticks = self.slow_ticks + 1 if opts.stop_p95_ms and p95 > opts.stop_p95_ms else 0
        if self.slow_ticks >= 20:
            logging.warning("AUTO-STOP at %d users: p95 %.0f ms above %.0f ms for 20 s", users, p95, opts.stop_p95_ms)
            return True
        n = self.window[-1][0] - self.window[0][0]
        f = self.window[-1][1] - self.window[0][1]
        if opts.stop_fail_pct and len(self.window) == self.window.maxlen and n and 100 * f / n > opts.stop_fail_pct:
            logging.warning("AUTO-STOP at %d users: %d of %d requests failed in 30 s", users, f, n)
            return True
        return False
