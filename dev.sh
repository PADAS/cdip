#!/bin/bash

# CDIP Admin Portal - Development Helper Script

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Use Compose v2 (the `docker compose` plugin) when available; fall back to
# the legacy `docker-compose` standalone binary if a host only has v1.
if docker compose version >/dev/null 2>&1; then
    DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    DC="docker-compose"
else
    echo -e "${RED}Neither 'docker compose' (v2 plugin) nor 'docker-compose' (v1) found on PATH.${NC}" >&2
    exit 1
fi

function print_help() {
    echo "CDIP Admin Portal - Development Helper Script"
    echo ""
    echo "Usage: ./dev.sh [command]"
    echo ""
    echo "Commands:"
    echo "  start           - Start all services"
    echo "  stop            - Stop all services"
    echo "  restart         - Restart all services"
    echo "  build           - Build/rebuild containers"
    echo "  logs [service]  - View logs (optionally for specific service)"
    echo "  shell           - Open Django shell"
    echo "  dbshell         - Open database shell"
    echo "  migrate         - Run database migrations"
    echo "  makemigrations  - Create new migrations"
    echo "  test [path]     - Run tests (optionally for specific path)"
    echo "  createsuperuser - Create Django superuser"
    echo "  clean           - Stop and remove all containers and volumes"
    echo "  status          - Show status of all services"
    echo "  setup           - One-command setup: secret, build, wait, migrate, kong routes, dev admin"
    echo ""
}

function start_services() {
    echo -e "${GREEN}Starting all services...${NC}"
    $DC up -d
    echo -e "${GREEN}Services started!${NC}"
    echo ""
    $DC ps
}

function stop_services() {
    echo -e "${YELLOW}Stopping all services...${NC}"
    $DC stop
    echo -e "${GREEN}Services stopped!${NC}"
}

function restart_services() {
    echo -e "${YELLOW}Restarting all services...${NC}"
    $DC restart
    echo -e "${GREEN}Services restarted!${NC}"
}

function build_containers() {
    echo -e "${GREEN}Building containers...${NC}"
    $DC build
    echo -e "${GREEN}Build complete!${NC}"
}

function view_logs() {
    if [ -z "$2" ]; then
        $DC logs -f
    else
        $DC logs -f "$2"
    fi
}

function django_shell() {
    echo -e "${GREEN}Opening Django shell...${NC}"
    $DC exec web python3.11 manage.py shell
}

function db_shell() {
    echo -e "${GREEN}Opening database shell...${NC}"
    $DC exec postgres psql -U cdip_dbuser -d cdip_portaldb
}

function run_migrate() {
    echo -e "${GREEN}Running migrations...${NC}"
    $DC exec web python3.11 manage.py migrate
    echo -e "${GREEN}Migrations complete!${NC}"
}

function make_migrations() {
    echo -e "${GREEN}Creating migrations...${NC}"
    $DC exec web python3.11 manage.py makemigrations
}

function run_tests() {
    echo -e "${GREEN}Running tests...${NC}"
    if [ -z "$2" ]; then
        $DC exec web pytest
    else
        $DC exec web pytest "$2"
    fi
}

function create_superuser() {
    echo -e "${GREEN}Creating superuser...${NC}"
    $DC exec web python3.11 manage.py createsuperuser
}

