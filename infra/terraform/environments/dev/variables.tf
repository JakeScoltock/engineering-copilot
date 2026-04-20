variable "aws_region" {
  description = "AWS region to deploy into."
  default     = "eu-west-1"
}

variable "project" {
  description = "Project name used as a prefix for all resource names."
  default     = "engineering-copilot"
}

variable "amplify_basic_auth_password" {
  description = "Password for Amplify basic auth. Username is 'dev'."
  sensitive   = true
}


