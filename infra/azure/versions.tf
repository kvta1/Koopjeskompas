# Which Terraform and which provider versions this code is written for, and where the
# state lives.
#
# `~>` allows newer minor versions (1.17 → 1.18, 5.12 → 5.13) but not the next major
# one, which may break things. The exact provider version in use, with its checksums,
# is pinned in .terraform.lock.hcl, committed like uv.lock.

terraform {
  required_version = "~> 1.17"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 5.12"
    }
  }

  # The state: Terraform's record of what it built, which it compares with this code
  # on every plan. Kept in Azure Storage (scripts/azure/bootstrap-state.sh made it),
  # not on the laptop: it survives a lost laptop, a run takes a lock on it so two
  # applies can't collide, and GitHub Actions can reach it later (phase 4).
  #
  # use_azuread_auth: signed in as you (az login), like everything else here; the
  # storage account has no keys. Nothing in this block is secret, but the state itself
  # is: it holds the page's deployment token.
  backend "azurerm" {
    resource_group_name  = "rg-koopjeskompas-tfstate"
    storage_account_name = "stkoopjeskompastfstate"
    container_name       = "tfstate"
    key                  = "prod.tfstate"
    use_azuread_auth     = true
  }
}
