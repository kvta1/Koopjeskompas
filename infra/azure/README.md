# infra/azure: the Azure demo as code

[Terraform](https://developer.hashicorp.com/terraform) code for the second copy of the demo, on
Azure. It's the same app as the AWS demo in [`infra/aws/`](../aws/README.md); only the hosting
differs. The page and the API have their own domains here, so the page is built with the API's
address and the API allows the page's address (CORS).

```
Browser ──► Static Web App: the page (frontend/dist, built with VITE_API_BASE_URL)
   │
   └──────► Container App: the API (ghcr.io/kvta1/koopjeskompas-api:<commit>)
              │ user-assigned identity, "Storage Blob Data Reader" on one container
              │ downloads at start
              ▼
            Blob Storage: data/deals/<chain>.json (koopjeskompas publish-deals --cloud azure)

            Log Analytics: the app's console and system logs (daily cap 0.1 GB)
```

| File | What |
|---|---|
| `versions.tf` | Terraform and provider versions, and where the state is kept |
| `providers.tf` | how the Azure provider signs in (your `az login`) and behaves |
| `variables.tf` | the inputs; only `image_tag` has no default |
| `main.tf` | the names, the tags and the resource group |
| `storage.tf` | Blob Storage for the deals, and your role to upload them |
| `api.tf` | identity, logs, Container Apps environment and the app |
| `page.tf` | the Static Web App |
| `outputs.tf` | addresses and the page's deployment token, for the deploy script |
| `tests/prod.tftest.hcl` | `terraform test` with a mocked provider: no Azure needed |
| `.terraform.lock.hcl` | the exact provider version and its checksums (commit it, like `uv.lock`) |

## The first time

1. **Install Terraform** from HashiCorp's apt repository, for Ubuntu:

   ```bash
   wget -O- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
   echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
   sudo apt update && sudo apt install terraform
   terraform version   # 1.17 or newer
   ```

2. **Sign in** to Azure and to GitHub's container registry:

   ```bash
   az login
   docker login ghcr.io   # your GitHub name, and a token with write:packages
   ```

3. **Create the state storage** once: `scripts/bootstrap-azure-state.sh`. Terraform keeps its
   record of what it built there, rather than on the laptop.

## Deploying

From the repository root:

```bash
scripts/deploy-azure.sh
```

This deploys the image, the infrastructure, the page and the deals, then checks the API answers.
Terraform shows its plan and asks before changing anything: read the plan. Lines starting with
`-` or `-/+` mean something is deleted or replaced.

The weekly deals: `scripts/refresh-deals.sh --azure` publishes to AWS and Azure.

Useful on their own (set `ARM_SUBSCRIPTION_ID=$(az account show --query id -o tsv)` first):

```bash
terraform -chdir=infra/azure plan -var image_tag=$(git rev-parse --short HEAD)   # what would change
terraform -chdir=infra/azure output                                              # the addresses
terraform -chdir=infra/azure test                                                # the tests, no Azure
```

## Good to know

- **Don't change these resources in the portal.** Terraform would undo it on the next apply. You
  can see such "drift" as unexpected changes in `terraform plan`. Change the code instead.
- **On a first deploy the app may not start straight away**, for two reasons:
  - a new role can take a few minutes to work everywhere;
  - the deals are uploaded after the app is created.

  Container Apps keeps retrying. The deploy script's health check waits two minutes and shows
  where the logs are otherwise.
- **The state holds a secret:** the page's deployment token. That's one reason it's kept in a
  private, keyless storage account rather than on disk.
- **Costs:**
  - The Container App scales to zero and has at most one replica.
  - Logs are capped at 0.1 GB a day.
  - The page is on the Free plan.
  - The storage holds a few MB.

  Normally all of this stays within the free allowances.

## Tearing down

```bash
terraform -chdir=infra/azure destroy -var image_tag=$(git rev-parse --short HEAD)
```

This removes everything Terraform built. The state storage (`rg-koopjeskompas-tfstate`) stays.
It's locked against deletion; to remove it too, first run
`az lock delete --name keep-terraform-state --resource-group rg-koopjeskompas-tfstate`.
