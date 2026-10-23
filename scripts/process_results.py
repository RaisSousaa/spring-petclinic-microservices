#!/usr/bin/env python3
"""
Trabalho Prático 06 — Processamento e Análise dos Resultados
Lê os CSVs brutos em results/raw, descarta a janela de aquecimento (warmup),
calcula as médias entre as repetições e gera tabelas e gráficos comparativos.
"""

import os
import re
import sys
import glob
import argparse

os.environ["MPLCONFIGDIR"] = "/tmp/matplotlib_cache"
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np


def parse_args():
    parser = argparse.ArgumentParser(description="Processa métricas brutas dos experimentos de desempenho.")
    parser.add_argument("--raw-dir", default="results/raw", help="Diretório com os arquivos CSV brutos")
    parser.add_argument("--tables-dir", default="results/tables", help="Diretório de saída para tabelas")
    parser.add_argument("--plots-dir", default="results/plots", help="Diretório de saída para gráficos")
    parser.add_argument("--warmup-sec", type=int, default=None, help="Tempo de aquecimento a ser descartado em segundos (padrão: 60s ou auto)")
    return parser.parse_args()


def process_docker_stats(docker_file, start_ts, warmup_sec):
    """Calcula a média de CPU por container pós-warmup."""
    if not os.path.exists(docker_file):
        return {}

    try:
        df = pd.read_csv(docker_file)
        if df.empty or "container" not in df.columns or "cpu_perc" not in df.columns:
            return {}

        # Filtra registros pós-warmup
        post_warmup_ts = start_ts + warmup_sec
        df = df[df["timestamp"] >= post_warmup_ts]

        if df.empty:
            return {}

        # Converte percentual string (ex: '25.4%') para float
        df["cpu_num"] = df["cpu_perc"].astype(str).str.rstrip("%").astype(float)

        cpu_means = df.groupby("container")["cpu_num"].mean().to_dict()
        return cpu_means
    except Exception as e:
        print(f"[!] Erro ao processar {docker_file}: {e}", file=sys.stderr)
        return {}


