module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.24"

  cluster_name    = var.project_name
  cluster_version = var.cluster_version

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  # Lets you (and Jenkins/Ansible) reach the API server directly for a
  # training project. Lock this down to specific CIDRs for anything
  # beyond a demo.
  cluster_endpoint_public_access = true

  eks_managed_node_groups = {
    default = {
      instance_types = [var.node_instance_type]
      capacity_type  = "ON_DEMAND"  # SPOT is cheaper but can be reclaimed mid-demo - avoid during presentation day

      min_size     = var.node_min_size
      max_size     = var.node_max_size
      desired_size = var.node_desired_size
    }
  }

  # Gives the Terraform-applying identity cluster-admin - convenient for
  # a training project with one or two operators.
  enable_cluster_creator_admin_permissions = true

  tags = {
    Project = var.project_name
  }
}

# metrics-server is required for the HPA manifests in ../k8s/30-hpa.yaml
# to function. EKS does not ship it by default (unlike k3s).
resource "helm_release" "metrics_server" {
  name       = "metrics-server"
  repository = "https://kubernetes-sigs.github.io/metrics-server/"
  chart      = "metrics-server"
  namespace  = "kube-system"

  depends_on = [module.eks]
}
