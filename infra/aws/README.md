# infra: the AWS demo as code

An [AWS CDK](https://docs.aws.amazon.com/cdk/) app in Python that defines the whole demo from
[PLAN.md §9.3](../PLAN.md): the page in a private S3 bucket and the API in a Lambda function, both
behind one CloudFront distribution.

```
Browser ──► CloudFront ──┬─► S3: the page (frontend/dist)
                         └─► /api/* ─► Lambda Function URL: the API (build/lambda.zip)
                                           │ downloads at cold start
                                           ▼
                                       S3: deals/<chain>.json (koopjeskompas publish-deals)
```

- `stack.py`: the resources, in the order they were first built by hand in the console.
- `app.py`: hands the stack the real builds and fixes the Region (eu-north-1).
- `cdk.json`: tells the `cdk` command how to run `app.py`.
- `package.json`: pins the `cdk` command itself (it's a Node program; the stack is Python).

`tests/infra/aws/test_stack.py` checks the synthesised template (who may read or call what), with no
AWS account needed, so it runs in CI.

## Deploying

From the repository root, signed in with `aws login`:

```bash
cd infra/aws && npm ci && npx cdk bootstrap && cd ../..   # once per account and Region
scripts/deploy.sh                                  # every deploy
```

`cdk bootstrap` creates a stack called `CDKToolkit`: a bucket for uploads and the roles CDK deploys
through. `scripts/deploy.sh` builds the Lambda zip and the page, runs `cdk deploy`, and uploads the
deal snapshots. CDK stops to ask before any change that widens access (IAM, for example). The demo's
address is printed at the end as `Koopjeskompas.SiteUrl`.

To see what a deploy would change without changing anything:

```bash
cd infra/aws && npx cdk diff
```

## The weekly snapshot

Once a week, preferably on Tuesday (when AH's, Jumbo's and Lidl's new deals are all out):

```bash
scripts/refresh-deals.sh        # fetch every chain's deals, then publish them
```

It checks the AWS login before asking any supermarket, and if one chain fails it still publishes
the others and says which failed. New Lambda environments use the new snapshots at once; warm ones
within hours. Until a chain's new snapshot arrives, the API ranks its old one on its last day
(`domain.scoring.chain_ranking_days`).

## Tearing it down

```bash
cd infra/aws && npx cdk destroy
```

This deletes everything except the data bucket, which is kept on purpose (`RETAIN`) so old
snapshots survive. Delete it by hand in the S3 console if you really want it gone.

## Cutover from the hand-made setup (once)

The first CDK deploy creates new resources next to the ones built by hand, with a new
`*.cloudfront.net` address. Once the new address works, delete the old ones, in this order (later
items depend on earlier ones):

1. **CloudFront › the old distribution:** *Disable*, wait until it's deployed, then *Delete*.
   A distribution can only be deleted once disabled.
2. **CloudFront › Origin access › Origin access controls:** delete the two old OACs (one for S3,
   one for Lambda). They can only go once no distribution uses them.
3. **Lambda › koopjeskompas-api:** delete the function. Its Function URL and permissions go with it.
4. **CloudWatch › Log groups › `/aws/lambda/koopjeskompas-api`:** delete it; logs outlive their function.
5. **IAM › Roles › `koopjeskompas-api-role-…`:** delete it, with its inline policy.
6. **S3:** empty, then delete `koopjeskompas-site-…` and `koopjeskompas-data`. The data bucket is
   versioned, so *Empty* removes old versions too.

Keep the budget (`koopjeskompas-zero-spend`): it's account-wide and not part of the stack.
