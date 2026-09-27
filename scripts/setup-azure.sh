#!/usr/bin/env bash
# Azure Container Apps Infrastructure Setup Script
# Run this script to create the Azure resources needed for deployment
# Azure Container Apps インフラ構築スクリプト
# デプロイに必要な Azure リソースを作成するために実行してください

set -euo pipefail

: "${GITHUB_OIDC_SUBJECT:?Set the exact observed GitHub stg OIDC subject}"

# Configuration - Modify these values
RESOURCE_GROUP="rg-genai-student-jp"
LOCATION="japaneast"  # Choose: japaneast, eastus, westeurope, etc.
CONTAINER_APP_ENV="rag-env"
CONTAINER_APP_NAME="serverless-rag-api"
LOG_ANALYTICS_WORKSPACE="log-${CONTAINER_APP_ENV}"
# Best-effort cap: Azure can ingest and bill above the configured threshold.
LOG_DAILY_QUOTA_GB="0.16"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Azure Container Apps Setup ===${NC}"
echo ""

# Check if logged in
echo "Checking Azure CLI login status..."
if ! az account show &> /dev/null; then
    echo -e "${YELLOW}Not logged in. Running 'az login'...${NC}"
    az login
fi

# Keep setup behavior reproducible instead of installing an arbitrary future
# Container Apps CLI extension release.
az extension add --name containerapp --version 0.3.55 --upgrade --yes

SUBSCRIPTION=$(az account show --query name -o tsv)
echo -e "Using subscription: ${GREEN}$SUBSCRIPTION${NC}"
echo ""

# Create Resource Group
echo "Creating Resource Group: $RESOURCE_GROUP..."
az group create \
    --name "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --output none
echo -e "${GREEN}✓ Resource Group created${NC}"

# Create a capped Log Analytics workspace explicitly; letting
# `az containerapp env create` generate one leaves it without a daily cap.
echo "Creating Log Analytics workspace: $LOG_ANALYTICS_WORKSPACE..."
az monitor log-analytics workspace create \
    --resource-group "$RESOURCE_GROUP" \
    --workspace-name "$LOG_ANALYTICS_WORKSPACE" \
    --location "$LOCATION" \
    --retention-time 30 \
    --quota "$LOG_DAILY_QUOTA_GB" \
    --output none
LOG_WORKSPACE_ID=$(az monitor log-analytics workspace show \
    --resource-group "$RESOURCE_GROUP" \
    --workspace-name "$LOG_ANALYTICS_WORKSPACE" \
    --query customerId -o tsv)
LOG_WORKSPACE_KEY=$(az monitor log-analytics workspace get-shared-keys \
    --resource-group "$RESOURCE_GROUP" \
    --workspace-name "$LOG_ANALYTICS_WORKSPACE" \
    --query primarySharedKey -o tsv)
echo -e "${GREEN}✓ Log Analytics workspace created (daily cap ${LOG_DAILY_QUOTA_GB} GB)${NC}"

# Create Container Apps Environment
echo "Creating Container Apps Environment: $CONTAINER_APP_ENV..."
az containerapp env create \
    --name "$CONTAINER_APP_ENV" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --logs-workspace-id "$LOG_WORKSPACE_ID" \
    --logs-workspace-key "$LOG_WORKSPACE_KEY" \
    --output none
unset LOG_WORKSPACE_KEY
echo -e "${GREEN}✓ Container Apps Environment created${NC}"

# Create Container App (placeholder image, will be updated by CD)
echo "Creating Container App: $CONTAINER_APP_NAME..."
az containerapp create \
    --name "$CONTAINER_APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$CONTAINER_APP_ENV" \
    --image mcr.microsoft.com/azuredocs/containerapps-helloworld@sha256:e9b3e7c34664c7cffd7144864b0e4eec369bfde80068f9095dc63b37058bec48 \
    --target-port 8000 \
    --ingress external \
    --revisions-mode multiple \
    --min-replicas 0 \
    --max-replicas 1 \
    --cpu 0.5 \
    --memory 1Gi \
    --output none

echo -e "${GREEN}✓ Container App created${NC}"
echo ""

