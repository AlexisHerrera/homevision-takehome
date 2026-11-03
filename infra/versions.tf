terraform {
  required_version = ">= 1.10"
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 6.0" }
    archive = { source = "hashicorp/archive", version = "~> 2.7" }
  }
  # bucket is passed with -backend-config: homevision-checkboxes-tfstate-<account id>.
  backend "s3" {
    key          = "main.tfstate"
    region       = "us-west-2"
    use_lockfile = true
  }
}

provider "aws" {
  region              = "us-west-2"
  allowed_account_ids = [var.account_id]
  default_tags { tags = { Project = "homevision-checkboxes" } }
}

locals {
  name = "homevision-checkboxes"
}
