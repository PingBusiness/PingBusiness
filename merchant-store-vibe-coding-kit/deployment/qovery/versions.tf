terraform {
  required_version = ">= 1.5.0"

  required_providers {
    qovery = {
      source  = "qovery/qovery"
      version = "= 0.86.1"
    }
  }
}

provider "qovery" {}
