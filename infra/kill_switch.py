import os

import boto3


def handler(event, context):
    # Everything stays off until the next `terraform apply` restores the throttle and concurrency.
    boto3.client("apigatewayv2").update_stage(
        ApiId=os.environ["API_ID"],
        StageName="$default",
        DefaultRouteSettings={"ThrottlingBurstLimit": 0, "ThrottlingRateLimit": 0},
    )
    boto3.client("lambda").put_function_concurrency(
        FunctionName=os.environ["FUNCTION_NAME"],
        ReservedConcurrentExecutions=0,
    )
