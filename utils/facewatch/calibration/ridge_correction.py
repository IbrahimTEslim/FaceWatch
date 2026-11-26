"""
Optional per-face gaze correction (setting: gaze_ridge_correction, default off).

ptgaze's gaze ray is mapped to the screen by a 2x3 affine fitted at calibration.
What the affine can't capture (head-pose-dependent bias, per-person eye shape)
is left as a residual. This module learns that residual with ridge regression
on eyetrax-style eye features (calibration/eye_features.py):

    screen = affine(hit) + correction(features)

Safety: the correction is validated with leave-one-dot-out cross-validation
during calibration (dots grouped into at most 10 folds) — each dot is predicted
by models (affine + ridge) trained without it — and is kept only if it beats
affine-only on those held-out dots by >= 10%. Otherwise no correction is
stored and the face stays affine-only.

Plain numpy, stored as arrays (no pickle).
"""
import io
from dataclasses import dataclass, asdict
from typing import Callable

import numpy as np

ALPHAS             = (1.0, 10.0, 100.0, 1e3, 1e4, 1e5)
MIN_FRAMES_PER_DOT = 5
MAX_FRAMES_PER_DOT = 20     # frames within a dot are highly correlated; caps cost
MIN_DOTS           = 6
ACCEPT_RATIO       = 0.90   # held-out error must improve by >= 10%
MAX_FOLDS          = 10     # cross-validation folds (dots grouped beyond this)


@dataclass
class Sample:
    dot:      int
    target:   np.ndarray   # (2,) screen px
    hit:      np.ndarray   # (2,) ptgaze ray hit, cm
    features: np.ndarray   # (d,) eye_features.extract_features


@dataclass
class CorrectionReport:
    n_dots:           int
    n_frames:         int
    affine_err_px:    float | None   # leave-one-dot-out, mean of per-dot medians
    corrected_err_px: float | None
    alpha:            float | None
    accepted:         bool
    reason:           str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class RidgeCorrection:
    mean:      np.ndarray   # (d,)
    scale:     np.ndarray   # (d,)
    coef:      np.ndarray   # (d, 2)
    intercept: np.ndarray   # (2,)
    alpha:     float

    def predict(self, features: np.ndarray) -> np.ndarray:
        """(dx, dy) screen-pixel correction to add to the affine output."""
        z = (np.asarray(features, dtype=np.float64) - self.mean) / self.scale
        return z @ self.coef + self.intercept

    def to_bytes(self) -> bytes:
        buf = io.BytesIO()
        np.savez(buf, mean=self.mean, scale=self.scale, coef=self.coef,
                 intercept=self.intercept, alpha=np.array(self.alpha))
        return buf.getvalue()

    @classmethod
    def from_bytes(cls, blob: bytes) -> "RidgeCorrection":
        with np.load(io.BytesIO(blob), allow_pickle=False) as z:
            return cls(mean=z["mean"], scale=z["scale"], coef=z["coef"],
                       intercept=z["intercept"], alpha=float(z["alpha"]))


def apply_affine(M: np.ndarray, hits: np.ndarray) -> np.ndarray:
    hits = np.asarray(hits, dtype=np.float64).reshape(-1, 2)
    return hits @ M[:, :2].T + M[:, 2]


def _fit_centered(G: np.ndarray, s: np.ndarray, n: int, ZtR: np.ndarray,
                  r_sum: np.ndarray, alpha: float) -> tuple[np.ndarray, np.ndarray]:
    """
    Ridge with intercept from sufficient statistics of the training rows:
    G = ZᵀZ, s = ΣZ, ZtR = ZᵀR, r_sum = ΣR. Returns (coef (d,2), intercept (2,)).
    """
    mu   = s / n
    rbar = r_sum / n
    Gc   = G - n * np.outer(mu, mu)
    ZRc  = ZtR - n * np.outer(mu, rbar)
    coef = np.linalg.solve(Gc + alpha * np.eye(G.shape[0]), ZRc)
    return coef, rbar - mu @ coef


def _dot_folds(dots: list[int]) -> list[list[int]]:
    """Leave-one-dot-out up to MAX_FOLDS dots; beyond that, dots are spread over
    MAX_FOLDS groups (deterministic), each group held out together."""
    if len(dots) <= MAX_FOLDS:
        return [[d] for d in dots]
    order = np.random.default_rng(0).permutation(len(dots))
    return [[dots[i] for i in order[f::MAX_FOLDS]] for f in range(MAX_FOLDS)]


