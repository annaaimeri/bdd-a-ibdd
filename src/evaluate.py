#!/usr/bin/env python3
"""Ejecutar experimentos de evaluación BDD->IBDD y exportar resultados agregados."""
import argparse
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime
from statistics import mean, stdev
from typing import Any, Dict, List, Tuple

try:
    from src.main import BDDToIBDDPipeline
except ModuleNotFoundError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from src.main import BDDToIBDDPipeline


CONFIGS = {
    "EN-EN": {"dataset": "data/Dataset_test_90.json", "prompt": "docs/PROMPT_EN.md"},
    "ES-EN": {"dataset": "data/Dataset_test_90.json", "prompt": "docs/PROMPT_ES.md"},
    "EN-ES": {"dataset": "data/Dataset_ES_test_90.json", "prompt": "docs/PROMPT_EN.md"},
    "ES-ES": {"dataset": "data/Dataset_ES_test_90.json", "prompt": "docs/PROMPT_ES.md"},
}

T_CRITICAL_95 = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262,
    10: 2.228,
    11: 2.201,
    12: 2.179,
    13: 2.160,
    14: 2.145,
    15: 2.131,
    16: 2.120,
    17: 2.110,
    18: 2.101,
    19: 2.093,
    20: 2.086,
    21: 2.080,
    22: 2.074,
    23: 2.069,
    24: 2.064,
    25: 2.060,
    26: 2.056,
    27: 2.052,
    28: 2.048,
    29: 2.045,
    30: 2.042,
}


def t_critical_95(n: int) -> float:
    if n <= 1:
        return 0.0
    df = n - 1
    if df in T_CRITICAL_95:
        return T_CRITICAL_95[df]
    return 1.96


def pct(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return 100.0 * numerator / denominator


def summarize_values(values: List[float]) -> Dict[str, float]:
    n = len(values)
    if n == 0:
        return {"mean": 0.0, "std": 0.0, "ci95_half_width": 0.0}
    if n == 1:
        return {"mean": values[0], "std": 0.0, "ci95_half_width": 0.0}
    sigma = stdev(values)
    ci = t_critical_95(n) * (sigma / math.sqrt(n))
    return {"mean": mean(values), "std": sigma, "ci95_half_width": ci}


def config_stats(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    initial_svr = [pct(r["initial_passed"], r["total_cases"]) for r in runs]
    final_svr = [pct(r["final_passed"], r["total_cases"]) for r in runs]
    gain = [f - i for i, f in zip(initial_svr, final_svr)]
    recovery = []
    rounds_used = []
    total_time = []

    for r in runs:
        init_failed = r["initial_failed"]
        fixed = r["initial_failed"] - r["final_failed"]
        recovery.append(pct(fixed, init_failed) if init_failed > 0 else 100.0)
        rounds_used.append(float(len(r.get("rounds", []))))
        total_time.append(float(r.get("total_pipeline_time", 0.0)))

    return {
        "runs": len(runs),
        "total_cases": runs[0]["total_cases"] if runs else 0,
        "initial_svr": summarize_values(initial_svr),
        "final_svr": summarize_values(final_svr),
        "gain_pp": summarize_values(gain),
        "recovery_rate": summarize_values(recovery),
        "rounds_used": summarize_values(rounds_used),
        "total_time_s": summarize_values(total_time),
    }


def collect_stability(runs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not runs:
        return []
    case_ids = sorted({cid for run in runs for cid in run.get("initial_failed_case_ids", [])}
                      | {cid for run in runs for cid in run.get("final_failed_case_ids", [])})
    if not case_ids:
        return []

    valid_counts = defaultdict(int)
    total_runs = len(runs)
    for run in runs:
        failed = set(run.get("final_failed_case_ids", []))
        for cid in case_ids:
            if cid not in failed:
                valid_counts[cid] += 1

    stability = []
    for cid in case_ids:
        score = valid_counts[cid] / total_runs
        stability.append({"case_id": cid, "stability": score})
    stability.sort(key=lambda x: (x["stability"], x["case_id"]))
    return stability


def latex_summary_table(aggregated: Dict[str, Any]) -> str:
    lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Resultados agregados de validez sintactica (conjunto de prueba)}",
        r"\label{tab:eval-test-svr}",
        r"\begin{tabular}{lccc}",
        r"\hline",
        r"\textbf{Config.} & $\mathbf{SVR_{inicial}}$ & $\mathbf{SVR_{final}}$ & $\mathbf{\Delta}$ (pp) \\",
        r"\hline",
    ]
    for cfg in ["EN-EN", "ES-EN", "EN-ES", "ES-ES"]:
        if cfg not in aggregated:
            continue
        item = aggregated[cfg]
        i = item["initial_svr"]["mean"]
        f = item["final_svr"]["mean"]
        d = item["gain_pp"]["mean"]
        lines.append(f"{cfg} & {i:.2f}\\% & {f:.2f}\\% & {d:+.2f} \\\\")
    lines.extend([r"\hline", r"\end{tabular}", r"\end{table}"])
    return "\n".join(lines)


def latex_ops_table(aggregated: Dict[str, Any]) -> str:
    lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Metricas del ciclo de correccion y metricas operativas}",
        r"\label{tab:eval-test-ops}",
        r"\begin{tabular}{lccc}",
        r"\hline",
        r"\textbf{Config.} & \textbf{Recovery rate} & \textbf{Rondas usadas} & \textbf{Tiempo total (s)} \\",
        r"\hline",
    ]
    for cfg in ["EN-EN", "ES-EN", "EN-ES", "ES-ES"]:
        if cfg not in aggregated:
            continue
        item = aggregated[cfg]
        rr = item["recovery_rate"]["mean"]
        ru = item["rounds_used"]["mean"]
        tt = item["total_time_s"]["mean"]
        lines.append(f"{cfg} & {rr:.2f}\\% & {ru:.2f} & {tt:.2f} \\\\")
    lines.extend([r"\hline", r"\end{tabular}", r"\end{table}"])
    return "\n".join(lines)


