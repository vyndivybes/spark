"""Independent idealized three-joint arm simulator. No device IO or OLLIE code."""
import math
from spark_productivity import WorkbenchError


def number(value, low, high):
    if type(value) not in (int, float) or not low <= value <= high or not math.isfinite(value):
        raise WorkbenchError("Simulation number is outside its finite range.")
    return float(value)


def forward(angles, links):
    yaw, shoulder, elbow = map(math.radians, angles)
    a, b = links
    radius = a*math.cos(shoulder)
    middle = [radius*math.cos(yaw), radius*math.sin(yaw), a*math.sin(shoulder)]
    radius += b*math.cos(shoulder+elbow)
    end = [radius*math.cos(yaw), radius*math.sin(yaw), middle[2]+b*math.sin(shoulder+elbow)]
    return [[0., 0., 0.], middle, end]


def solve(target, links):
    x, y, z = target
    a, b = links
    radius = math.hypot(x, y)
    cosine = (radius*radius+z*z-a*a-b*b)/(2*a*b)
    if cosine < -1-1e-10 or cosine > 1+1e-10 or radius*radius+z*z < 1e-16:
        raise WorkbenchError("Target is outside this idealized arm's reachable workspace.")
    elbow = math.acos(max(-1., min(1., cosine)))
    shoulder = math.atan2(z, radius)-math.atan2(b*math.sin(elbow), a+b*math.cos(elbow))
    return [math.degrees(math.atan2(y, x)), math.degrees(shoulder), math.degrees(elbow)]


def simulate(spec):
    if not isinstance(spec, dict) or set(spec) != {"links", "steps"}:
        raise WorkbenchError("Simulation requires links and steps.")
    links, steps = spec["links"], spec["steps"]
    if not isinstance(links, list) or len(links) != 2:
        raise WorkbenchError("Supply two link lengths in metres.")
    links = [number(v, .01, 2) for v in links]
    if not isinstance(steps, list) or not 1 <= len(steps) <= 50:
        raise WorkbenchError("Supply 1–50 simulation steps.")
    angles, gripper, elapsed = [0., 0., 0.], "open", 0.
    frames = []
    for step in steps:
        if not isinstance(step, dict): raise WorkbenchError("Invalid simulation step.")
        kind = step.get("type")
        if kind == "move" and set(step) == {"type", "target", "seconds"}:
            target = step["target"]
            if not isinstance(target, list) or len(target) != 3:
                raise WorkbenchError("Move target needs x, y and z in metres.")
            target = [number(v, -4, 4) for v in target]
            end = solve(target, links)
            duration = number(step["seconds"], .1, 10)
        elif kind == "delay" and set(step) == {"type", "seconds"}:
            end = angles[:]
            duration = number(step["seconds"], .1, 10)
        elif kind == "gripper" and set(step) == {"type", "state"} and step["state"] in ("open", "closed"):
            gripper, end, duration = step["state"], angles[:], .1
        else: raise WorkbenchError("Use move, delay or gripper simulation steps.")
        if elapsed+duration > 120:
            raise WorkbenchError("Simulation is limited to 120 seconds.")
        count = max(1, math.ceil(duration*10))
        for index in range(1, count+1):
            current = [start+(finish-start)*index/count for start, finish in zip(angles, end)]
            frames.append({"time": round(elapsed+duration*index/count, 3), "angles": current,
                           "points": forward(current, links), "gripper": gripper})
        angles, elapsed = end, elapsed+duration
    return {"mode": "simulation_only", "seconds": elapsed, "links": links, "frames": frames,
            "limitations": "Idealized 3-joint kinematics; no collision, calibration, motor or physical safety validation."}


def route(start, end):
    def point(value):
        if not isinstance(value, list) or len(value) != 2:
            raise WorkbenchError("Coordinates need latitude and longitude.")
        return [number(value[0], -90, 90), number(value[1], -180, 180)]
    start, end = point(start), point(end)
    lat1, lon1, lat2, lon2 = map(math.radians, start+end)
    hav = math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    angle = 2*math.atan2(math.sqrt(min(1, hav)), math.sqrt(max(0, 1-hav)))
    if angle > math.pi-1e-8:
        raise WorkbenchError("Antipodal points do not define a unique great-circle route.")
    def vector(lat, lon): return [math.cos(lat)*math.cos(lon), math.cos(lat)*math.sin(lon), math.sin(lat)]
    first, last = vector(lat1, lon1), vector(lat2, lon2)
    points = []
    for index in range(65):
        ratio = index/64
        if angle < 1e-10: points.append(start[:]); continue
        xyz = [(math.sin((1-ratio)*angle)*a+math.sin(ratio*angle)*b)/math.sin(angle) for a,b in zip(first,last)]
        points.append([math.degrees(math.atan2(xyz[2], math.hypot(xyz[0], xyz[1]))), math.degrees(math.atan2(xyz[1], xyz[0]))])
    return {"distance_km": round(6371.0088*angle, 3), "points": points,
            "kind": "geometric_great_circle", "live_flight_or_road_data": False}