function clean_all() {
    echo -e "${RED}WARNING: This will remove all containers and volumes!${NC}"
    read -p "Are you sure? (yes/no): " -r
    echo
    if [[ $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        echo -e "${YELLOW}Cleaning up...${NC}"
        $DC down -v
        echo -e "${GREEN}Cleanup complete!${NC}"
    else
        echo -e "${YELLOW}Cancelled.${NC}"
    fi
}

function show_status() {
    echo -e "${GREEN}Service status:${NC}"
    $DC ps
}

function initial_setup() {
    echo -e "${GREEN}Starting initial setup...${NC}"

    # 1. Kong's image builds from a sibling repo; fail early with guidance if absent.
    local kong_dir="${KONG_DIR:-../gundi-kp-dynamic-routing}"
    if [ ! -d "${kong_dir}" ]; then
        echo -e "${RED}Kong repo not found at ${kong_dir}.${NC}" >&2
        echo -e "${YELLOW}Clone it (or set KONG_DIR), then re-run ./dev.sh setup:${NC}" >&2
        echo "  git clone <gundi-kp-dynamic-routing repo> ../gundi-kp-dynamic-routing" >&2
        return 1
    fi

    # 2. Root .env (compose interpolation): ensure OIDC_SESSION_SECRET exists.
    touch .env
    if ! grep -q '^OIDC_SESSION_SECRET=' .env; then
        echo -e "${YELLOW}Generating OIDC_SESSION_SECRET in .env${NC}"
        echo "OIDC_SESSION_SECRET=$(openssl rand -base64 32 | tr -d '\n')" >> .env
    fi

    # Secondary Django app env template (retained as-is; stack runs off compose env).
    local env_template="cdip_admin/cdip_admin/.env.example"
    if [ ! -f "cdip_admin/.env" ] && [ -f "${env_template}" ]; then
        echo -e "${YELLOW}Copying ${env_template} to cdip_admin/.env${NC}"
        cp "${env_template}" cdip_admin/.env
    elif [ ! -f "cdip_admin/.env" ]; then
        echo -e "${YELLOW}Note: ${env_template} not found; skipping cdip_admin/.env copy (stack uses compose env).${NC}"
    fi

    # 3. Build (Kong builds from the verified sibling repo).
    echo -e "${GREEN}Building containers...${NC}"
    $DC build

    # 4. Start everything, then block until the core services are healthy.
    echo -e "${GREEN}Starting services...${NC}"
    # Start the full stack (incl. celery, kong-bootstrap); --wait below gates on the core services.
    $DC up -d
    echo -e "${YELLOW}Waiting for services to be healthy...${NC}"
    $DC up -d --wait postgres redis keycloak kong web caddy

    # 5. Migrations (also creates the GlobalAdmin / OrganizationMember groups).
    echo -e "${GREEN}Running migrations...${NC}"
    $DC exec -T web python3.11 manage.py migrate

    # 6. Register Kong's service/route/oidc plugin (idempotent; needs the secret above).
    echo -e "${GREEN}Registering Kong routes...${NC}"
    $DC run --rm kong-bootstrap

    # 7. Seed the local dev admin (idempotent; matches the Keycloak dev/dev user).
    echo -e "${GREEN}Seeding dev admin...${NC}"
    $DC exec -T web python3.11 manage.py seed_dev_admin

    echo -e "${GREEN}Setup complete!${NC}"
    echo ""
    echo "Portal (through Caddy + Kong, with auth):"
    echo "  https://web.127.0.0.1.nip.io   (accept the self-signed cert; log in dev / dev)"
    echo ""
    echo "Other endpoints:"
    echo "  http://localhost:8888                    - Django direct (bypasses Kong/auth)"
    echo "  https://keycloak.127.0.0.1.nip.io/auth   - Keycloak (admin / admin)"
    echo "  http://localhost:8001                    - Kong Admin API"
}

# Main script logic
case "$1" in
    start)
        start_services
        ;;
    stop)
        stop_services
        ;;
    restart)
        restart_services
        ;;
    build)
        build_containers
        ;;
    logs)
        view_logs "$@"
        ;;
    shell)
        django_shell
        ;;
    dbshell)
        db_shell
        ;;
    migrate)
        run_migrate
        ;;
    makemigrations)
        make_migrations
        ;;
    test)
        run_tests "$@"
        ;;
    createsuperuser)
        create_superuser
        ;;
    clean)
        clean_all
        ;;
    status)
        show_status
        ;;
    setup)
        initial_setup
        ;;
    *)
        print_help
        ;;
esac
