# QueueGuard

A fault-tolerant virtual queue and slot-booking platform. Built as an SRE
demonstration project: the domain itself (a ticket-drop style surge) is a
reliability problem, so observability, admission control, and safe
concurrency aren't bolted on - they're the point of the project.

## Services

| Service | Port | Responsibility |
|---|---|---|
| `queue_service` | 8001 | Virtual waiting room. Admits users in controlled batches. Redis-backed. |
| `booking_service` | 8002 | Claims slots for admitted users, with a distributed lock to prevent double-booking. Postgres + Redis. |
| `notification_service` | - | Consumes booking events off RabbitMQ, simulates notifications. |

## Quick start

```bash
docker compose up --build
```

This starts Postgres, Redis, RabbitMQ, and all three services. Give it
~15 seconds for health checks to pass.

Seed a demo event so there's something to book:

```bash
pip install sqlalchemy psycopg2-binary
DATABASE_URL=postgresql+psycopg2://queueguard:queueguard@localhost:5432/queueguard \
    python scripts/seed_event.py concert-1 "Test Concert" 5
```

## Try it end to end

```bash
# 1. Join the queue
curl -X POST localhost:8001/queue/join \
    -H "Content-Type: application/json" \
    -d '{"user_id": "alice", "event_id": "concert-1"}'
# -> {"status": "queued", "position": 1, ...}

# 2. Check status (the background admitter runs every 5s by default,
#    or trigger it manually)
curl -X POST "localhost:8001/queue/admit-batch/concert-1?batch_size=1"

curl localhost:8001/queue/status/concert-1/alice
# -> {"status": "admitted", "admission_token": "..."}

# 3. Claim a slot with the admission token
curl -X POST localhost:8002/bookings \
    -H "Content-Type: application/json" \
    -d '{"user_id": "alice", "event_id": "concert-1", "admission_token": "<paste token here>"}'
# -> {"id": "...", "status": "confirmed", ...}

# 4. Watch the Notification Service logs
docker compose logs -f notification_service
```

## Running tests

Each service has its own unit tests (fast, no dependencies - uses
`fakeredis` and in-memory sqlite) and integration tests (require the
real infrastructure from `docker-compose.yml`).

```bash
# Unit tests only, per service
cd queue_service && pip install -r requirements-dev.txt && pytest tests/test_unit.py -v
cd booking_service && pip install -r requirements-dev.txt && pytest tests/test_unit.py -v
cd notification_service && pip install -r requirements-dev.txt && pytest tests/test_unit.py -v

# Integration tests (bring infra up first)
docker compose up -d postgres redis rabbitmq
cd queue_service && pytest tests/test_integration.py -m integration -v
cd booking_service && pytest tests/test_integration.py -m integration -v
cd notification_service && pytest tests/test_integration.py -m integration -v

# Coverage report
pytest --cov=app --cov-report=term-missing tests/test_unit.py
```

The booking service's `test_two_admitted_users_racing_for_the_last_slot_only_one_wins`
test is the signature test for this project - it proves the distributed
lock actually prevents a double-booking race condition, using two real
threads hitting the same slot at the same time.

## Full project layout

This repo now covers the whole pipeline, not just the app:

```
queue_service/, booking_service/, notification_service/   application code + tests
docker-compose.yml                                        local dev environment
k8s/                                                       Kubernetes manifests (rolling update, HPA)
terraform/                                                 AWS VPC + EKS + ECR
ansible/deploy.yml                                         deploy playbook (registry -> cluster)
ci/Jenkinsfile                                              full CI/CD pipeline
monitoring/                                                 Prometheus, Alertmanager, Grafana dashboard
load-test/surge.js                                          k6 traffic-surge script for the live demo
docs/deployment-strategy.md                                  rolling-update vs blue-green research + decision
docs/cloud-cost-notes.md                                     free-tier / cost-control guidance
```

**Start here:** [`STEP_BY_STEP.md`](./STEP_BY_STEP.md) — walks through
everything from local run to full cloud deploy and the live surge demo.
