# infra: the demos as code

The same app runs as two demos, one per cloud. Each folder defines one of them, with that
cloud's usual tool. The app's own cloud code is split the same way, in `koopjeskompas/cloud/`.

| | [`aws/`](aws/README.md) | [`azure/`](azure/README.md) |
|---|---|---|
| Tool | AWS CDK (Python) | Terraform |
| Page | S3 + CloudFront | Static Web App |
| API | Lambda (the zip from `scripts/aws/build-lambda.sh`) | Container App (the image from the `Dockerfile`) |
| Deals | S3 bucket | Blob Storage container |
| Page and API | one domain (CloudFront sends `/api/*` to the Lambda) | two domains, so CORS |
| Region | eu-north-1 | germanywestcentral |
| Deploy | `scripts/aws/deploy.sh` | `scripts/azure/deploy.sh` |
| Tests, no cloud needed | `tests/infra/aws/` (synthesised template) | `azure/tests/` (`terraform test`, mocked provider) |

The weekly deals go to both with `scripts/refresh-deals.sh --azure`, or to AWS alone without
`--azure`.