def process_locust_history(history_file, warmup_sec):
    """
    Processa stats_history.csv do Locust, descartando os primeiros warmup_sec.
    Retorna métricas agregadas e métricas detalhadas por operação.
    """
    try:
        df = pd.read_csv(history_file)
        if df.empty or "Timestamp" not in df.columns:
            return None, None

        min_ts = df["Timestamp"].min()
        max_ts = df["Timestamp"].max()
        duration = max_ts - min_ts

        # Ajuste de warmup automático caso o teste seja curto (modo de teste rápido)
        actual_warmup = warmup_sec
        if actual_warmup is None:
            actual_warmup = 5 if duration <= 30 else 60

        cutoff_ts = min_ts + actual_warmup

        # Separa métricas agregadas
        agg_df = df[(df["Name"] == "Aggregated")].sort_values("Timestamp")
        if agg_df.empty:
            return None, None

        # Dados no início do período pós-warmup e no final
        agg_post = agg_df[agg_df["Timestamp"] >= cutoff_ts]
        agg_pre = agg_df[agg_df["Timestamp"] < cutoff_ts]

        if agg_post.empty:
            agg_post = agg_df

        start_reqs = agg_pre["Total Request Count"].max() if not agg_pre.empty else 0
        start_fails = agg_pre["Total Failure Count"].max() if not agg_pre.empty else 0

        end_reqs = agg_post["Total Request Count"].max()
        end_fails = agg_post["Total Failure Count"].max()

        window_duration = max(1, agg_post["Timestamp"].max() - cutoff_ts)
        useful_reqs = max(0, end_reqs - start_reqs)
        useful_fails = max(0, end_fails - start_fails)

        throughput = useful_reqs / window_duration
        failure_rate = (useful_fails / useful_reqs * 100.0) if useful_reqs > 0 else 0.0

        # Médias de tempo de resposta na janela pós-warmup
        avg_resp_time = agg_post["Total Average Response Time"].mean()
        
        # P95: converte coluna 95% para numérico (tratando N/A)
        p95_series = pd.to_numeric(agg_post["95%"], errors="coerce").dropna()
        p95_resp_time = p95_series.mean() if not p95_series.empty else avg_resp_time

        agg_metrics = {
            "start_ts": min_ts,
            "warmup_sec": actual_warmup,
            "total_requests": useful_reqs,
            "total_failures": useful_fails,
            "throughput_req_s": throughput,
            "failure_rate_perc": failure_rate,
            "avg_response_time_ms": avg_resp_time,
            "p95_response_time_ms": p95_resp_time,
        }

        # Métricas por operação individual
        ops_metrics = {}
        for (op_type, op_name), g in df[df["Name"] != "Aggregated"].groupby(["Type", "Name"]):
            g_post = g[g["Timestamp"] >= cutoff_ts]
            if g_post.empty:
                continue
            g_pre = g[g["Timestamp"] < cutoff_ts]
            pre_reqs = g_pre["Total Request Count"].max() if not g_pre.empty else 0
            post_reqs = g_post["Total Request Count"].max()
            req_count = max(0, post_reqs - pre_reqs)
            
            avg_rt = g_post["Total Average Response Time"].mean()
            p95_s = pd.to_numeric(g_post["95%"], errors="coerce").dropna()
            p95_rt = p95_s.mean() if not p95_s.empty else avg_rt

            ops_metrics[f"{op_type} {op_name}"] = {
                "requests": req_count,
                "avg_rt_ms": avg_rt,
                "p95_rt_ms": p95_rt
            }

        return agg_metrics, ops_metrics
    except Exception as e:
        print(f"[!] Erro ao processar {history_file}: {e}", file=sys.stderr)
        return None, None


def load_all_runs(raw_dir, warmup_sec):
    """Varre o diretório raw e compila todas as repetições de cada cenário."""
    history_files = glob.glob(os.path.join(raw_dir, "*_locust_stats_history.csv"))
    runs_data = []
    ops_data = []

    pattern = re.compile(r"^(reading|writing)_scenario_([ABC])_rep_(\d+)_locust_stats_history\.csv$")

    for h_file in history_files:
        basename = os.path.basename(h_file)
        match = pattern.match(basename)
        if not match:
            continue

        profile, scenario, rep = match.groups()
        rep = int(rep)

        agg_metrics, op_metrics = process_locust_history(h_file, warmup_sec)
        if not agg_metrics:
            continue

        # Arquivo de docker stats correspondente
        docker_file = os.path.join(raw_dir, f"{profile}_scenario_{scenario}_rep_{rep}_docker.csv")
        cpu_metrics = process_docker_stats(docker_file, agg_metrics["start_ts"], agg_metrics["warmup_sec"])

        run_entry = {
            "profile": profile,
            "scenario": scenario,
            "rep": rep,
            "total_requests": agg_metrics["total_requests"],
            "total_failures": agg_metrics["total_failures"],
            "throughput_req_s": agg_metrics["throughput_req_s"],
            "failure_rate_perc": agg_metrics["failure_rate_perc"],
            "avg_response_time_ms": agg_metrics["avg_response_time_ms"],
            "p95_response_time_ms": agg_metrics["p95_response_time_ms"],
            "cpu_api_gateway": cpu_metrics.get("api-gateway", np.nan),
            "cpu_customers_service": cpu_metrics.get("customers-service", np.nan),
            "cpu_vets_service": cpu_metrics.get("vets-service", np.nan),
        }
        runs_data.append(run_entry)

        if op_metrics:
            for op_label, m in op_metrics.items():
                ops_data.append({
                    "profile": profile,
                    "scenario": scenario,
                    "rep": rep,
                    "operation": op_label,
                    "requests": m["requests"],
                    "avg_rt_ms": m["avg_rt_ms"],
                    "p95_rt_ms": m["p95_rt_ms"],
                })

    return pd.DataFrame(runs_data), pd.DataFrame(ops_data)