def train_correction(
    samples: list[Sample],
    fit_affine: Callable[[np.ndarray, np.ndarray], np.ndarray | None],
    final_affine: np.ndarray,
) -> tuple[RidgeCorrection | None, CorrectionReport]:
    """
    samples:      per-frame calibration samples (blink frames already excluded)
    fit_affine:   (median_hits, targets) -> 2x3 M — the same fit calibration uses
    final_affine: the affine actually saved for this face (fitted on all dots)
    """
    by_dot: dict[int, list[Sample]] = {}
    for s in samples:
        if s.features is not None and s.hit is not None:
            by_dot.setdefault(s.dot, []).append(s)
    dots = []
    rows: list[Sample] = []
    for dot, group in sorted(by_dot.items()):
        if len(group) < MIN_FRAMES_PER_DOT:
            continue
        if len(group) > MAX_FRAMES_PER_DOT:
            keep = np.linspace(0, len(group) - 1, MAX_FRAMES_PER_DOT).round().astype(int)
            group = [group[i] for i in keep]
        dots.append(dot)
        rows.extend(group)

    def _report(**kw) -> CorrectionReport:
        base = dict(n_dots=len(dots), n_frames=len(rows), affine_err_px=None,
                    corrected_err_px=None, alpha=None, accepted=False, reason="")
        base.update(kw)
        return CorrectionReport(**base)

    if len(dots) < MIN_DOTS:
        return None, _report(reason=f"need >= {MIN_DOTS} dots with >= {MIN_FRAMES_PER_DOT} usable frames")

    D = np.array([r.dot for r in rows])
    T = np.array([r.target for r in rows], dtype=np.float64)
    H = np.array([r.hit for r in rows], dtype=np.float64)
    F = np.array([r.features for r in rows], dtype=np.float64)

    mean  = F.mean(axis=0)
    scale = F.std(axis=0)
    scale[scale < 1e-8] = 1.0
    Z = (F - mean) / scale

    dot_target = {d: T[D == d][0] for d in dots}
    dot_hit    = {d: np.median(H[D == d], axis=0) for d in dots}
    G_tot, s_tot = Z.T @ Z, Z.sum(axis=0)
    per_dot = {d: (Z[D == d].T @ Z[D == d], Z[D == d].sum(axis=0), int((D == d).sum())) for d in dots}

    aff_errs: list[float] = []         # one per held-out dot
    cor_errs: list[np.ndarray] = []    # one (len(ALPHAS),) per held-out dot
    alphas = np.array(ALPHAS)
    for held in _dot_folds(dots):
        held_set = set(held)
        others = [d for d in dots if d not in held_set]
        M_k = fit_affine(np.array([dot_hit[d] for d in others]), np.array([dot_target[d] for d in others]))
        if M_k is None:
            continue
        tr = ~np.isin(D, held)
        R = T[tr] - apply_affine(M_k, H[tr])
        G, s, n = G_tot.copy(), s_tot.copy(), len(rows)
        for d in held:
            Gk, sk, nk = per_dot[d]
            G -= Gk; s -= sk; n -= nk
        mu, rbar = s / n, R.sum(axis=0) / n
        Gc  = G - n * np.outer(mu, mu)
        ZRc = Z[tr].T @ R - n * np.outer(mu, rbar)
        lam, V = np.linalg.eigh(Gc)            # one decomposition serves every alpha
        B = V.T @ ZRc
        for d in held:
            te = D == d
            base_te = apply_affine(M_k, H[te])
            aff_errs.append(float(np.median(np.linalg.norm(base_te - T[te], axis=1))))
            Zc_te = (Z[te] - mu) @ V           # (m, d) in eigen-basis
            errs = np.empty(len(alphas))
            for i, alpha in enumerate(alphas):
                corr = Zc_te @ (B / (lam + alpha)[:, None]) + rbar
                errs[i] = np.median(np.linalg.norm(base_te + corr - T[te], axis=1))
            cor_errs.append(errs)

    if not cor_errs:
        return None, _report(reason="affine fit failed in every fold")

    affine_err = float(np.mean(aff_errs))
    per_alpha  = np.mean(np.array(cor_errs), axis=0)
    best       = int(np.argmin(per_alpha))
    corrected  = float(per_alpha[best])
    alpha      = ALPHAS[best]
    accepted   = corrected < ACCEPT_RATIO * affine_err
    if not accepted:
        return None, _report(affine_err_px=affine_err, corrected_err_px=corrected, alpha=alpha,
                             reason="no held-out improvement over affine")

    R_all = T - apply_affine(final_affine, H)
    coef, icpt = _fit_centered(G_tot, s_tot, len(rows), Z.T @ R_all, R_all.sum(axis=0), alpha)
    model = RidgeCorrection(mean=mean, scale=scale, coef=coef, intercept=icpt, alpha=alpha)
    return model, _report(affine_err_px=affine_err, corrected_err_px=corrected, alpha=alpha,
                          accepted=True, reason="held-out error improved")
