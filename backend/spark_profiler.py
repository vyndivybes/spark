"""Self-optimization profiler: measure SPARK-owned cost with before/after evidence.

§3F asks for measurement before recommendation. This module provides the
measurement half: a monotonic timing recorder, a benchmark comparison that only
recommends when a change is real, module-import-cost measurement, a
frontend-render responsiveness probe, and a resource-delta summary. It runs no
profiling daemon and never mutates state.

Design choices:

* Clock is injected (`clock=time.perf_counter`), so tests are deterministic.
* A benchmark needs an explicit tolerance floor; sub-tolerance noise is reported
  as `no_measurable_change`, never as an improvement.
* Import cost is measured in a subprocess against a throwaway `sys.path` entry so
  the measuring process is not polluted, and against the *current* Python.
* The frontend probe measures real component render latency of the shipped
  screens through one bounded Node subprocess using the repository's own dev
  dependencies; it is an offline render probe, not a browser benchmark, and it
  says so in its output.
* Recommendations are advisory strings; acting on them still flows through the
  maintenance and repository approval gates.
"""
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROBE_REPEAT_MAX = 10

FRONTEND_SECTIONS = ("SparkScreens", "IntelligenceConsole")

_FRONTEND_PROBE_SCRIPT = r"""
const path = require('path'), fs = require('fs'), os = require('os');
const {createRequire} = require('module');
const [root, section, repeatsRaw] = process.argv.slice(1);
const repeats = Number(repeatsRaw);
const req = createRequire(path.join(root, 'package.json'));
const esbuild = req('esbuild');
const React = req('react');
const {renderToStaticMarkup} = req('react-dom/server');
const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'spark-frontend-probe-'));
const target = path.join(directory, section + '.cjs');
try {
    esbuild.buildSync({
        entryPoints: [path.join(root, 'src', 'components', section + '.jsx')],
        outfile: target, bundle: true, platform: 'node', format: 'cjs',
        external: ['react'], logLevel: 'silent'});
    const Module = require('module');
    const loaded = new Module(target, module);
    loaded.filename = target;
    loaded.paths = [path.join(root, 'node_modules')];
    loaded._compile(fs.readFileSync(target, 'utf8'), target);
    const Component = loaded.exports.default;
    const props = {socket: {connected: false}, project: 'general'};
    const timings = [];
    for (let index = 0; index < repeats; index += 1) {
        const started = process.hrtime.bigint();
        const html = renderToStaticMarkup(React.createElement(Component, props));
        const milliseconds = Number(process.hrtime.bigint() - started) / 1e6;
        if (typeof html !== 'string' || html.length < 100) {
            throw new Error(section + ' rendered no markup');
        }
        timings.push(Math.round(milliseconds * 1000) / 1000);
    }
    fs.rmSync(directory, {recursive: true, force: true});
    console.log(JSON.stringify(timings));
} catch (error) {
    fs.rmSync(directory, {recursive: true, force: true});
    console.error(error.message);
    process.exit(1);
}
"""


class ProfilerError(ValueError):
    pass


