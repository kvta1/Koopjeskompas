# The inputs. Only image_tag has no default: every deploy says which image to run.

variable "environment" {
  description = "Name of this copy of the demo, part of every resource name (rg-koopjeskompas-prod)."
  type        = string
  default     = "prod"
}

variable "location" {
  description = "Azure region for everything except the page."
  type        = string
  # West Europe refused new storage accounts for this subscription (2026-11-12).
  default = "germanywestcentral"
}

variable "page_location" {
  description = "Azure region of the Static Web App: only where its settings are kept, the files are served worldwide."
  type        = string
  # Static Web Apps offers few regions, and West Europe is refused for this subscription.
  default = "eastus2"
}

variable "image" {
  description = "The API's container image, without tag."
  type        = string
  default     = "ghcr.io/kvta1/koopjeskompas-api"
}

variable "image_tag" {
  description = "Which build of the image to run: the git commit it was built from (git rev-parse --short HEAD)."
  type        = string

  validation {
    condition     = can(regex("^[0-9a-f]{7,40}$", var.image_tag))
    error_message = "image_tag must be a git commit hash, so every deploy says exactly which code runs (never 'latest')."
  }
}
