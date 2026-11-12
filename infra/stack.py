"""The AWS demo as code: what PLAN.md §9.3 first built by hand in the console.

Read top to bottom, it follows the same order as the hand-made setup: the data bucket,
the API's Lambda function, the page's bucket, and the CloudFront distribution that
puts both behind one address. ``cdk deploy`` turns this into a CloudFormation
template; CloudFormation compares it with what exists and changes only the
difference, so deploying twice is the same as deploying once.

The Lambda code and the page's files are parameters, like ``create_app``'s data
directory: ``app.py`` passes the real builds, the tests pass small stand-ins, and
neither needs AWS to synthesise the template.
"""

from collections.abc import Sequence
from typing import Any

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
)
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from constructs import Construct

# Names shared with the app, which reads them back: publish-deals uploads the
# snapshots under DEALS_PREFIX and finds the bucket through the stack's output.
from koopjeskompas.publish import DATA_BUCKET_OUTPUT, DEALS_PREFIX

API_HANDLER = "koopjeskompas.cloud.aws.lambda_handler.handler"
SITE_URL_OUTPUT = "SiteUrl"


class KoopjeskompasStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        api_code: lambda_.Code,
        site_sources: Sequence[s3deploy.ISource],
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # --- the deals snapshot ----------------------------------------------
        # Versioned, so last week's snapshot can be restored; old versions expire
        # after 90 days. RETAIN: tearing down the stack never deletes the data.
        data_bucket = s3.Bucket(
            self,
            "DataBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            versioned=True,
            lifecycle_rules=[
                s3.LifecycleRule(noncurrent_version_expiration=Duration.days(90))
            ],
            removal_policy=RemovalPolicy.RETAIN,
        )

        # --- the API -----------------------------------------------------------
        # Logs kept a week rather than forever: stored logs cost a little each month.
        api_logs = logs.LogGroup(
            self,
            "ApiLogs",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )
        api = lambda_.Function(
            self,
            "Api",
            runtime=lambda_.Runtime.PYTHON_3_14,
            # The zip holds arm64 builds (scripts/build-lambda.sh); the two must match.
            architecture=lambda_.Architecture.ARM_64,
            code=api_code,
            handler=API_HANDLER,
            # CPU comes with memory: 512 MB keeps cold starts near a second.
            memory_size=512,
            timeout=Duration.seconds(10),
            # At most 5 copies at once: a flood of requests gets 429s, not a bill.
            reserved_concurrent_executions=5,
            environment={"DEALS_BUCKET": data_bucket.bucket_name},
            log_group=api_logs,
        )
        # Least privilege: read the snapshots, nothing else. Not grant_read(),
        # which would also allow listing the bucket and reading anything in it.
        api.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject"],
                resources=[data_bucket.arn_for_objects(f"{DEALS_PREFIX}*")],
            )
        )
        # AWS_IAM: only signed requests get through, and the OAC below makes
        # CloudFront the only signer allowed. NONE would let anyone call it.
        api_url = api.add_function_url(auth_type=lambda_.FunctionUrlAuthType.AWS_IAM)

        # --- the page ------------------------------------------------------------
        # DESTROY: the page is rebuilt from git at every deploy, so nothing is lost.
        site_bucket = s3.Bucket(
            self,
            "SiteBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # --- one address for both ---------------------------------------------
        distribution = cloudfront.Distribution(
            self,
            "Distribution",
            comment="Koopjeskompas: the page from S3, /api/* from Lambda",
            default_root_object="index.html",
            # Edge locations in Europe and North America only: the cheapest
            # class, and the visitors are in the Netherlands.
            price_class=cloudfront.PriceClass.PRICE_CLASS_100,
            # Everything else: the page's files, cached. OAC signs the requests,
            # and CDK writes the bucket policy that lets only this distribution read.
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(site_bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
            ),
            additional_behaviors={
                "/api/*": cloudfront.BehaviorOptions(
                    origin=origins.FunctionUrlOrigin.with_origin_access_control(
                        api_url
                    ),
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    # POST /api/rank, so not just GET and HEAD.
                    allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                    # A ranking depends on the request body: never serve a cached one.
                    cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                    # Passes on Content-Type and x-amz-content-sha256, but not Host:
                    # the Function URL only answers to its own host name.
                    origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
                ),
            },
        )

        # Upload the page and drop CloudFront's cached index.html, which names the
        # current JS and CSS files. Those have new names in each build, so they
        # need no invalidation; files from older builds are removed (prune).
        s3deploy.BucketDeployment(
            self,
            "Site",
            sources=site_sources,
            destination_bucket=site_bucket,
            distribution=distribution,
            distribution_paths=["/index.html"],
            # The upload runs as a helper Lambda; without its own log group, Lambda
            # makes one that keeps every deploy's logs forever and outlives the stack.
            log_group=logs.LogGroup(
                self,
                "SiteDeploymentLogs",
                retention=logs.RetentionDays.ONE_WEEK,
                removal_policy=RemovalPolicy.DESTROY,
            ),
        )

        CfnOutput(
            self,
            SITE_URL_OUTPUT,
            value=f"https://{distribution.distribution_domain_name}",
            description="The demo",
        )
        CfnOutput(
            self,
            DATA_BUCKET_OUTPUT,
            value=data_bucket.bucket_name,
            description="Where koopjeskompas publish-deals uploads the snapshots",
        )
