"""The CDK app: what ``cdk synth`` and ``cdk deploy`` run (see cdk.json).

It hands the stack the real builds, so build them first; ``scripts/aws/deploy.sh`` does
all of it in order.
"""

import os
from pathlib import Path

import aws_cdk as cdk
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3_deployment as s3deploy

from infra.aws.stack import KoopjeskompasStack
from koopjeskompas.publish import REGION, STACK_NAME

ROOT = Path(__file__).resolve().parents[2]
LAMBDA_ZIP = ROOT / "build" / "lambda.zip"
PAGE_BUILD = ROOT / "frontend" / "dist"


def main() -> None:
    for path, build in [
        (LAMBDA_ZIP, "scripts/aws/build-lambda.sh"),
        (PAGE_BUILD, "npm run build (in frontend/)"),
    ]:
        if not path.exists():
            raise SystemExit(f"{path} is missing: run {build} first.")

    app = cdk.App()
    KoopjeskompasStack(
        app,
        STACK_NAME,
        api_code=lambda_.Code.from_asset(str(LAMBDA_ZIP)),
        site_sources=[s3deploy.Source.asset(str(PAGE_BUILD))],
        # The account comes from your `aws login` session; the Region is fixed.
        env=cdk.Environment(
            account=os.environ.get("CDK_DEFAULT_ACCOUNT"), region=REGION
        ),
        description="Koopjeskompas demo: page on S3 + CloudFront, API on Lambda",
    )
    # Tagged, so Cost Explorer can show what this project costs.
    cdk.Tags.of(app).add("project", "koopjeskompas")
    app.synth()


if __name__ == "__main__":
    main()
