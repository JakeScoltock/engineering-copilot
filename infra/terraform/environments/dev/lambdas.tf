# Query API Lambda

resource "aws_lambda_function" "query_api" {
  function_name = "${var.project}-query-api"
  role          = aws_iam_role.query_api.arn
  runtime       = "python3.13"
  handler       = "src.query_api.handler.lambda_handler"
  filename      = "${path.module}/builds/query_api.zip"

  # Derived from source files so terraform plan works before the zip is built
  source_code_hash = local.lambda_src_hash

  timeout     = 30
  memory_size = 512

  environment {
    variables = {
      DYNAMODB_TABLE     = aws_dynamodb_table.jobs.name
      SQS_QUEUE_URL      = aws_sqs_queue.ingestion.url
      S3_BUCKET          = aws_s3_bucket.repo_data.bucket
      VECTOR_BUCKET_NAME = local.vector_bucket_name
    }
  }

  depends_on = [null_resource.build_lambdas]
}

resource "aws_lambda_permission" "apigw_query_api" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.query_api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.api.execution_arn}/*/*"
}

# Ingestion Lambda

resource "aws_lambda_function" "ingestion" {
  function_name = "${var.project}-ingestion"
  role          = aws_iam_role.ingestion.arn
  runtime       = "python3.13"
  handler       = "src.ingestion.handler.lambda_handler"
  filename      = "${path.module}/builds/ingestion.zip"

  source_code_hash = local.lambda_src_hash

  timeout     = 600
  memory_size = 1024

  environment {
    variables = {
      DYNAMODB_TABLE          = aws_dynamodb_table.jobs.name
      S3_BUCKET               = aws_s3_bucket.repo_data.bucket
      VECTOR_BUCKET_NAME      = local.vector_bucket_name
      GITHUB_TOKEN_SECRET_ARN = aws_secretsmanager_secret.github_token.arn
    }
  }

  depends_on = [null_resource.build_lambdas]
}

resource "aws_lambda_event_source_mapping" "ingestion_sqs" {
  event_source_arn = aws_sqs_queue.ingestion.arn
  function_name    = aws_lambda_function.ingestion.arn
  batch_size       = 1
}
