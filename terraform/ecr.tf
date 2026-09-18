locals {
  services = ["queue-service", "booking-service", "notification-service"]
}

resource "aws_ecr_repository" "service" {
  for_each             = toset(local.services)
  name                 = "${var.project_name}-${each.value}"
  image_tag_mutability = "IMMUTABLE"   # each Jenkins build gets its own tag - never overwrite an existing one

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Project = var.project_name
  }
}

# Keeps the registry from filling up with every build ever made - keeps
# the last 15 images per service, expires anything older.
resource "aws_ecr_lifecycle_policy" "service" {
  for_each   = aws_ecr_repository.service
  repository = each.value.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "keep last 15 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 15
      }
      action = { type = "expire" }
    }]
  })
}
