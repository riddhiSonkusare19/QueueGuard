# Cloud Cost Notes

Per instructor guidance: use free-tier resources where possible, avoid
oversized instances, and shut things down when not actively working.

## What costs money here

- **EKS control plane**: ~$0.10/hour (~$2.40/day) - this is **not**
  free-tier eligible, unlike EC2. This is the main fixed cost of this
  setup, and it runs whether or not you're actively working.
- **Worker nodes** (`t3.small` x2 by default): a few cents/hour each,
  roughly free-tier-adjacent if you're on a new AWS account with
  ongoing free-tier EC2 hours - check your account's actual free-tier
  status, it's not guaranteed.
- **NAT Gateway**: ~$0.045/hour + data - kept to a single NAT gateway
  (not one per AZ) specifically to control this cost.

## How to keep costs down

```bash
# Scale worker nodes to zero overnight/between sessions (control plane
# still bills, but this is the biggest lever you have)
aws eks update-nodegroup-config \
    --cluster-name queueguard --nodegroup-name default \
    --scaling-config minSize=0,maxSize=3,desiredSize=0

# Scale back up before a work session or the demo
aws eks update-nodegroup-config \
    --cluster-name queueguard --nodegroup-name default \
    --scaling-config minSize=1,maxSize=3,desiredSize=2
```

**Best option if cost is a real concern:** `terraform destroy` at the
end of each work session and `terraform apply` at the start of the
next one. This project's state is disposable — Postgres data doesn't
need to persist between sessions during development — so this is safe
here. Keep the ECR repos as the one thing worth *not* tearing down
constantly (images take time to rebuild/push).

```bash
terraform destroy    # end of session
terraform apply      # start of next session (~10-15 min for EKS to come up)
```

## If cloud costs become a blocker

Per the training guidance: talk to the engagement manager or trainer
early if this becomes a problem, rather than close to the deadline.
Keep the local `docker-compose.yml` setup working throughout as a
fallback demo path, and document any roadblocks encountered — that's
itself a valid part of the demonstration.
