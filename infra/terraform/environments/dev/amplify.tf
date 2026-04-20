data "aws_secretsmanager_secret_version" "github_token" {
  secret_id = aws_secretsmanager_secret.github_token.id
}

resource "aws_amplify_app" "frontend" {
  name         = "${var.project}-frontend"
  repository   = "https://github.com/JakeScoltock/engineering-copilot"
  access_token = data.aws_secretsmanager_secret_version.github_token.secret_string
  platform     = "WEB_COMPUTE"

  build_spec = <<-EOT
    version: 1
    applications:
      - appRoot: frontend
        frontend:
          phases:
            preBuild:
              commands:
                - npm ci
            build:
              commands:
                - npm run build
          artifacts:
            baseDirectory: .next
            files:
              - '**/*'
          cache:
            paths:
              - node_modules/**/*
  EOT

  environment_variables = {
    BACKEND_API_URL       = aws_api_gateway_stage.dev.invoke_url
    BACKEND_STREAMING_URL = trimsuffix(aws_lambda_function_url.query_streaming.function_url, "/")
    BACKEND_API_KEY       = aws_api_gateway_api_key.default.value
  }

  enable_basic_auth      = true
  basic_auth_credentials = base64encode("dev:${var.amplify_basic_auth_password}")
}

resource "aws_amplify_branch" "main" {
  app_id            = aws_amplify_app.frontend.id
  branch_name       = "main"
  stage             = "DEVELOPMENT"
  enable_auto_build = false
}
