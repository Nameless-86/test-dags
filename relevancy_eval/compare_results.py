#!/usr/bin/env python3
import argparse
from pathlib import Path
import pandas as pd


def load_csv(path: Path) -> pd.DataFrame:
    # Lee CSVs tolerando comillas dobles anidadas
    return pd.read_csv(path)


def per_label_counts(df: pd.DataFrame) -> pd.Series:
    if "label" not in df.columns:
        raise ValueError(f"Falta columna 'label' en {df}")
    return df["label"].value_counts().sort_index()


def compare_one(
    pre_df: pd.DataFrame, post_df: pd.DataFrame, filename: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    # Totales
    totals = pd.DataFrame(
        {
            "file": [filename],
            "pre_total": [len(pre_df)],
            "post_total": [len(post_df)],
        }
    )
    totals["delta"] = totals["post_total"] - totals["pre_total"]
    totals["reduction_abs"] = totals["pre_total"] - totals["post_total"]
    totals["reduction_pct"] = (totals["reduction_abs"] / totals["pre_total"]).replace(
        [pd.NA, float("inf")], 0
    ) * 100

    # Por label
    pre_counts = per_label_counts(pre_df).rename("pre")
    post_counts = per_label_counts(post_df).rename("post")
    by_label = pd.concat([pre_counts, post_counts], axis=1).fillna(0).astype(int)
    by_label["delta"] = by_label["post"] - by_label["pre"]
    by_label["reduction_abs"] = by_label["pre"] - by_label["post"]
    by_label["reduction_pct"] = (
        by_label["reduction_abs"] / by_label["pre"].replace(0, pd.NA)
    ) * 100
    by_label = by_label.reset_index().rename(columns={"index": "label"})
    by_label.insert(0, "file", filename)
    return totals, by_label


def main():
    ap = argparse.ArgumentParser(
        description="Comparar métricas malas pre vs post remediación."
    )
    ap.add_argument(
        "--pre", required=True, help="Carpeta con CSVs PRE (e.g., reasons_results)"
    )
    ap.add_argument(
        "--post",
        required=True,
        help="Carpeta con CSVs POST (e.g., post_remediation_results)",
    )
    ap.add_argument("--out", default="out", help="Carpeta de salida (default: out)")
    args = ap.parse_args()

    pre_dir = Path(args.pre)
    post_dir = Path(args.post)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Emparejar por nombre de archivo presente en PRE y POST
    pre_files = {p.name: p for p in pre_dir.glob("*.csv")}
    post_files = {p.name: p for p in post_dir.glob("*.csv")}
    common = sorted(set(pre_files) & set(post_files))
    if not common:
        raise SystemExit(
            "No se encontraron CSVs con el mismo nombre en ambas carpetas."
        )

    totals_list = []
    labels_list = []

    for fname in common:
        pre_df = load_csv(pre_files[fname])
        post_df = load_csv(post_files[fname])
        totals, by_label = compare_one(pre_df, post_df, fname)
        totals_list.append(totals)
        labels_list.append(by_label)

    totals_all = pd.concat(totals_list, ignore_index=True)
    labels_all = pd.concat(labels_list, ignore_index=True)

    # Agregado global
    global_totals = pd.DataFrame(
        {
            "file": ["__ALL__"],
            "pre_total": [totals_all["pre_total"].sum()],
            "post_total": [totals_all["post_total"].sum()],
        }
    )
    global_totals["delta"] = global_totals["post_total"] - global_totals["pre_total"]
    global_totals["reduction_abs"] = (
        global_totals["pre_total"] - global_totals["post_total"]
    )
    global_totals["reduction_pct"] = (
        global_totals["reduction_abs"] / global_totals["pre_total"]
    ) * 100

    global_by_label = (
        labels_all.groupby("label")[["pre", "post"]]
        .sum()
        .assign(
            delta=lambda d: d["post"] - d["pre"],
            reduction_abs=lambda d: d["pre"] - d["post"],
            reduction_pct=lambda d: (d["reduction_abs"] / d["pre"].replace(0, pd.NA))
            * 100,
        )
        .reset_index()
        .sort_values("label")
    )

    # Guardar
    totals_all.to_csv(out_dir / "comparison_totals_by_file.csv", index=False)
    labels_all.to_csv(out_dir / "comparison_by_label_by_file.csv", index=False)
    global_totals.to_csv(out_dir / "comparison_totals_GLOBAL.csv", index=False)
    global_by_label.to_csv(out_dir / "comparison_by_label_GLOBAL.csv", index=False)

    # Mostrar resumen por consola
    print("\n== Resumen GLOBAL ==")
    print(global_totals.to_string(index=False))
    print("\n== Desglose GLOBAL por label ==")
    print(global_by_label.to_string(index=False))

    print(f"\nArchivos generados en: {out_dir.resolve()}")


if __name__ == "__main__":
    main()