def _percentile(sorted_values, fraction):
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = fraction * (len(sorted_values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


class ProfileRecorder:
    """Collect named timing samples (seconds) and summarise them.

    Every sample must be a non-negative finite number. Summaries report count,
    min, mean, p50, p95 and max so callers can reason about tail latency, not
    just the average.
    """

    def __init__(self, *, clock=time.perf_counter):
        self.clock = clock
        self._samples = {}

    def record(self, name, seconds):
        if not isinstance(name, str) or not name.strip():
            raise ProfilerError("A sample name is required.")
        if not isinstance(seconds, (int, float)) or isinstance(seconds, bool):
            raise ProfilerError("Sample duration must be a number of seconds.")
        value = float(seconds)
        if value < 0 or value != value or abs(value) == float("inf"):
            raise ProfilerError("Sample duration must be a non-negative finite number.")
        self._samples.setdefault(name, []).append(value)
        return value

    def measure(self, name):
        """Context manager that records the wall time of its block."""
        return _Measure(self, name)

    def summary(self, name):
        values = sorted(self._samples.get(name, []))
        if not values:
            return {"name": name, "count": 0, "min": None, "mean": None,
                    "p50": None, "p95": None, "max": None}
        return {
            "name": name, "count": len(values),
            "min": round(values[0], 6),
            "mean": round(sum(values) / len(values), 6),
            "p50": round(_percentile(values, 0.5), 6),
            "p95": round(_percentile(values, 0.95), 6),
            "max": round(values[-1], 6),
        }

    def names(self):
        return sorted(self._samples)

    def report(self):
        return {name: self.summary(name) for name in self.names()}


class _Measure:
    def __init__(self, recorder, name):
        self.recorder = recorder
        self.name = name

    def __enter__(self):
        self._start = self.recorder.clock()
        return self

    def __exit__(self, exc_type, exc, tb):
        elapsed = self.recorder.clock() - self._start
        self.recorder.record(self.name, elapsed)
        return False


def compare(name, before, after, *, tolerance=0.10, lower_is_better=True):
    """Compare two measurements. Recommend only when the change clears `tolerance`.

    `tolerance` is a relative fraction (0.10 = 10%). Sub-tolerance differences
    return `no_measurable_change`, so noise is never reported as an improvement.
    """
    for label, value in (("before", before), ("after", after)):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ProfilerError("Benchmark %s value must be a number." % label)
        if value < 0 or value != value or abs(value) == float("inf"):
            raise ProfilerError("Benchmark %s value must be non-negative and finite." % label)
    if not isinstance(tolerance, (int, float)) or isinstance(tolerance, bool) or not 0 <= tolerance <= 1:
        raise ProfilerError("Tolerance must be a fraction between 0 and 1.")
    if before == 0:
        relative = 0.0 if after == 0 else 1.0
    else:
        relative = (after - before) / before
    improved = relative < -tolerance if lower_is_better else relative > tolerance
    regressed = relative > tolerance if lower_is_better else relative < -tolerance
    if improved:
        verdict, recommendation = "improved", "Keep this change; the measured gain clears tolerance."
    elif regressed:
        verdict, recommendation = "regressed", "Investigate or roll back; this is a measurable regression."
    else:
        verdict, recommendation = "no_measurable_change", "Do not claim an improvement within measurement noise."
    return {
        "name": name, "before": before, "after": after,
        "delta": round(after - before, 6), "relative": round(relative, 6),
        "tolerance": tolerance, "lower_is_better": lower_is_better,
        "verdict": verdict, "recommendation": recommendation,
    }


def import_cost(module, *, timeout=60, repeats=1):
    """Measure the wall time to import `module` in a fresh subprocess.

    Runs `python -c "import <module>"` against the current interpreter, so cost
    reflects what SPARK actually pays. No third-party tooling required.
    """
    if not isinstance(module, str) or not module or not all(
            part.isidentifier() for part in module.split(".")):
        raise ProfilerError("Provide a dotted module name.")
    if not isinstance(repeats, int) or not 1 <= repeats <= 10:
        raise ProfilerError("Repeats must be between 1 and 10.")
    if not isinstance(timeout, int) or not 5 <= timeout <= 300:
        raise ProfilerError("Timeout must be 5-300 seconds.")
    timings = []
    for _ in range(repeats):
        try:
            start = time.perf_counter()
            result = subprocess.run([sys.executable, "-c", "import " + module],
                                    capture_output=True, timeout=timeout, text=True,
                                    encoding="utf-8", errors="replace")
            elapsed = time.perf_counter() - start
        except subprocess.TimeoutExpired:
            raise ProfilerError("Import of %s timed out." % module) from None
        if result.returncode:
            raise ProfilerError("Module %s is not importable in this interpreter." % module)
        timings.append(elapsed)
    best = min(timings)
    return {"module": module, "seconds": round(best, 6),
            "repeats": repeats, "all": [round(value, 6) for value in timings]}


def resource_delta(before_vitals, after_vitals):
    """Compare two host-vitals snapshots. Positive means the resource grew.

    Reports RAM available and disk free as deltas; only the keys present in both
    snapshots are compared, and nothing is asserted about external processes.
    """
    if not isinstance(before_vitals, dict) or not isinstance(after_vitals, dict):
        raise ProfilerError("Vitals must be mappings.")
    deltas = {}
    for key in ("ram_available_gb", "ram_total_gb", "disk_free_gb", "disk_total_gb"):
        before, after = before_vitals.get(key), after_vitals.get(key)
        if isinstance(before, (int, float)) and isinstance(after, (int, float)):
            deltas[key] = round(after - before, 3)
    findings = []
    ram = deltas.get("ram_available_gb")
    if ram is not None and ram < -0.25:
        findings.append({"resource": "ram", "delta_gb": ram})
    disk = deltas.get("disk_free_gb")
    if disk is not None and disk < -0.25:
        findings.append({"resource": "disk", "delta_gb": disk})
    return {"deltas": deltas, "findings": findings}


def profile_callable(func, *, recorder=None, name="call", repeats=1):
    """Run `func` `repeats` times, recording each run. Returns the recorder.

    `func` must be callable and side-effect-free is the caller's responsibility;
    this helper does not sandbox it.
    """
    if not callable(func):
        raise ProfilerError("A callable is required.")
    if not isinstance(repeats, int) or not 1 <= repeats <= 1000:
        raise ProfilerError("Repeats must be between 1 and 1000.")
    recorder = recorder or ProfileRecorder()
    for _ in range(repeats):
        with recorder.measure(name):
            func()
    return recorder


def _frontend_runner(root, section, repeats):
    node = shutil.which("node")
    if not node:
        raise ProfilerError("Node.js is unavailable, so the render probe cannot run.")
    try:
        result = subprocess.run(
            [node, "-e", _FRONTEND_PROBE_SCRIPT, root, section, str(repeats)],
            capture_output=True, timeout=180, text=True,
            encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired as error:
        raise ProfilerError("The frontend render probe timed out.") from None
    if result.returncode:
        raise ProfilerError("The render probe failed: %s"
                            % (result.stderr or "unknown error")[:200])
    return result.stdout


def frontend_probe(section, repeats, *, runner=None):
    """Measure offline render latency (milliseconds) of a shipped screen.

    One bounded Node subprocess bundles the real component with the
    repository's own dev dependencies, then renders it with
    `react-dom/server` once per repeat and reports the stochastic summary.
    This is an offline render probe — not a browser benchmark — and the
    result carries that honesty in `context`.
    """
    if section not in FRONTEND_SECTIONS:
        raise ProfilerError("Choose one shipped component: %s."
                            % ", ".join(FRONTEND_SECTIONS))
    if not isinstance(repeats, int) or not 1 <= repeats <= PROBE_REPEAT_MAX:
        raise ProfilerError("Repeats must be between 1 and %d." % PROBE_REPEAT_MAX)
    root = str(Path(__file__).resolve().parents[1])
    runner = runner or _frontend_runner
    try:
        text = runner(root, section, repeats)
    except (OSError,) as error:
        raise ProfilerError("The frontend render probe could not run.") from error
    try:
        timings = json.loads(text)
    except ValueError:
        raise ProfilerError("The render probe returned unreadable data.") from None
    if (not isinstance(timings, list) or len(timings) != repeats
            or any(not isinstance(value, (int, float)) or value < 0
                   or value > 120000 for value in timings)):
        raise ProfilerError("The render probe returned unverifiable timings.")
    ordered = sorted(round(float(value), 1) for value in timings)
    return {
        "section": section,
        "repeats": repeats,
        "timings_ms": ordered,
        "min_ms": ordered[0],
        "mean_ms": round(sum(ordered) / len(ordered), 1),
        "p95_ms": round(_percentile(ordered, 0.95), 1),
        "context": "offline react-dom/server render of the shipped components",
    }