# Create a deployment identity without a password. Bootstrap is explicit;
# existing installations should import/manage the identity through Terraform.
echo "Creating OIDC application for GitHub Actions..."
CLIENT_ID=$(az ad app create --display-name "sp-github-rag-deploy" --query appId -o tsv)
SP_ID=$(az ad sp create --id "$CLIENT_ID" --query id -o tsv)
SUBSCRIPTION_ID=$(az account show --query id -o tsv)
az role assignment create --assignee-object-id "$SP_ID" --assignee-principal-type ServicePrincipal \
    --role Contributor --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP" --output none
FEDERATED_FILE=$(mktemp)
trap 'rm -f "$FEDERATED_FILE"' EXIT
python3 -c 'import json, os; print(json.dumps({"name":"github-actions-stg", "issuer":"https://token.actions.githubusercontent.com", "subject":os.environ["GITHUB_OIDC_SUBJECT"], "audiences":["api://AzureADTokenExchange"]}))' > "$FEDERATED_FILE"
az ad app federated-credential create --id "$CLIENT_ID" --parameters "$FEDERATED_FILE" --output none
rm -f "$FEDERATED_FILE"
trap - EXIT

echo "Set GitHub stg secrets AZURE_CLIENT_ID=$CLIENT_ID, AZURE_SUBSCRIPTION_ID=$SUBSCRIPTION_ID"
echo "AZURE_TENANT_ID=$(az account show --query tenantId -o tsv)"
echo "Also set CANARY_CACHE_BYPASS_TOKEN in GitHub stg and in the Container App."

# Configure the application only when required values arrive via the process
# environment. Shell history and terminal output never contain secret values.
if [ -n "${AZURE_SEARCH_ENDPOINT:-}" ] && [ -n "${AZURE_SEARCH_QUERY_KEY:-}" ] && [ -n "${OPENAI_API_KEY:-}" ]; then
    : "${CANARY_CACHE_BYPASS_TOKEN:?CANARY_CACHE_BYPASS_TOKEN is required for CD}"
    echo "Configuring named Container Apps secrets and 3.2 environment..."

    secret_args=(
        "azure-search-query-key=$AZURE_SEARCH_QUERY_KEY"
        "canary-cache-bypass-token=$CANARY_CACHE_BYPASS_TOKEN"
        "openai-key=$OPENAI_API_KEY"
    )
    app_env_args=(
        "AZURE_SEARCH_ENDPOINT=$AZURE_SEARCH_ENDPOINT"
        "AZURE_SEARCH_QUERY_KEY=secretref:azure-search-query-key"
        "CANARY_CACHE_BYPASS_TOKEN=secretref:canary-cache-bypass-token"
        "AZURE_SEARCH_INDEX_NAME=ragdocs-v4"
        "OPENAI_API_KEY=secretref:openai-key"
        "OPENAI_MODEL=gpt-5.6-terra"
        "OPENAI_MAX_OUTPUT_TOKENS=1200"
        "OPENAI_REASONING_EFFORT=low"
        "OPENAI_VERBOSITY=low"
        "EMBEDDING_OFFLINE=1"
        "EMBEDDING_THREADS=1"
        "DD_TRACE_ENABLED=false"
        "DD_LLMOBS_ENABLED=false"
        "DD_TRACE_OPENAI_ENABLED=false"
    )

    if [ -n "${DD_API_KEY:-}" ]; then
        secret_args+=("dd-api-key=$DD_API_KEY")
    fi

    az containerapp secret set \
        --name "$CONTAINER_APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --secrets "${secret_args[@]}" \
        --output none
    az containerapp update \
        --name "$CONTAINER_APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --set-env-vars "${app_env_args[@]}" \
        --output none

    unset AZURE_SEARCH_QUERY_KEY OPENAI_API_KEY
    if [ -n "${DD_API_KEY:-}" ]; then
        unset DD_API_KEY
    fi
    echo -e "${GREEN}✓ Named secrets and environment references configured${NC}"
else
    echo -e "${YELLOW}Application secrets were not configured.${NC}"
    echo "Do not rerun the full bootstrap solely to add them: that would create"
    echo "another Service Principal credential. Set the named Container App secrets"
    echo "and env references separately with Azure CLI, supplying values through"
    echo "the process environment. DD_API_KEY is optional; never print the values."
fi
