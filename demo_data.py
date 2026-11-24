"""Generate the public synthetic scenario, with explicit stress intervals."""

import csv
import random
from pathlib import Path


def generate(path):
    rng = random.Random(304)
    spot = 2270.0
    stress = {
        "2019-06": (-148, 93, 41),
        "2020-03": (-340, -251, -306),
        "2021-10": (418, 285, 316),
        "2022-06": (-602, -712, -655),
        "2022-07": (-409, -340, -371),
        "2023-08": (-187, 128, 59),
        "2024-09": (-92, 224, 162),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(("month", "spot_myr_t", "futures_change_c1", "futures_change_c2"))
        writer.writerow(("2014-12", f"{spot:.2f}", "", ""))
        for year in range(2015, 2026):
            for month in range(1, 13):
                date = f"{year:04}-{month:02}"
                level = 2900 if year < 2020 else 4050
                sigma = 215 if 2020 <= year <= 2022 else 138
                factor = rng.gauss(0, sigma) + 0.075 * (level - spot)
                ds = factor + rng.gauss(0, 54)
                c1 = 1.12 * factor + rng.gauss(0, 111 if year >= 2023 else 79)
                c2 = 0.88 * factor + rng.gauss(0, 65)
                ds, c1, c2 = stress.get(date, (ds, c1, c2))
                spot = round(spot + ds, 2)
                writer.writerow((date, f"{spot:.2f}", f"{c1:.2f}", f"{c2:.2f}"))


if __name__ == "__main__":
    generate(Path(__file__).resolve().parent / "data" / "demo.csv")
