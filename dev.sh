#!/bin/bash

# CDIP Admin Portal - Development Helper Script

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

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
    echo "  setup           - Initial setup (copy env, build, migrate, createsuperuser)"
    echo ""
}

function start_services() {
    echo -e "${GREEN}Starting all services...${NC}"
    docker-compose up -d
    echo -e "${GREEN}Services started!${NC}"
    echo ""
    docker-compose ps
}

function stop_services() {
    echo -e "${YELLOW}Stopping all services...${NC}"
    docker-compose stop
    echo -e "${GREEN}Services stopped!${NC}"
}

function restart_services() {
    echo -e "${YELLOW}Restarting all services...${NC}"
    docker-compose restart
    echo -e "${GREEN}Services restarted!${NC}"
}

function build_containers() {
    echo -e "${GREEN}Building containers...${NC}"
    docker-compose build
    echo -e "${GREEN}Build complete!${NC}"
}

function view_logs() {
    if [ -z "$2" ]; then
        docker-compose logs -f
    else
        docker-compose logs -f "$2"
    fi
}

function django_shell() {
    echo -e "${GREEN}Opening Django shell...${NC}"
    docker-compose exec web python3.11 manage.py shell
}

function db_shell() {
    echo -e "${GREEN}Opening database shell...${NC}"
    docker-compose exec postgres psql -U cdip_dbuser -d cdip_portaldb
}

function run_migrate() {
    echo -e "${GREEN}Running migrations...${NC}"
    docker-compose exec web python3.11 manage.py migrate
    echo -e "${GREEN}Migrations complete!${NC}"
}

function make_migrations() {
    echo -e "${GREEN}Creating migrations...${NC}"
    docker-compose exec web python3.11 manage.py makemigrations
}

function run_tests() {
    echo -e "${GREEN}Running tests...${NC}"
    if [ -z "$2" ]; then
        docker-compose exec web pytest
    else
        docker-compose exec web pytest "$2"
    fi
}

function create_superuser() {
    echo -e "${GREEN}Creating superuser...${NC}"
    docker-compose exec web python3.11 manage.py createsuperuser
}

function clean_all() {
    echo -e "${RED}WARNING: This will remove all containers and volumes!${NC}"
    read -p "Are you sure? (yes/no): " -r
    echo
    if [[ $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        echo -e "${YELLOW}Cleaning up...${NC}"
        docker-compose down -v
        echo -e "${GREEN}Cleanup complete!${NC}"
    else
        echo -e "${YELLOW}Cancelled.${NC}"
    fi
}

function show_status() {
    echo -e "${GREEN}Service status:${NC}"
    docker-compose ps
}

function initial_setup() {
    echo -e "${GREEN}Starting initial setup...${NC}"

    # Check if .env exists
    local env_template="cdip_admin/cdip_admin/.env.example"
    if [ ! -f "cdip_admin/.env" ]; then
        if [ -f "${env_template}" ]; then
            echo -e "${YELLOW}Copying ${env_template} to cdip_admin/.env${NC}"
            cp "${env_template}" cdip_admin/.env
        else
            echo -e "${RED}Missing environment template: ${env_template}${NC}"
            return 1
        fi
    else
        echo -e "${YELLOW}.env file already exists, skipping copy${NC}"
    fi

    # Build containers
    echo -e "${GREEN}Building containers...${NC}"
    docker-compose build

    # Start services
    echo -e "${GREEN}Starting services...${NC}"
    docker-compose up -d

    # Wait for services to be ready
    echo -e "${YELLOW}Waiting for services to be ready...${NC}"
    sleep 10

    # Run migrations
    echo -e "${GREEN}Running migrations...${NC}"
    docker-compose exec web python3.11 manage.py migrate

    # Create superuser
    echo -e "${GREEN}Let's create a superuser...${NC}"
    docker-compose exec web python3.11 manage.py createsuperuser

    echo -e "${GREEN}Setup complete!${NC}"
    echo ""
    echo "You can now access:"
    echo "  - Django app: http://localhost:8888"
    echo "  - Django admin: http://localhost:8888/admin"
    echo "  - Keycloak: http://localhost:8080 (admin/admin)"
    echo "  - Kong Admin: http://localhost:8001"
    echo "  - Kong Manager: http://localhost:8002"
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