def latex_run_setup(runs: int, max_rounds: int, model: str, provider: str) -> str:
    return "\n".join([
        r"\paragraph{Configuracion experimental utilizada.}",
        (
            f"Se ejecutaron $N={runs}$ repeticiones independientes por configuracion, "
            f"con \\texttt{{--max-rounds}}={max_rounds}, proveedor \\texttt{{{provider}}} "
            f"y modelo \\texttt{{{model}}}."
        ),
    ])


def write_json(path: str, payload: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def write_text(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ejecutar experimentos de evaluación y generar resumen en LaTeX."
    )
    parser.add_argument("--runs", type=int, default=1, help="Repeticiones independientes por configuración")
    parser.add_argument("--max-rounds", type=int, default=3, help="Máximo de rondas de corrección")
    parser.add_argument("--workers", type=int, default=1, help="Workers paralelos para llamadas a la API")
    parser.add_argument("--provider", default=None, help="Proveedor LLM (openai u ollama)")
    parser.add_argument("--model", default=None, help="Identificador del modelo")
    parser.add_argument("--base-url", default=None, help="URL base opcional del proveedor")
    parser.add_argument("--api-key", default=None, help="Clave API opcional")
    parser.add_argument(
        "--configs",
        nargs="+",
        default=["EN-EN", "ES-EN", "EN-ES", "ES-ES"],
        choices=list(CONFIGS.keys()),
        help="Configuraciones a ejecutar",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directorio de salida de evaluación (default: data/eval_YYYYmmdd_HHMMSS)",
    )
    parser.add_argument(
        "--latex-out",
        default="tesis/07_evaluacion/generated_results.tex",
        help="Ruta del fragmento LaTeX generado",
    )
    return parser.parse_args()


def run_experiments(args: argparse.Namespace) -> Tuple[Dict[str, List[Dict[str, Any]]], str]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir or f"data/eval_{timestamp}"
    os.makedirs(output_dir, exist_ok=True)

    all_runs: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for cfg in args.configs:
        cfg_data = CONFIGS[cfg]
        for run_idx in range(1, args.runs + 1):
            stem = f"{cfg.lower().replace('-', '_')}_run{run_idx:02d}"
            translation_output = os.path.join(output_dir, f"{stem}_output.json")
            validation_output = os.path.join(output_dir, f"{stem}_validation.json")
            explanations_output = os.path.join(output_dir, f"{stem}_explanations.json")

            print(f"\n=== Ejecutando {cfg} | corrida {run_idx}/{args.runs} ===")
            pipeline = BDDToIBDDPipeline(
                api_key=args.api_key,
                provider=args.provider,
                model=args.model,
                base_url=args.base_url,
                workers=args.workers,
            )
            metrics = pipeline.run(
                dataset_path=cfg_data["dataset"],
                prompt_path=cfg_data["prompt"],
                translation_output_path=translation_output,
                validation_output_path=validation_output,
                explanations_output_path=explanations_output,
                max_rounds=args.max_rounds,
            )
            metrics["config"] = cfg
            metrics["run_index"] = run_idx
            all_runs[cfg].append(metrics)

    return all_runs, output_dir


def main() -> None:
    args = parse_args()
    all_runs, output_dir = run_experiments(args)

    aggregated = {cfg: config_stats(runs) for cfg, runs in all_runs.items()}
    stability = {cfg: collect_stability(runs) for cfg, runs in all_runs.items()}

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "parameters": {
            "runs": args.runs,
            "max_rounds": args.max_rounds,
            "workers": args.workers,
            "provider": args.provider,
            "model": args.model,
            "configs": args.configs,
        },
        "aggregated": aggregated,
        "stability": stability,
        "runs": all_runs,
    }
    summary_json_path = os.path.join(output_dir, "evaluation_summary.json")
    write_json(summary_json_path, payload)

    provider_name = args.provider or "openai"
    model_name = args.model or "gpt-4o"
    latex_parts = [
        "% ARCHIVO AUTOGENERADO. NO EDITAR MANUALMENTE.",
        latex_run_setup(args.runs, args.max_rounds, model_name, provider_name),
        "",
        latex_summary_table(aggregated),
        "",
        latex_ops_table(aggregated),
    ]
    write_text(args.latex_out, "\n".join(latex_parts) + "\n")

    print("\nEvaluación finalizada.")
    print(f"- Directorio de salida: {output_dir}")
    print(f"- Resumen JSON: {summary_json_path}")
    print(f"- Fragmento LaTeX: {args.latex_out}")


if __name__ == "__main__":
    main()
