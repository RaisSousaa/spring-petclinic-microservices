#!/usr/bin/env bash
# ==============================================================================
# Trabalho Prático 06 — Avaliação de Desempenho com Locust
# Script de automação das 60 execuções experimentais
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

# Parâmetros padrão conforme especificação do trabalho
TOTAL_REPS=10
TEST_DURATION="420s"      # 7 minutos total (1 min aquecimento + 6 min teste útil)
WARMUP_SEC=60             # 1 minuto de descarte
TARGET_PROFILE="all"      # "reading", "writing", ou "all"
TARGET_SCENARIO="all"     # "A", "B", "C", ou "all"
QUICK_MODE=false

# Detecção automática da porta do api-gateway (8088 ou 8080)
DEFAULT_HOST=""
if curl -s -o /dev/null -w "%{http_code}" "http://localhost:8088/api/customer/owners" 2>/dev/null | grep -q "200"; then
    DEFAULT_HOST="http://localhost:8088"
elif curl -s -o /dev/null -w "%{http_code}" "http://localhost:8080/api/customer/owners" 2>/dev/null | grep -q "200"; then
    DEFAULT_HOST="http://localhost:8080"
else
    DEFAULT_HOST="http://localhost:8088"
fi
PETCLINIC_HOST="${PETCLINIC_HOST:-$DEFAULT_HOST}"

# Parsing de argumentos de linha de comando
while [[ $# -gt 0 ]]; do
    case "$1" in
        --profile)
            TARGET_PROFILE="$2"
            shift 2
            ;;
        --scenario)
            TARGET_SCENARIO="$2"
            shift 2
            ;;
        --reps)
            TOTAL_REPS="$2"
            shift 2
            ;;
        --host)
            PETCLINIC_HOST="$2"
            shift 2
            ;;
        --quick)
            QUICK_MODE=true
            TOTAL_REPS=1
            TEST_DURATION="20s"
            WARMUP_SEC=5
            shift
            ;;
        --help|-h)
            echo "Uso: $0 [opções]"
            echo "Opções:"
            echo "  --profile [reading|writing|all]   Perfil de carga (padrão: all)"
            echo "  --scenario [A|B|C|all]            Cenário de carga (padrão: all)"
            echo "  --reps [N]                        Número de repetições (padrão: 10)"
            echo "  --host [URL]                      URL do API Gateway (padrão detectado: $DEFAULT_HOST)"
            echo "  --quick                           Modo rápido para validação (1 rep, 20s)"
            echo "  --help                            Exibe esta ajuda"
            exit 0
            ;;
        *)
            echo "Opção desconhecida: $1"
            exit 1
            ;;
    esac
done

# Localização do binário do locust
LOCUST_BIN="$ROOT_DIR/.venv/bin/locust"
if [[ ! -x "$LOCUST_BIN" ]]; then
    if command -v locust &>/dev/null; then
        LOCUST_BIN="$(command -v locust)"
    else
        echo "Erro: locust não encontrado. Crie o virtualenv ou instale o locust."
        exit 1
    fi
fi

# Diretórios de saída
RESULTS_DIR="$ROOT_DIR/results"
RAW_DIR="$RESULTS_DIR/raw"
mkdir -p "$RAW_DIR" "$RESULTS_DIR/tables" "$RESULTS_DIR/plots"

# Definição dos cenários experimentais:
# Formato: "Cenário:Usuários:TaxaSpawn"
SCENARIOS_DEF=("A:30:10" "B:80:20" "C:150:30")

PROFILES_DEF=()
if [[ "$TARGET_PROFILE" == "all" || "$TARGET_PROFILE" == "reading" ]]; then
    PROFILES_DEF+=("reading:ReadingUser")
fi
if [[ "$TARGET_PROFILE" == "all" || "$TARGET_PROFILE" == "writing" ]]; then
    PROFILES_DEF+=("writing:WritingUser")
fi

# Pre-flight check de conectividade com o API Gateway
echo "Verificando se o API Gateway está respondendo em $PETCLINIC_HOST/api/customer/owners..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$PETCLINIC_HOST/api/customer/owners" 2>/dev/null || true)
if [[ "$HTTP_STATUS" != "200" ]]; then
    if [[ "$PETCLINIC_HOST" == *"8088"* ]]; then
        ALT_HOST="http://localhost:8080"
    else
        ALT_HOST="http://localhost:8088"
    fi
    ALT_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$ALT_HOST/api/customer/owners" 2>/dev/null || true)
    if [[ "$ALT_STATUS" == "200" ]]; then
        echo "API Gateway detectado na porta alternativa: $ALT_HOST"
        PETCLINIC_HOST="$ALT_HOST"
    else
        echo "ERRO CRÍTICO: Não foi possível conectar ao API Gateway em $PETCLINIC_HOST nem em $ALT_HOST (código: '$HTTP_STATUS')."
        echo "Certifique-se de que os containers do PetClinic estão em execução com 'docker compose up -d'."
        exit 1
    fi
