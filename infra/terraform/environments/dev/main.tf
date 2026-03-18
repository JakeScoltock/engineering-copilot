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

  # Hash of all Python source files + requirements + build script.
  # Changes here trigger Terraform to upload new Lambda zips.
  lambda_src_hash = sha256(join("", concat(
    [for f in sort(fileset("${path.module}/../../../../src", "**/*.py")) :
    filesha256("${path.module}/../../../../src/${f}")],
    [
      filesha256("${path.module}/../../../../requirements.txt"),
      filesha256("${path.module}/../../../../scripts/build_lambdas.sh"),
    ]
  )))
}

# Note: Lambda zip files must be built before running terraform plan/apply.
# In CI this is handled by the "Build Lambda packages" step.
# Locally: run `bash scripts/build_lambdas.sh` from the repo root first.
