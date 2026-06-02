#!/bin/bash
# UniMind 域名配置管理脚本
# 用法: ./scripts/domain-config.sh [domain]
# 示例: ./scripts/domain-config.sh korsonedu.com
#       ./scripts/domain-config.sh unimind-ai.com

set -e

# 配置文件路径
CONFIG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOMAIN_CONFIG="$CONFIG_DIR/domain.env"

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

usage() {
    echo "用法: $0 [domain]"
    echo ""
    echo "可用域名:"
    echo "  korsonedu.com     - 临时方案（已备案）"
    echo "  unimind-ai.com    - 主域名（需备案后使用）"
    echo ""
    echo "示例:"
    echo "  $0 korsonedu.com"
    echo "  $0 unimind-ai.com"
    exit 1
}

# 读取当前配置
load_config() {
    if [ -f "$DOMAIN_CONFIG" ]; then
        source "$DOMAIN_CONFIG"
    fi
}

# 保存配置
save_config() {
    local domain=$1
    local base_url="https://www.${domain}"
    local cookie_domain=".${domain}"

    cat > "$DOMAIN_CONFIG" << EOF
# UniMind 域名配置
# 自动生成于 $(date)
# 切换域名: ./scripts/domain-config.sh [domain]

ACTIVE_DOMAIN=${domain}
BASE_URL=${base_url}
API_URL=${base_url}/api
COOKIE_DOMAIN=${cookie_domain}
EOF

    echo -e "${GREEN}✓ 配置已保存到: ${DOMAIN_CONFIG}${NC}"
}

# 更新前端环境变量
update_frontend() {
    local domain=$1
    local frontend_env="$CONFIG_DIR/frontend/.env"

    if [ -f "$frontend_env" ]; then
        # 更新 VITE_API_URL
        sed -i '' "s|^VITE_API_URL=.*|VITE_API_URL=https://www.${domain}/api|" "$frontend_env"
        echo -e "${GREEN}✓ 前端配置已更新${NC}"
    fi
}

# 更新后端环境变量
update_backend() {
    local domain=$1
    local backend_env="/opt/unimind/backend/.env"

    echo -e "${YELLOW}请在服务器上执行以下命令:${NC}"
    echo ""
    echo "# 更新 Cookie 域名"
    echo "sed -i 's|^SESSION_COOKIE_DOMAIN=.*|SESSION_COOKIE_DOMAIN=.${domain}|' ${backend_env}"
    echo "sed -i 's|^CSRF_COOKIE_DOMAIN=.*|CSRF_COOKIE_DOMAIN=.${domain}|' ${backend_env}"
    echo ""
    echo "# 更新 CORS/CSRF（如果需要）"
    echo "# 当前配置已包含两个域名，无需修改"
    echo ""
    echo "# 重启服务"
    echo "systemctl restart unimind.service"
}

# 显示 Nginx 配置
show_nginx_config() {
    local domain=$1

    echo -e "${YELLOW}Nginx 配置已存在于:${NC}"
    echo "  - /etc/nginx/sites-enabled/unimind-ai.com.conf"
    echo "  - /etc/nginx/sites-enabled/www.korsonedu.com.conf"
    echo ""
    echo "两个域名都已配置指向同一应用，无需修改。"
}

# 显示 DNS 配置
show_dns_config() {
    local domain=$1

    echo -e "${YELLOW}DNS 配置:${NC}"
    echo "  - 确保 ${domain} A 记录指向 47.104.77.217"
    echo "  - 确保 www.${domain} A 记录指向 47.104.77.217"
}

# 主流程
main() {
    local domain=$1

    if [ -z "$domain" ]; then
        # 显示当前配置
        load_config
        if [ -n "$ACTIVE_DOMAIN" ]; then
            echo -e "${GREEN}当前活跃域名: ${ACTIVE_DOMAIN}${NC}"
            echo "API 地址: ${API_URL}"
            echo "Cookie 域名: ${COOKIE_DOMAIN}"
        else
            echo "尚未配置域名"
        fi
        usage
    fi

    # 验证域名
    case "$domain" in
        korsonedu.com|unimind-ai.com)
            ;;
        *)
            echo "错误: 不支持的域名 $domain"
            usage
            ;;
    esac

    echo -e "${GREEN}切换到域名: ${domain}${NC}"
    echo ""

    # 保存配置
    save_config "$domain"

    # 更新前端
    update_frontend "$domain"

    # 显示后端操作
    update_backend "$domain"

    # 显示 Nginx 配置
    show_nginx_config "$domain"

    # 显示 DNS 配置
    show_dns_config "$domain"

    echo ""
    echo -e "${GREEN}✓ 配置完成！${NC}"
    echo ""
    echo "下一步:"
    echo "1. 重新构建前端: cd frontend && npm run build"
    echo "2. 在服务器上执行上述命令"
    echo "3. 测试访问: https://www.${domain}"
}

main "$@"
