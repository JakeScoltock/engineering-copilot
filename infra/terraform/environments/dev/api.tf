# REST API

resource "aws_api_gateway_rest_api" "api" {
  name = "${var.project}-api"

  lifecycle {
    prevent_destroy = true
  }
}

# /health

resource "aws_api_gateway_resource" "health" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  parent_id   = aws_api_gateway_rest_api.api.root_resource_id
  path_part   = "health"
}

resource "aws_api_gateway_method" "health_get" {
  rest_api_id   = aws_api_gateway_rest_api.api.id
  resource_id   = aws_api_gateway_resource.health.id
  http_method   = "GET"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "health_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.api.id
  resource_id             = aws_api_gateway_resource.health.id
  http_method             = aws_api_gateway_method.health_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.query_api.invoke_arn
}

# /repos

resource "aws_api_gateway_resource" "repos" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  parent_id   = aws_api_gateway_rest_api.api.root_resource_id
  path_part   = "repos"
}

resource "aws_api_gateway_method" "repos_post" {
  rest_api_id      = aws_api_gateway_rest_api.api.id
  resource_id      = aws_api_gateway_resource.repos.id
  http_method      = "POST"
  authorization    = "NONE"
  api_key_required = true
}

resource "aws_api_gateway_integration" "repos_post_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.api.id
  resource_id             = aws_api_gateway_resource.repos.id
  http_method             = aws_api_gateway_method.repos_post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.query_api.invoke_arn
}

# /repos/{repo_id}

resource "aws_api_gateway_resource" "repo" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  parent_id   = aws_api_gateway_resource.repos.id
  path_part   = "{repo_id}"
}

resource "aws_api_gateway_method" "repo_get" {
  rest_api_id      = aws_api_gateway_rest_api.api.id
  resource_id      = aws_api_gateway_resource.repo.id
  http_method      = "GET"
  authorization    = "NONE"
  api_key_required = true
}

resource "aws_api_gateway_integration" "repo_get_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.api.id
  resource_id             = aws_api_gateway_resource.repo.id
  http_method             = aws_api_gateway_method.repo_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.query_api.invoke_arn
}

# /repos/{repo_id}/query

resource "aws_api_gateway_resource" "repo_query" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  parent_id   = aws_api_gateway_resource.repo.id
  path_part   = "query"
}

resource "aws_api_gateway_method" "repo_query_post" {
  rest_api_id      = aws_api_gateway_rest_api.api.id
  resource_id      = aws_api_gateway_resource.repo_query.id
  http_method      = "POST"
  authorization    = "NONE"
  api_key_required = true
}

resource "aws_api_gateway_integration" "repo_query_post_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.api.id
  resource_id             = aws_api_gateway_resource.repo_query.id
  http_method             = aws_api_gateway_method.repo_query_post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.query_api.invoke_arn
}

# Deployment

resource "aws_api_gateway_deployment" "api" {
  rest_api_id = aws_api_gateway_rest_api.api.id

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_method.health_get,
      aws_api_gateway_integration.health_lambda,
      aws_api_gateway_method.repos_post,
      aws_api_gateway_integration.repos_post_lambda,
      aws_api_gateway_method.repo_get,
      aws_api_gateway_integration.repo_get_lambda,
      aws_api_gateway_method.repo_query_post,
      aws_api_gateway_integration.repo_query_post_lambda,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [
    aws_api_gateway_method.health_get,
    aws_api_gateway_integration.health_lambda,
    aws_api_gateway_method.repos_post,
    aws_api_gateway_integration.repos_post_lambda,
    aws_api_gateway_method.repo_get,
    aws_api_gateway_integration.repo_get_lambda,
    aws_api_gateway_method.repo_query_post,
    aws_api_gateway_integration.repo_query_post_lambda,
  ]
}

resource "aws_api_gateway_stage" "dev" {
  rest_api_id   = aws_api_gateway_rest_api.api.id
  deployment_id = aws_api_gateway_deployment.api.id
  stage_name    = "dev"
}

# API key auth

resource "aws_api_gateway_api_key" "default" {
  name = "${var.project}-default"
}

resource "aws_api_gateway_usage_plan" "default" {
  name = "${var.project}-default"

  api_stages {
    api_id = aws_api_gateway_rest_api.api.id
    stage  = aws_api_gateway_stage.dev.stage_name
  }

  throttle_settings {
    burst_limit = 20
    rate_limit  = 10
  }

  quota_settings {
    limit  = 1000
    period = "MONTH"
  }
}

resource "aws_api_gateway_usage_plan_key" "default" {
  key_id        = aws_api_gateway_api_key.default.id
  key_type      = "API_KEY"
  usage_plan_id = aws_api_gateway_usage_plan.default.id
}
