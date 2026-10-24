"""JNS Heating Zones thermal learner v0.3.5 (staged; advisory only).

Drop-in replacement for the v0.3.4 ZoneLearner API. Persistent samples retain
their exact dataclass field schema and order. No thermostat writes live here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from math import isfinite


@dataclass
class Sample:
    at: str
    indoor: float
    outdoor: float
    duty: float
    valid: bool = True


class ZoneLearner:
    """Train on *nonoverlapping* time-weighted observation windows.

    Adjacent five-minute samples are kept in storage, but are never treated as
    independent estimates of building heat loss when an integer-degree room
    sensor cannot resolve the underlying change. A window is at least 30
    minutes, or 50 minutes if coarse room-temperature resolution is detected.
    """

    MAX_SAMPLES = 2016
    MIN_WINDOWS = 48
    MAX_SEGMENT_MINUTES = 20
    WINDOW_MAX_MINUTES = 75

    def __init__(self, samples=None):
        self.samples = [Sample(**item) for item in (samples or [])][-self.MAX_SAMPLES:]

    def add(self, at: datetime, indoor: float, outdoor: float, duty: float, valid=True):
        if not all(isfinite(x) for x in (indoor, outdoor, duty)) or not 0 <= duty <= 1:
            return
        # A clock reset or duplicate coordinator update must not corrupt
        # chronology. Retain historical samples and resume after time catches up.
        if self.samples and at.isoformat() <= self.samples[-1].at:
            return
        self.samples.append(Sample(at.isoformat(), indoor, outdoor, duty, bool(valid)))
        self.samples = self.samples[-self.MAX_SAMPLES:]

    def _windows(self):
        levels = sorted(set(s.indoor for s in self.samples if isfinite(s.indoor)))
        diffs = [b-a for a,b in zip(levels, levels[1:]) if b>a]
        resolution = min(diffs) if diffs else None
        coarse = resolution is None or resolution >= 0.5
        target_minutes = 50 if coarse else 30
        diagnostics = {
            "stored_samples": len(self.samples),
            "resolution_c": round(resolution,3) if resolution is not None else None,
            "coarse_sensor": coarse,
            "window_target_minutes": target_minutes,
            "clock_or_gap_rejections": 0,
            "invalid_or_jump_rejections": 0,
            "nonzero_delta_windows": 0,
            "heated_windows": 0,
            "unheated_windows": 0,
            "indoor_levels": len(levels),
            "short_5min_adjacent_pairs": 0,
        }
        pairs = list(zip(self.samples, self.samples[1:]))
        for a,b in pairs:
            try:
                dt=(datetime.fromisoformat(b.at)-datetime.fromisoformat(a.at)).total_seconds()/60
            except ValueError:
                continue
            if 4.5 <= dt < 5:
                diagnostics["short_5min_adjacent_pairs"] += 1

        rows = []
        i = 0
        while i < len(self.samples) - 1:
            anchor = self.samples[i]
            try:
                beginning = datetime.fromisoformat(anchor.at)
            except ValueError:
                i += 1
                diagnostics["invalid_or_jump_rejections"] += 1
                continue
            if not anchor.valid:
                i += 1
                diagnostics["invalid_or_jump_rejections"] += 1
                continue
            total = 0.0
            area_difference = 0.0
            duty_hours = 0.0
            j = i
            broken = False
            while j+1 < len(self.samples):
                a, b = self.samples[j], self.samples[j+1]
                try:
                    minutes = (datetime.fromisoformat(b.at) -
                               datetime.fromisoformat(a.at)).total_seconds()/60
                except ValueError:
                    broken = True
                    diagnostics["invalid_or_jump_rejections"] += 1
                    break
                if not 0 < minutes <= self.MAX_SEGMENT_MINUTES:
                    broken = True
                    diagnostics["clock_or_gap_rejections"] += 1
                    break
                if not (a.valid and b.valid) or any(not isfinite(v) for v in
                        (a.indoor,a.outdoor,a.duty,b.indoor,b.outdoor,b.duty)):
                    broken = True
                    diagnostics["invalid_or_jump_rejections"] += 1
                    break
                if not (0 <= a.duty <= 1 and 0 <= b.duty <= 1):
                    broken = True
                    diagnostics["invalid_or_jump_rejections"] += 1
                    break
                # Quantised readings can legitimately jump 1C at one
                # sample boundary; reject multi-degree telemetry spikes.
                if abs(b.indoor-a.indoor) > max(2.0, 3*minutes/60 + 0.5):
                    broken = True
                    diagnostics["invalid_or_jump_rejections"] += 1
                    break
                step = minutes / 60
                total += step
                area_difference += step*(
                    ((a.outdoor-a.indoor) + (b.outdoor-b.indoor))/2)
                duty_hours += step*((a.duty+b.duty)/2)
                j += 1
                elapsed = (datetime.fromisoformat(self.samples[j].at) -
                           beginning).total_seconds()/60
                if elapsed > self.WINDOW_MAX_MINUTES:
                    broken = True
                    diagnostics["clock_or_gap_rejections"] += 1
                    break
                if elapsed >= target_minutes:
                    break

            elapsed_minutes = total*60
            if not broken and elapsed_minutes >= target_minutes and total > 0:
                end = self.samples[j]
                delta = end.indoor - anchor.indoor
                # Quantisation adds up to one degree of apparent change
                # at endpoints; the bound still rejects runaway sensors.
                maximum = 3*total + (1.25 if coarse else 0.4)
                if abs(delta) <= maximum:
                    observed_duty = duty_hours / total
                    rows.append((area_difference/total,observed_duty,delta/total))
                    diagnostics["nonzero_delta_windows"] += int(abs(delta) > 0.0001)
                    diagnostics["heated_windows"] += int(observed_duty >= 0.45)
                    diagnostics["unheated_windows"] += int(observed_duty <= 0.1)
                else:
                    diagnostics["invalid_or_jump_rejections"] += 1
                i = j
            else:
                # Begin after corrupted sample/gap; otherwise no complete
                # window is available before the end of history.
                if not broken:
                    break
                i = max(i+1,j+1)
        diagnostics["valid_windows"] = len(rows)
        return rows, diagnostics

    def rows(self):
        return self._windows()[0]

    @staticmethod
    def _solve(a, y):
        n = len(y)
        m = [r[:] + [y[i]] for i,r in enumerate(a)]
        for c in range(n):
            p = max(range(c,n),key=lambda i: abs(m[i][c]))
            if abs(m[p][c]) < 1e-9:
                raise ValueError("degenerate observations")
            m[c],m[p] = m[p],m[c]
            v = m[c][c]
            m[c] = [x/v for x in m[c]]
            for r in range(n):
                if r != c:
                    v=m[r][c]
                    m[r]=[x-v*z for x,z in zip(m[r],m[c])]
        return [m[i][-1] for i in range(n)]

    def status(self):
        rows, quality = self._windows()
        n = len(rows)
        base = {"ready":False,"samples":n,**quality}
        if n < self.MIN_WINDOWS:
            return {**base,"reason":"Learning: fewer than 48 independent observation windows"}
        if quality["heated_windows"] < 10 or quality["unheated_windows"] < 10:
            return {**base,"reason":"Learning: needs heated and unheated periods"}
        if quality["nonzero_delta_windows"] < 6 or (
            quality["coarse_sensor"] and quality["indoor_levels"] < 3):
            return {**base,"reason":"Learning: insufficient temperature variation"}
        if max(u for _,u,_ in rows)-min(u for _,u,_ in rows) < 0.3:
            return {**base,"reason":"Learning: insufficient heating variation"}
        if max(x for x,_,_ in rows)-min(x for x,_,_ in rows) < 0.75:
            return {**base,"reason":"Learning: insufficient outdoor temperature variation"}
        # Retain proven v0.3.4 regression and physical bounds; learn from
        # windows instead of noisy, usually-zero five-minute differences.
        features=[(x,u,1.) for x,u,_ in rows]
        gram=[[sum(z[i]*z[j] for z in features) for j in range(3)] for i in range(3)]
        rhs=[sum(z[i]*r[2] for z,r in zip(features,rows)) for i in range(3)]
        for i,prior in enumerate((.1,.1,.01)):
            gram[i][i] += prior
        try:
            k,h,b=self._solve(gram,rhs)
        except ValueError:
            return {**base,"reason":"Learning: observations lack variation"}
        plausible = .001 <= k <= 1 and .05 <= h <= 20 and abs(b) <= 2
        return {**base,
                "ready":plausible,
                "reason":"Validated" if plausible else "Learned values outside safe bounds",
                "loss_per_hour":round(k,4),
                "heat_gain_c_per_hour":round(h,3),
                "drift_c_per_hour":round(b,3)}

    def dump(self):
        return [asdict(x) for x in self.samples]

    def project(self, now, forecast, duty, minutes=60):
        status=self.status()
        if not status["ready"] or not self.samples or not forecast:
            return None
        if not isfinite(duty) or not 0 <= duty <= 1:
            return None
        try:
            last=datetime.fromisoformat(self.samples[-1].at)
            if not 0 <= (now-last).total_seconds() <= 90*60:
                return None
            points=sorted(forecast,key=lambda x:x[0])
            if not points:
                return None
            t=self.samples[-1].indoor
            k=status["loss_per_hour"]
            h=status["heat_gain_c_per_hour"]
            b=status["drift_c_per_hour"]
            index=0
            for minute in range(0,minutes,5):
                instant=now+timedelta(minutes=minute)
                while index+1<len(points) and points[index+1][0]<=instant:
                    index+=1
                step=min(5,minutes-minute)/60
                t+=step*(k*(points[index][1]-t)+h*duty+b)
            return round(t,2) if isfinite(t) else None
        except (ValueError,TypeError,OverflowError,IndexError,KeyError):
            return None
