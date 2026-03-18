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
  # Used as source_code_hash on Lambda functions so Terraform detects
  # source changes without needing to read the (not-yet-built) zip.
  lambda_src_hash = sha256(join("", concat(
    [for f in sort(fileset("${path.module}/../../../../src", "**/*.py")) :
    filesha256("${path.module}/../../../../src/${f}")],
    [
      filesha256("${path.module}/../../../../requirements.txt"),
      filesha256("${path.module}/../../../../scripts/build_lambdas.sh"),
    ]
  )))
}

# Builds both Lambda zips whenever source changes.
# depends_on in aws_lambda_function resources ensures the zip exists before upload.
resource "null_resource" "build_lambdas" {
  triggers = {
    src_hash = local.lambda_src_hash
  }

  provisioner "local-exec" {
    command = "bash '${path.module}/../../../../scripts/build_lambdas.sh'"
  }
}
