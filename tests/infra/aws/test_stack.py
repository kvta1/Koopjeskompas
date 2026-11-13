"""The CDK stack, checked on its synthesised CloudFormation template.

Synthesising needs no AWS account or credentials, so these run in CI. Each test pins
down a decision from PLAN.md §9.3, mostly about who may read or call what: if a change
loosens one of them, a test here fails before anything is deployed.
"""

from collections.abc import Mapping
from typing import Any

import aws_cdk as cdk
import pytest
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3_deployment as s3deploy
from aws_cdk.assertions import Match, Template

from infra.aws.stack import API_HANDLER, KoopjeskompasStack

# AWS's managed CloudFront policies, by their fixed IDs.
CACHING_DISABLED = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
ALL_VIEWER_EXCEPT_HOST_HEADER = "b689b0a8-53d0-40ab-baf2-68738e2966ac"


@pytest.fixture(scope="module")
def template() -> Template:
    app = cdk.App()
    stack = KoopjeskompasStack(
        app,
        "Test",
        # Stand-ins for the real builds, which tests don't need.
        api_code=lambda_.Code.from_inline("def handler(event, context): pass"),
        site_sources=[s3deploy.Source.data("index.html", "<!doctype html>")],
        env=cdk.Environment(account="111111111111", region="eu-north-1"),
    )
    return Template.from_stack(stack)


def resources(template: Template, type_: str) -> Mapping[str, Any]:
    return template.find_resources(type_)


def the_distribution(template: Template) -> Any:
    (distribution,) = resources(template, "AWS::CloudFront::Distribution").values()
    return distribution["Properties"]["DistributionConfig"]


def test_both_buckets_are_private_and_https_only(template: Template) -> None:
    buckets = resources(template, "AWS::S3::Bucket")
    assert len(buckets) == 2
    for bucket in buckets.values():
        assert bucket["Properties"]["PublicAccessBlockConfiguration"] == {
            "BlockPublicAcls": True,
            "BlockPublicPolicy": True,
            "IgnorePublicAcls": True,
            "RestrictPublicBuckets": True,
        }
    # enforce_ssl: each bucket policy denies plain-HTTP requests.
    for policy in resources(template, "AWS::S3::BucketPolicy").values():
        statements = policy["Properties"]["PolicyDocument"]["Statement"]
        assert any(
            s["Effect"] == "Deny"
            and s["Condition"] == {"Bool": {"aws:SecureTransport": "false"}}
            for s in statements
        )


def test_the_data_bucket_keeps_old_snapshots_and_survives_the_stack(
    template: Template,
) -> None:
    template.has_resource(
        "AWS::S3::Bucket",
        {
            "Properties": Match.object_like(
                {"VersioningConfiguration": {"Status": "Enabled"}}
            ),
            "DeletionPolicy": "Retain",
            "UpdateReplacePolicy": "Retain",
        },
    )


def test_the_api_function(template: Template) -> None:
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Runtime": "python3.14",
            "Architectures": ["arm64"],
            "Handler": API_HANDLER,
            "MemorySize": 512,
            "Timeout": 10,
            "ReservedConcurrentExecutions": 5,
            "Environment": {"Variables": {"DEALS_BUCKET": Match.any_value()}},
        },
    )
    template.has_resource_properties("AWS::Logs::LogGroup", {"RetentionInDays": 7})


def test_every_log_group_of_the_stack_expires(template: Template) -> None:
    # The API's and the page upload's; logs kept forever cost a little each month.
    groups = resources(template, "AWS::Logs::LogGroup").values()
    assert len(groups) == 2
    assert all(g["Properties"]["RetentionInDays"] == 7 for g in groups)
    assert all(g["DeletionPolicy"] == "Delete" for g in groups)


def test_the_api_may_only_read_the_snapshots(template: Template) -> None:
    policies = [
        statement
        for policy in resources(template, "AWS::IAM::Policy").values()
        if any("Api" in role["Ref"] for role in policy["Properties"]["Roles"])
        for statement in policy["Properties"]["PolicyDocument"]["Statement"]
    ]
    assert len(policies) == 1
    (statement,) = policies
    assert statement["Action"] == "s3:GetObject"
    assert statement["Effect"] == "Allow"
    # The ARN is built from the bucket's at deploy time; it must end in deals/*.
    assert statement["Resource"]["Fn::Join"][1][-1] == "/deals/*"


def test_only_this_distribution_may_call_the_api(template: Template) -> None:
    template.has_resource_properties("AWS::Lambda::Url", {"AuthType": "AWS_IAM"})

    (distribution_id,) = resources(template, "AWS::CloudFront::Distribution")
    permissions = resources(template, "AWS::Lambda::Permission").values()
    # Since October 2025 a Function URL needs both actions; one alone is a 403.
    by_action = {p["Properties"]["Action"]: p["Properties"] for p in permissions}
    assert set(by_action) == {"lambda:InvokeFunctionUrl", "lambda:InvokeFunction"}
    for permission in by_action.values():
        assert permission["Principal"] == "cloudfront.amazonaws.com"
        source_arn = permission["SourceArn"]["Fn::Join"][1]
        assert ":distribution/" in source_arn
        assert {"Ref": distribution_id} in source_arn
    assert by_action["lambda:InvokeFunction"]["InvokedViaFunctionUrl"] is True


def test_both_origins_are_signed_by_cloudfront(template: Template) -> None:
    access_controls = [
        oac["Properties"]["OriginAccessControlConfig"]
        for oac in resources(template, "AWS::CloudFront::OriginAccessControl").values()
    ]
    assert sorted(c["OriginAccessControlOriginType"] for c in access_controls) == [
        "lambda",
        "s3",
    ]
    assert all(c["SigningBehavior"] == "always" for c in access_controls)


def test_the_page_is_served_over_https_from_its_root(template: Template) -> None:
    config = the_distribution(template)
    assert config["DefaultRootObject"] == "index.html"
    assert config["PriceClass"] == "PriceClass_100"
    assert config["DefaultCacheBehavior"]["ViewerProtocolPolicy"] == "redirect-to-https"
    # Left out of the template means CloudFormation's default: GET and HEAD only.
    assert config["DefaultCacheBehavior"].get("AllowedMethods", ["GET", "HEAD"]) == [
        "GET",
        "HEAD",
    ]


def test_api_requests_go_to_the_lambda_uncached(template: Template) -> None:
    (api,) = the_distribution(template)["CacheBehaviors"]
    assert api["PathPattern"] == "/api/*"
    assert "POST" in api["AllowedMethods"]
    assert api["ViewerProtocolPolicy"] == "redirect-to-https"
    assert api["CachePolicyId"] == CACHING_DISABLED
    assert api["OriginRequestPolicyId"] == ALL_VIEWER_EXCEPT_HOST_HEADER


def test_a_deploy_refreshes_the_cached_index_page(template: Template) -> None:
    template.has_resource_properties(
        "Custom::CDKBucketDeployment",
        {"DistributionPaths": ["/index.html"], "Prune": True},
    )


def test_outputs_for_the_deploy_tools(template: Template) -> None:
    outputs = template.find_outputs("*")
    assert {"SiteUrl", "DataBucketName"} <= set(outputs)
