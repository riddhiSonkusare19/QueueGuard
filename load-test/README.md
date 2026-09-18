# Load Testing / Surge Demo

`surge.js` is the k6 script that produces the live "traffic surge"
demo for the final presentation — the thing that makes the whole
observability stack (Grafana dashboard, backlog alert, HPA scaling)
actually show something happening in real time, instead of being
inferred from static screenshots.

## Install k6

```bash
# macOS
brew install k6

# Linux (Debian/Ubuntu)
sudo gpg -k
sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update && sudo apt-get install k6
```

## Run against local docker-compose

```bash
docker compose up --build
k6 run load-test/surge.js
```

## Run against the deployed EKS cluster

```bash
# Get an externally-reachable address for the queue service - either a
# LoadBalancer Service, an Ingress, or (simplest for a demo) a port-forward:
kubectl -n queueguard port-forward svc/queue-service 8001:8001 &

k6 run -e QUEUE_URL=http://localhost:8001 load-test/surge.js
```

## What to have on screen during the demo

1. **Grafana** — the Queue Health dashboard (`monitoring/grafana-dashboard-queue-health.json`), watching queue depth climb in real time.
2. **A second terminal** running `kubectl -n queueguard get hpa -w` so the replica count change is visible live.
3. **A third terminal** running `kubectl -n queueguard get pods -w` to show new pods coming up.
4. Then run the k6 script and narrate what's happening on each screen as the surge hits, the alert fires, and HPA scales the Booking Service.

## Expected output shape

```
     scenarios: (100.00%) 1 scenario, 500 max VUs, ...
     ...
     http_req_duration..............: avg=... p(95)=...
     http_req_failed.................: rate<0.5 (threshold)
     iterations......................: ...
```

If `http_req_failed` stays low even at 500 concurrent virtual users,
that's the headline result: the queue absorbed the surge instead of
falling over.
