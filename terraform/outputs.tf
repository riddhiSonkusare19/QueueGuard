output "ecr_repository_urls" {
  description = "Push images here from Jenkins, e.g. <url>:<git-sha>"
  value       = { for k, v in aws_ecr_repository.service : k => v.repository_url }
}

output "eks_cluster_name" {
  value = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "configure_kubectl" {
  description = "Run this after apply to point kubectl at the new cluster"
  value       = "aws eks update-kubeconfig --region ${var.aws_region} --name ${module.eks.cluster_name}"
}
