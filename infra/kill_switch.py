import os

import boto3


def handler(event, context):
    # Every request gets 429 until the next `terraform apply` restores the throttle.
    boto3.client("apigatewayv2").update_stage(
        ApiId=os.environ["API_ID"],
        StageName="$default",
        DefaultRouteSettings={"ThrottlingBurstLimit": 0, "ThrottlingRateLimit": 0},
    )