def generate_tables(runs_df, ops_df, tables_dir):
    """Calcula médias e desvios e salva tabelas em CSV e Markdown."""
    if runs_df.empty:
        print("[!] Nenhum dado experimental encontrado para tabular.")
        return None, None

    # Mapeamento do número de usuários
    users_map = {"A": 30, "B": 80, "C": 150}
    runs_df["users"] = runs_df["scenario"].map(users_map)

    # Agregação por (profile, scenario)
    grouped = runs_df.groupby(["profile", "scenario", "users"]).agg({
        "avg_response_time_ms": ["mean", "std"],
        "p95_response_time_ms": ["mean", "std"],
        "throughput_req_s": ["mean", "std"],
        "total_requests": ["mean"],
        "failure_rate_perc": ["mean"],
        "cpu_api_gateway": ["mean"],
        "cpu_customers_service": ["mean"],
        "cpu_vets_service": ["mean"],
        "rep": "count"
    }).reset_index()

    # Flatten das colunas
    flat_cols = []
    for col in grouped.columns:
        if col[1] == "":
            flat_cols.append(col[0])
        elif col[1] == "mean":
            flat_cols.append(col[0])
        else:
            flat_cols.append(f"{col[0]}_{col[1]}")
    grouped.columns = flat_cols

    grouped = grouped.rename(columns={"rep": "num_reps"})
    summary_csv = os.path.join(tables_dir, "summary_metrics.csv")
    grouped.to_csv(summary_csv, index=False)

    # Versão Markdown formatada para o README
    summary_md = os.path.join(tables_dir, "summary_metrics.md")
    with open(summary_md, "w", encoding="utf-8") as f:
        f.write("# Tabela Resumo dos Experimentos (Média das Repetições)\n\n")
        f.write("| Perfil | Cenário | Usuários | Tempo Médio (ms) | P95 (ms) | Vazão (req/s) | Total Reqs | Falhas (%) | CPU Gateway (%) | CPU Customers (%) |\n")
        f.write("|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|\n")
        for _, row in grouped.iterrows():
            prof = "Leitura" if row["profile"] == "reading" else "Escrita"
            f.write(
                f"| {prof} | {row['scenario']} | {int(row['users'])} | "
                f"{row['avg_response_time_ms']:.2f} | {row['p95_response_time_ms']:.2f} | "
                f"{row['throughput_req_s']:.2f} | {int(row['total_requests']):,} | "
                f"{row['failure_rate_perc']:.2f}% | {row['cpu_api_gateway']:.2f}% | "
                f"{row['cpu_customers_service']:.2f}% |\n"
            )

    # Tabela de operações detalhadas
    ops_summary = None
    if not ops_df.empty:
        ops_df["users"] = ops_df["scenario"].map(users_map)
        ops_grouped = ops_df.groupby(["profile", "scenario", "users", "operation"]).agg({
            "avg_rt_ms": "mean",
            "p95_rt_ms": "mean",
            "requests": "mean"
        }).reset_index()

        ops_csv = os.path.join(tables_dir, "operations_degradation.csv")
        ops_grouped.to_csv(ops_csv, index=False)

        ops_md = os.path.join(tables_dir, "operations_degradation.md")
        with open(ops_md, "w", encoding="utf-8") as f:
            f.write("# Degradação por Operação (Tempo Médio e P95)\n\n")
            f.write("| Perfil | Cenário | Operação | Tempo Médio (ms) | P95 (ms) | Total Reqs |\n")
            f.write("|:---|:---:|:---|:---:|:---:|:---:|\n")
            for _, row in ops_grouped.iterrows():
                prof = "Leitura" if row["profile"] == "reading" else "Escrita"
                f.write(
                    f"| {prof} | {row['scenario']} ({row['users']}u) | {row['operation']} | "
                    f"{row['avg_rt_ms']:.2f} | {row['p95_rt_ms']:.2f} | {int(row['requests']):,} |\n"
                )
        ops_summary = ops_grouped

    print(f"[+] Tabelas salvas com sucesso em: {tables_dir}")
    return grouped, ops_summary


