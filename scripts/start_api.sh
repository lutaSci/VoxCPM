#!/bin/bash
# ============================================================
# VoxCPM API 守护进程启动脚本
# 
# 使用方法:
#   ./scripts/start_api.sh          # 启动服务
#   ./scripts/start_api.sh stop     # 停止服务
#   ./scripts/start_api.sh restart  # 重启服务
#   ./scripts/start_api.sh status   # 查看状态
#   ./scripts/start_api.sh logs     # 查看日志 (实时)
#   ./scripts/start_api.sh logs -n 100  # 查看最近100行日志
# ============================================================

# 配置
APP_NAME="voxcpm-api"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${APP_DIR}/logs"
LOG_FILE="${LOG_DIR}/api.log"
PID_FILE="${LOG_DIR}/api.pid"

# 默认参数
HOST="${VOXCPM_HOST:-0.0.0.0}"
PORT="${VOXCPM_PORT:-6006}"

# 确保日志目录存在
mkdir -p "${LOG_DIR}"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

get_pid() {
    if [ -f "${PID_FILE}" ]; then
        cat "${PID_FILE}"
    else
        echo ""
    fi
}

is_running() {
    local pid=$(get_pid)
    if [ -n "${pid}" ] && kill -0 "${pid}" 2>/dev/null; then
        return 0
    else
        return 1
    fi
}

start() {
    if is_running; then
        log_warn "${APP_NAME} is already running (PID: $(get_pid))"
        return 1
    fi
    
    log_info "Starting ${APP_NAME}..."
    log_info "Host: ${HOST}, Port: ${PORT}"
    log_info "Log file: ${LOG_FILE}"
    
    cd "${APP_DIR}"
    
    # 使用 nohup 在后台运行，日志输出到文件
    nohup python run_api.py --host "${HOST}" --port "${PORT}" \
        >> "${LOG_FILE}" 2>&1 &
    
    local pid=$!
    echo "${pid}" > "${PID_FILE}"
    
    # 等待几秒检查是否启动成功
    sleep 2
    
    if is_running; then
        log_info "${APP_NAME} started successfully (PID: ${pid})"
        log_info "API Docs: http://${HOST}:${PORT}/docs"
        log_info "View logs: $0 logs"
    else
        log_error "Failed to start ${APP_NAME}. Check logs: ${LOG_FILE}"
        return 1
    fi
}

stop() {
    if ! is_running; then
        log_warn "${APP_NAME} is not running"
        rm -f "${PID_FILE}"
        return 0
    fi
    
    local pid=$(get_pid)
    log_info "Stopping ${APP_NAME} (PID: ${pid})..."
    
    # 优雅关闭
    kill "${pid}" 2>/dev/null
    
    # 等待进程结束
    local count=0
    while is_running && [ ${count} -lt 30 ]; do
        sleep 1
        count=$((count + 1))
    done
    
    # 如果还在运行，强制关闭
    if is_running; then
        log_warn "Force killing ${APP_NAME}..."
        kill -9 "${pid}" 2>/dev/null
    fi
    
    rm -f "${PID_FILE}"
    log_info "${APP_NAME} stopped"
}

restart() {
    stop
    sleep 2
    start
}

status() {
    if is_running; then
        local pid=$(get_pid)
        log_info "${APP_NAME} is running (PID: ${pid})"
        echo ""
        echo "Process info:"
        ps -p "${pid}" -o pid,ppid,user,%cpu,%mem,etime,command
    else
        log_warn "${APP_NAME} is not running"
    fi
}

show_logs() {
    if [ ! -f "${LOG_FILE}" ]; then
        log_error "Log file not found: ${LOG_FILE}"
        return 1
    fi
    
    # 解析额外参数
    local lines=50
    local follow=true
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            -n|--lines)
                lines="$2"
                shift 2
                ;;
            -f|--follow)
                follow=true
                shift
                ;;
            --no-follow)
                follow=false
                shift
                ;;
            *)
                shift
                ;;
        esac
    done
    
    echo "=== ${APP_NAME} Logs (${LOG_FILE}) ==="
    echo ""
    
    if [ "${follow}" = true ]; then
        tail -n "${lines}" -f "${LOG_FILE}"
    else
        tail -n "${lines}" "${LOG_FILE}"
    fi
}

# 主命令处理
case "$1" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    status)
        status
        ;;
    logs)
        shift
        show_logs "$@"
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs}"
        echo ""
        echo "Commands:"
        echo "  start     Start the API server in background"
        echo "  stop      Stop the API server"
        echo "  restart   Restart the API server"
        echo "  status    Show server status"
        echo "  logs      Show logs (default: tail -f last 50 lines)"
        echo ""
        echo "Logs options:"
        echo "  logs -n 100      Show last 100 lines"
        echo "  logs --no-follow Show logs without following"
        echo ""
        echo "Environment variables:"
        echo "  VOXCPM_HOST      Host to bind (default: 0.0.0.0)"
        echo "  VOXCPM_PORT      Port to bind (default: 6006)"
        exit 1
        ;;
esac
