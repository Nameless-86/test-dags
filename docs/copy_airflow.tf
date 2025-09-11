#####################################################################################
# Airflow Namespace
#####################################################################################
resource "kubernetes_namespace" "airflow" {
  metadata {
    name        = "airflow"
    annotations = { name = "airflow" }
    labels      = { app = "airflow" }
  }
}

# resource "kubernetes_secret" "airflow_git_ssh" {
#   metadata {
#     name      = "airflow-git-ssh"
#     namespace = "airflow"
#   }

#   data = {
#     gitSshKey = filebase64("./keys/id_rsa")
#   }

#   type = "Opaque"
# }

#####################################################################################
# Airflow Helm Release (Apache official chart)
# Docs: https://airflow.apache.org/docs/helm-chart/stable/index.html
#####################################################################################
resource "helm_release" "airflow" {
  name             = "airflow"
  repository       = "https://airflow.apache.org"
  chart            = "airflow"
  version          = "1.16.0"
  namespace        = kubernetes_namespace.airflow.id
  create_namespace = false
  depends_on       = [module.eks, helm_release.ingress, helm_release.cert_manager]
  #timeout          = 900

  values = [yamlencode({
    executor          = "KubernetesExecutor"
    defaultAirflowTag = "2.10.5"

    webserver = {
      enabled   = true
      resources = { requests = { cpu = "200m", memory = "512Mi" }, limits = { cpu = "1", memory = "1Gi" } }
      startupProbe = {
        initialDelaySeconds = 30
        periodSeconds       = 10
        timeoutSeconds      = 20
        failureThreshold    = 18
      }
      waitForMigrations = {
        enabled = true
      }
      defaultUser = {
        enabled   = true
        username  = "admin"
        password  = "admin"
        email     = "admin@example.com"
        firstName = "Admin"
        lastName  = "User"
      }
    }
    scheduler = {
      resources = { requests = { cpu = "200m", memory = "512Mi" }, limits = { cpu = "1", memory = "1Gi" } }
      waitForMigrations = {
        enabled = true
      }
    }

    api = {
      enabled = false
    }

    triggerer = {
      enabled = false
    }
    dagProcessor = {
      enabled = false
    }
    dags = {
      gitSync = {
        enabled = true
        repo    = "https://github.com/Nameless-86/test-dags.git"
        branch  = "main"
        rev     = "HEAD"
        depth   = 1
        subPath = "dags"
        wait    = 60
      }
    }

    postgresql = {
      enabled = true
      primary = {
        resources = { requests = { cpu = "100m", memory = "256Mi" }, limits = { cpu = "500m", memory = "512Mi" } }
        persistence = {
          enabled = true
          size    = "5Gi"
        }
      }
    }


    #disable this when deploying via terraform or argocd
    createUserJob = {
      useHelmHooks   = false
      applyCustomEnv = false
    }

    migrateDatabaseJob = {
      useHelmHooks   = false
      applyCustomEnv = false
    }


  })]
}


resource "kubectl_manifest" "airflow_ingress" {
  yaml_body = yamlencode({
    apiVersion = "networking.k8s.io/v1"
    kind       = "Ingress"
    metadata = {
      name      = "ingress-airflow"
      namespace = kubernetes_namespace.airflow.metadata[0].name
      annotations = {
        "cert-manager.io/cluster-issuer" = "letsencrypt"
      }
    }
    spec = {
      ingressClassName = "nginx"
      rules = [
        {
          host = "airflow.dev.autoptic.com"
          http = {
            paths = [
              {
                path     = "/"
                pathType = "Prefix"
                backend  = { service = { name = "airflow-webserver", port = { number = 8080 } } }
              }
            ]
          }
        }
      ]
      tls = [
        {
          hosts      = ["airflow.dev.autoptic.com"]
          secretName = "airflow-tls"
        }
      ]
    }
  })

  depends_on = [
    helm_release.airflow
  ]
}

