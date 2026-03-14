# Claude Code — Project Guidelines

## Region
Always use **eu-west-1** (AWS Ireland). The team is based in Scotland.

## Security — Never commit secrets
- Never hardcode or commit secrets, credentials, API keys, tokens, or passwords
- AWS credentials must come from environment variables, IAM roles, or AWS Secrets Manager — never from `variables.tf` defaults or source code
- Terraform state files (`*.tfstate`, `*.tfstate.backup`) must never be committed; use remote state (e.g. S3 + DynamoDB lock)
- Use `terraform.tfvars` for local variable overrides — it is gitignored; never commit it
- If a secret is accidentally staged, treat it as compromised and rotate it immediately

## Security best practices
- **IAM least privilege**: Lambda execution roles must only have the permissions they need — do not attach `AdministratorAccess` or overly broad policies
- **No wildcards in IAM**: Avoid `"Resource": "*"` except where AWS requires it (e.g. CloudWatch Logs `CreateLogGroup`)
- **Encryption at rest**: Enable encryption for any S3 buckets, DynamoDB tables, or other storage resources
- **No public S3 buckets**: Block public access on all S3 resources unless explicitly required and reviewed
- **API Gateway auth**: New routes must have appropriate authorisation (`NONE` is only acceptable for public health-check endpoints)
- **Dependency scanning**: Keep Lambda runtime and Python dependencies up to date; flag CVEs before deploying
- **No eval/exec on user input**: Lambda handlers must never pass untrusted input to `eval()`, `exec()`, `subprocess`, or shell commands

## Terraform
- Use `var.aws_region` — default is `eu-west-1`
- Pin provider versions; do not use `>= x` without an upper bound
- Run `terraform plan` and review output before applying
- Remote state should be stored in an S3 bucket with versioning and encryption enabled

## Git workflow
- Always work on a feature branch — never commit directly to `main`
- Branch naming: `feature/<short-description>` (e.g. `feature/add-auth-endpoint`)
- One branch per feature or change; open a PR to merge into `main`
- Always confirm the branch name with the user before creating it

## General
- Follow OWASP Top 10 guidance
- Prefer environment variables and AWS SSM Parameter Store / Secrets Manager for runtime config
- Do not introduce backwards-compatibility shims or dead code