fi
echo "Conectividade confirmada com sucesso (HTTP 200) em $PETCLINIC_HOST!"

echo "================================================================================"
echo "Iniciando Bateria Experimental de Testes de Desempenho"
echo "Host Alvo:        $PETCLINIC_HOST"
echo "Duração por teste: $TEST_DURATION (Warmup: ${WARMUP_SEC}s)"
echo "Repetições:       $TOTAL_REPS"
echo "Perfis:           ${TARGET_PROFILE}"
echo "Cenários:         ${TARGET_SCENARIO}"
echo "Resultados em:    $RAW_DIR"
echo "================================================================================"

TOTAL_TESTS=0
for prof_entry in "${PROFILES_DEF[@]}"; do
    for scn_entry in "${SCENARIOS_DEF[@]}"; do
        IFS=":" read -r scn_id _ _ <<< "$scn_entry"
        if [[ "$TARGET_SCENARIO" != "all" && "$TARGET_SCENARIO" != "$scn_id" ]]; then
            continue
        fi
        TOTAL_TESTS=$((TOTAL_TESTS + TOTAL_REPS))
    done
done

CURRENT_TEST=0
STATS_PID=""

cleanup() {
    echo -e "\n[!] Interrompendo execuções..."
    if [[ -n "$STATS_PID" ]] && kill -0 "$STATS_PID" 2>/dev/null; then
        kill "$STATS_PID" 2>/dev/null || true
    fi
    pkill -P $$ || true
    exit 1
}
trap cleanup SIGINT SIGTERM

for prof_entry in "${PROFILES_DEF[@]}"; do
    IFS=":" read -r prof_name prof_class <<< "$prof_entry"

    for scn_entry in "${SCENARIOS_DEF[@]}"; do
        IFS=":" read -r scn_id users spawn_rate <<< "$scn_entry"

        if [[ "$TARGET_SCENARIO" != "all" && "$TARGET_SCENARIO" != "$scn_id" ]]; then
            continue
        fi

        for rep in $(seq 1 "$TOTAL_REPS"); do
            CURRENT_TEST=$((CURRENT_TEST + 1))
            RUN_ID="${prof_name}_scenario_${scn_id}_rep_${rep}"
            LOCUST_CSV_PREFIX="$RAW_DIR/${RUN_ID}_locust"
            DOCKER_CSV="$RAW_DIR/${RUN_ID}_docker.csv"

            echo ""
            echo "--------------------------------------------------------------------------------"
            echo "[$CURRENT_TEST/$TOTAL_TESTS] Executando: Perfil=$prof_name | Cenário=$scn_id ($users usuários) | Repetição=$rep/$TOTAL_REPS"
            echo "Hora de início: $(date '+%Y-%m-%d %H:%M:%S')"
            echo "--------------------------------------------------------------------------------"

            # Cabeçalho do arquivo de métricas de CPU do Docker
            echo "timestamp,container,cpu_perc,mem_usage,mem_perc" > "$DOCKER_CSV"

            # Inicia o Locust em segundo plano
            "$LOCUST_BIN" -f "$ROOT_DIR/locustfile.py" "$prof_class" \
                --headless \
                -u "$users" \
                -r "$spawn_rate" \
                --run-time "$TEST_DURATION" \
                --host "$PETCLINIC_HOST" \
                --csv "$LOCUST_CSV_PREFIX" \
                --csv-full-history \
                --only-summary > "$RAW_DIR/${RUN_ID}_locust.log" 2>&1 &
            LOCUST_PID=$!

            # Coletor de CPU do Docker em segundo plano a cada 2 segundos
            (
                while kill -0 "$LOCUST_PID" 2>/dev/null; do
                    NOW=$(date +%s)
                    # Coleta métricas de api-gateway, customers-service, vets-service, visits-service
                    docker stats --no-stream --format "$NOW,{{.Name}},{{.CPUPerc}},{{.MemUsage}},{{.MemPerc}}" \
                        api-gateway customers-service vets-service visits-service 2>/dev/null >> "$DOCKER_CSV" || true
                    sleep 2
                done
            ) &
            STATS_PID=$!

            # Aguarda a conclusão do Locust
            wait "$LOCUST_PID" || true
            wait "$STATS_PID" 2>/dev/null || true
            STATS_PID=""

            echo "Concluído: $RUN_ID"
            # Pausa de estabilização de 5 segundos entre as rodadas
            sleep 5
        done
    done
done

echo ""
echo "================================================================================"
echo "Todos os testes foram concluídos com sucesso!"
echo "Arquivos brutos salvos em: $RAW_DIR"
echo "Processando resultados e gerando gráficos automaticamente..."
if [[ -x "$SCRIPT_DIR/run_analysis.sh" ]]; then
    "$SCRIPT_DIR/run_analysis.sh"
fi
echo "================================================================================"

