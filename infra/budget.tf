resource "aws_sns_topic" "budget" {
  name = "${local.name}-budget"
}

resource "aws_sns_topic_policy" "budget" {
  arn = aws_sns_topic.budget.arn
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = ["budgets.amazonaws.com", "cloudwatch.amazonaws.com"] }
      Action    = "SNS:Publish"
      Resource  = aws_sns_topic.budget.arn
    }]
  })
}

resource "aws_budgets_budget" "monthly" {
  name         = "${local.name}-monthly"
  budget_type  = "COST"
  limit_amount = var.monthly_budget_usd
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 25
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 75
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.alert_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
    subscriber_sns_topic_arns  = [aws_sns_topic.budget.arn]
  }
}

data "archive_file" "kill_switch" {
  type        = "zip"
  source_file = "${path.module}/kill_switch.py"
  output_path = "${path.module}/.terraform/kill_switch.zip"
}

resource "aws_iam_role" "kill_switch" {
  name = "${local.name}-kill-switch"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy_attachment" "kill_switch_logs" {
  role       = aws_iam_role.kill_switch.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "kill_switch" {
  role = aws_iam_role.kill_switch.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "apigateway:PATCH"
        Resource = "arn:aws:apigateway:us-west-2::/apis/${aws_apigatewayv2_api.api.id}/stages/*"
      },
      {
        Effect   = "Allow"
        Action   = "lambda:PutFunctionConcurrency"
        Resource = aws_lambda_function.api.arn
      },
    ]
  })
}

resource "aws_lambda_function" "kill_switch" {
  function_name    = "${local.name}-kill-switch"
  role             = aws_iam_role.kill_switch.arn
  runtime          = "python3.13"
  handler          = "kill_switch.handler"
  filename         = data.archive_file.kill_switch.output_path
  source_code_hash = data.archive_file.kill_switch.output_base64sha256
  environment {
    variables = {
      API_ID        = aws_apigatewayv2_api.api.id
      FUNCTION_NAME = aws_lambda_function.api.function_name
    }
  }
}

resource "aws_lambda_permission" "kill_switch" {
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.kill_switch.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.budget.arn
}

resource "aws_sns_topic_subscription" "kill_switch" {
  topic_arn = aws_sns_topic.budget.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.kill_switch.arn
}

resource "aws_cloudwatch_metric_alarm" "invocations" {
  alarm_name          = "${local.name}-invocations"
  alarm_description   = "Traffic spike: trips the kill switch within minutes, before billing data catches up"
  namespace           = "AWS/Lambda"
  metric_name         = "Invocations"
  dimensions          = { FunctionName = aws_lambda_function.api.function_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 500
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.budget.arn]
}