def generate_plots(grouped, ops_summary, plots_dir):
    """Gera os 5 gráficos comparativos essenciais para a análise."""
    if grouped is None or grouped.empty:
        return

    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    colors = {"reading": "#1f77b4", "writing": "#ff7f0e"}
    labels = {"reading": "Perfil 1 (Leitura)", "writing": "Perfil 2 (Escrita)"}

    # 1. Gráfico: Tempo de Resposta vs Usuários (Médio e P95)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for profile in grouped["profile"].unique():
        sub = grouped[grouped["profile"] == profile].sort_values("users")
        c = colors.get(profile, "#333333")
        lbl = labels.get(profile, profile)

        # Tempo Médio
        axes[0].plot(sub["users"], sub["avg_response_time_ms"], marker="o", color=c, label=lbl, linewidth=2)
        # P95
        axes[1].plot(sub["users"], sub["p95_response_time_ms"], marker="s", linestyle="--", color=c, label=lbl, linewidth=2)

    axes[0].set_title("Tempo Médio de Resposta vs Usuários", fontsize=12, fontweight="bold")
    axes[0].set_xlabel("Usuários Concorrentes")
    axes[0].set_ylabel("Tempo de Resposta (ms)")
    axes[0].set_xticks([30, 80, 150])
    axes[0].legend()
    axes[0].grid(True, linestyle="--", alpha=0.6)

    axes[1].set_title("Tempo de Resposta P95 vs Usuários", fontsize=12, fontweight="bold")
    axes[1].set_xlabel("Usuários Concorrentes")
    axes[1].set_ylabel("Percentil 95 (ms)")
    axes[1].set_xticks([30, 80, 150])
    axes[1].legend()
    axes[1].grid(True, linestyle="--", alpha=0.6)

    plt.tight_layout()
    p1 = os.path.join(plots_dir, "response_time_vs_users.png")
    plt.savefig(p1, dpi=300)
    plt.close()

    # 2. Gráfico: Vazão (Throughput) Comparativa
    fig, ax = plt.subplots(figsize=(8, 5))
    bar_width = 0.35
    users_list = [30, 80, 150]
    indices = np.arange(len(users_list))

    reading_sub = grouped[grouped["profile"] == "reading"].set_index("users")
    writing_sub = grouped[grouped["profile"] == "writing"].set_index("users")

    r_vals = [reading_sub.loc[u, "throughput_req_s"] if u in reading_sub.index else 0 for u in users_list]
    w_vals = [writing_sub.loc[u, "throughput_req_s"] if u in writing_sub.index else 0 for u in users_list]

    ax.bar(indices - bar_width/2, r_vals, bar_width, label="Perfil 1 (Leitura)", color="#1f77b4")
    ax.bar(indices + bar_width/2, w_vals, bar_width, label="Perfil 2 (Escrita)", color="#ff7f0e")

    ax.set_title("Comparação de Vazão (Throughput req/s)", fontsize=13, fontweight="bold")
    ax.set_xlabel("Cenário de Carga (Usuários)")
    ax.set_ylabel("Vazão Média (req/s)")
    ax.set_xticks(indices)
    ax.set_xticklabels([f"A ({30}u)", f"B ({80}u)", f"C ({150}u)"])
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.6)

    plt.tight_layout()
    p2 = os.path.join(plots_dir, "throughput_comparison.png")
    plt.savefig(p2, dpi=300)
    plt.close()

    # 3. Gráfico: Utilização de CPU dos Microsserviços
    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(grouped))
    width = 0.35

    x_labels = [f"{'Leitura' if r['profile']=='reading' else 'Escrita'} - {r['scenario']}" for _, r in grouped.iterrows()]
    ax.bar(x - width/2, grouped["cpu_api_gateway"], width, label="api-gateway CPU %", color="#2ca02c")
    ax.bar(x + width/2, grouped["cpu_customers_service"], width, label="customers-service CPU %", color="#d62728")

    ax.set_title("Consumo Médio de CPU por Microsserviço", fontsize=13, fontweight="bold")
    ax.set_ylabel("Utilização de CPU (%)")
    ax.set_xticks(x)
    ax.set_xticklabels(x_labels, rotation=30, ha="right")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.6)

    plt.tight_layout()
    p3 = os.path.join(plots_dir, "cpu_usage_comparison.png")
    plt.savefig(p3, dpi=300)
    plt.close()

    # 4. Gráfico: Taxa de Falhas
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for profile in grouped["profile"].unique():
        sub = grouped[grouped["profile"] == profile].sort_values("users")
        c = colors.get(profile, "#333333")
        lbl = labels.get(profile, profile)
        ax.plot(sub["users"], sub["failure_rate_perc"], marker="^", color=c, label=lbl, linewidth=2)

    ax.set_title("Taxa de Falhas (%) vs Usuários", fontsize=13, fontweight="bold")
    ax.set_xlabel("Usuários Concorrentes")
    ax.set_ylabel("Falhas (%)")
    ax.set_xticks([30, 80, 150])
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.6)

    plt.tight_layout()
    p4 = os.path.join(plots_dir, "failure_rate.png")
    plt.savefig(p4, dpi=300)
    plt.close()

    # 5. Gráfico: Degradação de cada Operação
    if ops_summary is not None and not ops_summary.empty:
        fig, ax = plt.subplots(figsize=(10, 5.5))
        for op in ops_summary["operation"].unique():
            sub = ops_summary[ops_summary["operation"] == op].groupby("users")["avg_rt_ms"].mean().reset_index()
            ax.plot(sub["users"], sub["avg_rt_ms"], marker="o", label=op, linewidth=2)

        ax.set_title("Degradação do Tempo de Resposta Médio por Operação", fontsize=13, fontweight="bold")
        ax.set_xlabel("Usuários Concorrentes")
        ax.set_ylabel("Tempo de Resposta Médio (ms)")
        ax.set_xticks([30, 80, 150])
        ax.legend()
        ax.grid(True, linestyle="--", alpha=0.6)

        plt.tight_layout()
        p5 = os.path.join(plots_dir, "operations_degradation.png")
        plt.savefig(p5, dpi=300)
        plt.close()

    print(f"[+] Gráficos salvos com sucesso em: {plots_dir}")


def main():
    args = parse_args()
    os.makedirs(args.tables_dir, exist_ok=True)
    os.makedirs(args.plots_dir, exist_ok=True)

    print("================================================================================")
    print("Processamento dos Resultados Experimentais")
    print(f"Diretório de entrada: {args.raw_dir}")
    print(f"Diretório de tabelas: {args.tables_dir}")
    print(f"Diretório de plots:   {args.plots_dir}")
    print("================================================================================")

    runs_df, ops_df = load_all_runs(args.raw_dir, args.warmup_sec)

    if runs_df.empty:
        print(f"[!] Nenhum resultado de execução encontrado em {args.raw_dir}.")
        print("Execute primeiro ./scripts/run_experiments.sh para gerar os dados.")
        sys.exit(0)

    print(f"[+] Total de execuções processadas: {len(runs_df)}")
    grouped, ops_summary = generate_tables(runs_df, ops_df, args.tables_dir)
    generate_plots(grouped, ops_summary, args.plots_dir)
    print("================================================================================")
    print("Processamento concluído!")
    print("================================================================================")


if __name__ == "__main__":
    main()
