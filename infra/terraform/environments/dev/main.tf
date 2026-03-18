terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }

  backend "s3" {
    bucket         = "engineering-copilot-tf-state"
    key            = "environments/dev/terraform.tfstate"
    region         = "eu-west-1"
    dynamodb_table = "engineering-copilot-tf-lock"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

locals {
  vector_bucket_name = "${var.project}-vectors"
}

# Note: Lambda zip files must be built before running terraform plan/apply.
# In CI this is handled by the "Build Lambda packages" step.
# Locally: run `bash scripts/build_lambdas.sh` from the repo root first.
