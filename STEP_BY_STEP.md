# QueueGuard — Step-by-Step Build & Deploy Guide

This walks through the entire project from an empty checkout to a live
demo on AWS EKS. Follow it top to bottom the first time; after that,
jump to whichever phase you're working on.

---

## Phase 0 — Prerequisites (do this once)

Install on your machine:
- Docker + Docker Compose
- Python 3.11+
- `kubectl`
- `terraform` (>= 1.5)
- `ansible`
- AWS CLI (`aws configure` with your credentials)
- `k6` (for the load test — see `load-test/README.md`)
- (Optional but recommended) `helm`

AWS account: make sure you have permission to create VPCs, EKS
clusters, and ECR repos. Read `docs/cloud-cost-notes.md` before you
run anything — an EKS cluster costs money the moment it's up, not just
when you're actively using it.

---

## Phase 1 — Run everything locally first

Don't skip this. Prove the application logic works before adding
cloud/K8s/CI complexity on top of it.

```bash
docker compose up --build
```

Wait ~15s for health checks, then seed a demo event:

```bash
pip install sqlalchemy psycopg2-binary
DATABASE_URL=postgresql+psycopg2://queueguard:queueguard@localhost:5432/queueguard \
    python scripts/seed_event.py concert-1 "Test Concert" 5
```

Walk through the flow with curl (see the root `README.md` for the full
sequence: join queue → admit → book → watch notification logs).

Run the unit tests for each service:

```bash
for svc in queue_service booking_service notification_service; do
  (cd $svc && pip install -r requirements-dev.txt && pytest tests/test_unit.py -v)
done
```

**Checkpoint:** all unit tests pass, and you can manually complete a
booking end to end via curl. Don't move on until this works.

---

## Phase 2 — Provision the cloud infrastructure (Terraform)

This creates the VPC, EKS cluster, and ECR repositories — the "real
cloud platform, not local-only" requirement.

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # edit if you want different sizing
terraform init
terraform plan     # review what it's about to create
terraform apply    # takes ~10-15 minutes, mostly waiting on EKS
```

When it finishes:

```bash
# Point kubectl at the new cluster
$(terraform output -raw configure_kubectl)

# Confirm it worked
kubectl get nodes
```

Note the ECR repository URLs from `terraform output ecr_repository_urls`
— you'll need the registry hostname for Phase 3 and 4.

Install metrics-server if the Terraform `helm_release` resource didn't
apply cleanly (needed for HPA to function):

```bash
helm repo add metrics-server https://kubernetes-sigs.github.io/metrics-server/
helm install metrics-server metrics-server/metrics-server -n kube-system
```

**Checkpoint:** `kubectl get nodes` shows your worker nodes as `Ready`.
`aws ecr describe-repositories` shows three `queueguard-*` repos.

---

## Phase 3 — Build and push images manually (first time, before Jenkins exists)

Before Jenkins is set up, do one manual push so you have something to
deploy and test against.

```bash
aws ecr get-login-password --region us-east-1 | \
    docker login --username AWS --password-stdin <your-ecr-registry>

for svc in queue_service booking_service notification_service; do
  name=$(echo $svc | tr '_' '-')
  docker build -t <your-ecr-registry>/queueguard-${name}:manual-v1 $svc
  docker push <your-ecr-registry>/queueguard-${name}:manual-v1
done
```

---

## Phase 4 — Deploy to Kubernetes (Ansible, rolling update)

Set up secrets first (never commit the real file):

```bash
cp k8s/02-secrets.yaml.example k8s/02-secrets.yaml
# edit k8s/02-secrets.yaml with real values if you want anything beyond the demo defaults
```

Then deploy:

```bash
cd ansible
ansible-playbook -i inventory.ini deploy.yml \
    -e registry=<your-ecr-registry> \
    -e image_tag=manual-v1
```

This applies the namespace/config/infra manifests, deploys the three
services, applies the HPA rules, and does a `kubectl set image` +
`rollout status` for each service — the rolling update in action (see
`docs/deployment-strategy.md` for why this strategy was chosen).

**Checkpoint:**
```bash
kubectl -n queueguard get pods
kubectl -n queueguard get hpa
```
All pods `Running`, HPAs showing current CPU/target.

---

## Phase 5 — Wire up observability

Install the kube-prometheus-stack (bundles Prometheus + Grafana +
Alertmanager, saves you from wiring each up by hand):

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install monitoring prometheus-community/kube-prometheus-stack -n monitoring --create-namespace
```

Apply the custom scrape config and alert rules from `monitoring/`:

```bash
kubectl -n monitoring create configmap queueguard-alert-rules \
    --from-file=monitoring/alert.rules.yml
# Then reference it in your Prometheus custom resource, or merge the
# rules into the kube-prometheus-stack values.yaml under
# additionalPrometheusRulesMap — see the chart's README for the exact key.
```

