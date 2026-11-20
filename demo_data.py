"""Symulowane dane z cyklera (format zbliżony do eksportu EC-Lab) do demonstracji aplikacji.

Model: katoda typu PBA z dwoma plateau napięciowymi, polaryzacją rosnącą z liczbą cykli,
spadkiem pojemności Q(n) = Q0·(1 − a·n^z) oraz nieodwracalną stratą w pierwszym cyklu.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ParametryOgniwa:
    nazwa: str
    masa_mg: float
    q0_mah_g: float
    a: float
    z: float
    plateau: tuple[float, float]
    udzial_plateau: float
    polaryzacja_v: float
    wzrost_polaryzacji_v: float
    szerokosc_v: float
    ce_pierwszy: float
    ce_stabilna: float
    seed: int


OGNIWA_DEMO = [
    ParametryOgniwa("HE-PBA (Mn,Fe,Co,Ni,Cu) – synteza 25 °C", 3.2, 132.0, 0.0080, 0.62, (3.28, 3.62), 0.48,
                    0.045, 0.00040, 0.035, 0.89, 0.9978, 1),
    ParametryOgniwa("HE-PBA (Mn,Fe,Co,Ni,Cu) – synteza 60 °C", 3.5, 128.0, 0.0053, 0.60, (3.30, 3.63), 0.50,
                    0.040, 0.00025, 0.032, 0.91, 0.9988, 2),
    ParametryOgniwa("MnFe-PBA (referencja)", 3.0, 141.0, 0.0112, 0.68, (3.45, 3.62), 0.55,
                    0.055, 0.00080, 0.030, 0.86, 0.9952, 3),
]


def _q_od_v(v: np.ndarray, plateau: tuple[float, float], udzial: float, szerokosc: float) -> np.ndarray:
    """Znormalizowana pojemność (0–1) jako funkcja napięcia: dwa sigmoidalne plateau + lekkie nachylenie."""
    e1, e2 = plateau
    krok1 = 1 / (1 + np.exp(-(v - e1) / szerokosc))
    krok2 = 1 / (1 + np.exp(-(v - e2) / szerokosc))
    nachylenie = (v - v.min()) / (v.max() - v.min())
    q = 0.92 * (udzial * krok1 + (1 - udzial) * krok2) + 0.08 * nachylenie
    return (q - q.min()) / (q.max() - q.min())


def symuluj_ogniwo(p: ParametryOgniwa, liczba_cykli: int = 250, punkty: int = 70) -> pd.DataFrame:
    rng = np.random.default_rng(p.seed)
    v_siatka = np.linspace(2.0, 4.0, 600)
    prad_ma = p.q0_mah_g * p.masa_mg / 1000
    czas = 0.0
    wiersze = []

    for n in range(1, liczba_cykli + 1):
        q_dis = p.q0_mah_g * (1 - p.a * (n - 1) ** p.z) * (1 + rng.normal(0, 0.002))
        if n > 1 and rng.random() < 0.03:
            q_dis *= 1 + rng.uniform(0.003, 0.01)
        ce = p.ce_pierwszy if n == 1 else min(0.9998, p.ce_stabilna - 0.006 * np.exp(-n / 12) + rng.normal(0, 0.0003))
        q_ch = q_dis / ce

        eta = p.polaryzacja_v + p.wzrost_polaryzacji_v * n
        szer = p.szerokosc_v * (1 + 0.0015 * n)

        for etap, q_calk, przesuniecie, znak in (("charge", q_ch, +eta / 2, 1), ("discharge", q_dis, -eta / 2, -1)):
            plateau = (p.plateau[0] + przesuniecie, p.plateau[1] + przesuniecie)
            q_norm = _q_od_v(v_siatka, plateau, p.udzial_plateau, szer)
            frakcje = np.linspace(0, 1, punkty)
            napiecie = np.interp(frakcje, q_norm, v_siatka)
            if etap == "discharge":
                napiecie = napiecie[::-1]
            napiecie = napiecie + rng.normal(0, 0.0015, punkty)
            pojemnosc = frakcje * q_calk * p.masa_mg / 1000
            czasy = czas + pojemnosc / prad_ma * 3600
            czas = czasy[-1] + 60

            for t, v, q in zip(czasy, napiecie, pojemnosc):
                wiersze.append((n, t, v, znak * prad_ma,
                                q if etap == "charge" else 0.0,
                                q if etap == "discharge" else 0.0))

    return pd.DataFrame(
        wiersze,
        columns=["cycle number", "time/s", "Ecell/V", "<I>/mA", "Q charge/mA.h", "Q discharge/mA.h"],
    )


def dane_demo(liczba_cykli: int = 250) -> dict[str, tuple[pd.DataFrame, float]]:
    """Zwraca {nazwa ogniwa: (surowe dane, masa materiału aktywnego w mg)}."""
    return {p.nazwa: (symuluj_ogniwo(p, liczba_cykli), p.masa_mg) for p in OGNIWA_DEMO}
