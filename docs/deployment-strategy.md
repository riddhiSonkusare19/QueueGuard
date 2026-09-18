# Kubernetes Deployment Strategy — Research & Decision

Per instructor guidance: research the deployment strategy options, then
implement **only one** of them. This document records that research and
the decision made for QueueGuard.

## Options considered

### 1. Rolling Update (chosen)
Kubernetes' native `Deployment` strategy. New pods are brought up
gradually while old pods are terminated gradually, controlled by
`maxSurge` (how many extra pods above the desired count are allowed
during the rollout) and `maxUnavailable` (how many pods can be down at
once).

**Pros:**
- Native to `Deployment` objects — no extra infrastructure, no second
  environment to provision or pay for.
- Zero-downtime by default when `maxUnavailable: 0`.
- Simple rollback: `kubectl rollout undo deployment/<name>`.
- Works cleanly with a single Service pointing at one Deployment — no
  manual traffic-switch step.

**Cons:**
- Old and new versions run simultaneously during the rollout, so both
  versions must be compatible with the same database schema at once.
- A bad rollout is caught pod-by-pod (via readiness probes), not
  all-at-once — slightly slower to detect a fully broken version than
  blue-green's instant cutover.

### 2. Blue-Green (considered, not implemented)
Two full environments ("blue" = current, "green" = new) run side by
side. Traffic is switched all at once by updating the Service selector
(or a load balancer) from blue to green.

**Pros:** instant, atomic cutover; instant rollback (flip back to
blue); the new version is fully tested in isolation before receiving
any real traffic.

**Cons:** requires roughly 2x the resource footprint while both
environments are up; more manifests and manual/scripted switch-over
logic to build and maintain; overkill for a 2-service, 2-person
project on free-tier cloud resources.

### 3. Canary (considered, not implemented)
A small percentage of traffic is routed to the new version first,
increased gradually. Needs a service mesh or ingress controller with
traffic-splitting support (e.g. Istio, Flagger, or NGINX weighted
routing) to do properly.

**Cons:** the extra tooling required is disproportionate to this
project's scope and timeline.

## Decision

**QueueGuard uses Rolling Update**, Kubernetes' default `Deployment`
strategy, explicitly configured (not left at cluster defaults) in each
service's manifest:

```yaml
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxSurge: 1
    maxUnavailable: 0   # zero-downtime: never drop below the desired replica count
```

**Why:** it demonstrates the core SRE concept the training is asking
for (safe, zero-downtime deployment with automatic rollback capability)
without the extra infrastructure cost and complexity of running two
full environments side by side — appropriate for a two-person team on
free-tier cloud resources and a two-week timeline. Blue-green remains
a valid, documented alternative if the team later has time/resources
to demonstrate it as a stretch goal.

## How to demonstrate this in the final presentation

```bash
# Trigger a rollout (e.g. after Jenkins pushes a new image tag)
kubectl -n queueguard set image deployment/booking-service \
    booking-service=<registry>/queueguard-booking-service:<new-tag>

# Watch it happen live
kubectl -n queueguard rollout status deployment/booking-service

# Show rollout history
kubectl -n queueguard rollout history deployment/booking-service

# Demonstrate rollback
kubectl -n queueguard rollout undo deployment/booking-service
```