Import the dashboard:

```bash
kubectl -n monitoring port-forward svc/monitoring-grafana 3000:80
# open http://localhost:3000 (default admin/prom-operator unless you changed it)
# Dashboards > Import > upload monitoring/grafana-dashboard-queue-health.json
```

**Checkpoint:** Grafana shows the Queue Health dashboard with live
(if flat, since there's no traffic yet) panels.

---

## Phase 6 — Set up the Jenkins pipeline

1. Install Jenkins (locally, on an EC2 instance, or via Helm on the
   same cluster — your choice; keep it simple for a 2-person team).
2. Install plugins: Pipeline, Docker Pipeline, JUnit, HTML Publisher,
   SonarQube Scanner, Ansible, Amazon ECR/AWS Credentials.
3. Add credentials in Jenkins (Manage Jenkins → Credentials):
   - `aws-credentials` — AWS access key/secret
   - `ecr-registry-url` — secret text, your ECR registry hostname
   - `sonarqube-token` — if using SonarCloud/a remote SonarQube server
4. Set up a SonarQube server (SonarCloud free tier works fine for a
   training project) and configure it under Manage Jenkins → System →
   SonarQube servers, name it `sonarqube-server` to match the
   Jenkinsfile.
5. Create a new Pipeline job pointing at this repo, script path
   `ci/Jenkinsfile`.
6. Run it.

**Checkpoint:** a full pipeline run goes green through all stages:
Checkout → Unit Tests → Integration Tests → Code Review → Quality Gate
→ Coverage → Docker Build → Push to ECR → Ansible Deploy → Smoke Tests.

From here on, every push triggers the full pipeline, ending in a
rolling update to the live cluster — this is the "registry round-trip,
never deploy from the build machine directly" requirement in action.

---

## Phase 7 — Run the surge demo

See `load-test/README.md` for the full walkthrough. Short version:

```bash
kubectl -n queueguard port-forward svc/queue-service 8001:8001 &
kubectl -n queueguard get hpa -w &         # separate terminal
kubectl -n queueguard get pods -w &        # separate terminal

k6 run -e QUEUE_URL=http://localhost:8001 load-test/surge.js
```

Watch queue depth climb in Grafana, the `QueueBacklogHigh` alert fire,
HPA add replicas to `booking-service`, and (once the surge tapers off)
everything scale back down.

---

## Phase 8 — Fault injection (for the reliability demo section)

```bash
# Scenario: kill a booking-service pod mid-surge, watch K8s replace it
kubectl -n queueguard delete pod -l app=booking-service --field-selector status.phase=Running -o name | head -1 | xargs kubectl -n queueguard delete

# Scenario: simulate Redis latency (requires a bit of manual setup -
# e.g. `tc` traffic shaping inside the redis pod, or temporarily scale
# redis to 0 replicas and watch booking_service's readiness probe fail)
kubectl -n queueguard scale deployment/redis --replicas=0
# ... observe /health/ready failing, alerts firing ...
kubectl -n queueguard scale deployment/redis --replicas=1
```

Capture before/after screenshots or a short screen recording of each
scenario for the runbook documentation and final presentation.

---

## Phase 9 — Rollback demo (rolling update strategy)

Demonstrates the deployment-strategy decision from Phase 6/`docs/deployment-strategy.md`:

```bash
kubectl -n queueguard rollout history deployment/booking-service
kubectl -n queueguard rollout undo deployment/booking-service
kubectl -n queueguard rollout status deployment/booking-service
```

---

## Phase 10 — Wind down (cost control)

```bash
# Between work sessions
cd terraform && terraform destroy

# Before the next session
cd terraform && terraform apply
$(terraform output -raw configure_kubectl)
cd ../ansible && ansible-playbook -i inventory.ini deploy.yml -e registry=<registry> -e image_tag=<last-good-tag>
```

See `docs/cloud-cost-notes.md` for the node-scaling alternative if you
don't want to fully tear down between sessions.

---

## Quick reference — what lives where

| Path | What it is |
|---|---|
| `queue_service/`, `booking_service/`, `notification_service/` | The three application services |
| `docker-compose.yml` | Local dev environment |
| `k8s/` | Kubernetes manifests (numbered = apply order) |
| `terraform/` | AWS infra: VPC, EKS, ECR |
| `ansible/deploy.yml` | Deploys to the cluster, rolling update |
| `ci/Jenkinsfile` | The full CI/CD pipeline |
| `monitoring/` | Prometheus, Alertmanager, Grafana dashboard configs |
| `load-test/surge.js` | The traffic-surge demo script |
| `docs/deployment-strategy.md` | Research + decision: rolling update vs blue-green vs canary |
| `docs/cloud-cost-notes.md` | Cost management guidance |
| `scripts/seed_event.py` | Seeds a demo event into Postgres |
