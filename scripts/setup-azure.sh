#!/usr/bin/env bash
# Azure Container Apps Infrastructure Setup Script
# Run this script to create the Azure resources needed for deployment
# Azure Container Apps インフラ構築スクリプト
# デプロイに必要な Azure リソースを作成するために実行してください

set -euo pipefail

# Configuration - Modify these values
RESOURCE_GROUP="rg-genai-student-jp"
LOCATION="japaneast"  # Choose: japaneast, eastus, westeurope, etc.
CONTAINER_APP_ENV="rag-env"
CONTAINER_APP_NAME="serverless-rag-api"
LOG_ANALYTICS_WORKSPACE="log-${CONTAINER_APP_ENV}"
# 0.16 GB/day keeps log ingestion inside the 5 GB/month free allowance.
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

# Get the app URL
APP_URL=$(az containerapp show \
    --name "$CONTAINER_APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query properties.configuration.ingress.fqdn \
    -o tsv)

echo -e "${GREEN}✓ Container App created${NC}"
echo ""

# Create Service Principal for GitHub Actions. The JSON is written to a
# permission-600 file and is never printed to the terminal.
echo "Creating Service Principal for GitHub Actions..."
SP_OUTPUT_FILE=$(mktemp "${TMPDIR:-/tmp}/azure-credentials.XXXXXX")
chmod 600 "$SP_OUTPUT_FILE"

cleanup_credentials_on_error() {
    exit_code=$?
    trap - EXIT
    if [ "$exit_code" -ne 0 ]; then
        rm -f "$SP_OUTPUT_FILE"
    fi
    exit "$exit_code"
}
trap cleanup_credentials_on_error EXIT

az ad sp create-for-rbac \
    --name "sp-github-rag-deploy" \
    --role contributor \
    --scopes "/subscriptions/$(az account show --query id -o tsv)/resourceGroups/$RESOURCE_GROUP" \
    --sdk-auth >"$SP_OUTPUT_FILE"

python3 -c \
    'import json, sys; data=json.load(open(sys.argv[1], encoding="utf-8")); print("Client ID:       " + data["clientId"]); print("Tenant ID:       " + data["tenantId"]); print("Subscription ID: " + data["subscriptionId"])' \
    "$SP_OUTPUT_FILE"

trap - EXIT

echo ""
echo -e "${GREEN}=== Setup Complete! ===${NC}"
echo ""
echo -e "Container App URL: ${GREEN}https://$APP_URL${NC}"
echo ""
echo -e "${YELLOW}=== IMPORTANT: GitHub Secrets Setup ===${NC}"
echo ""
echo "The Service Principal JSON was written to a permission-600 temporary file:"
echo "  $SP_OUTPUT_FILE"
echo "Set it without printing the value:"
echo "  gh secret set AZURE_CREDENTIALS < \"$SP_OUTPUT_FILE\""
echo "Then securely delete the temporary file after confirming the secret:"
echo "  rm -f \"$SP_OUTPUT_FILE\""
echo ""

# Configure the application only when required values arrive via the process
# environment. Shell history and terminal output never contain secret values.
if [ -n "${AZURE_SEARCH_ENDPOINT:-}" ] && [ -n "${AZURE_SEARCH_API_KEY:-}" ] && [ -n "${OPENAI_API_KEY:-}" ]; then
    echo "Configuring named Container Apps secrets and 3.1 environment..."

    secret_args=(
        "azure-search-api-key=$AZURE_SEARCH_API_KEY"
        "openai-key=$OPENAI_API_KEY"
    )
    app_env_args=(
        "AZURE_SEARCH_ENDPOINT=$AZURE_SEARCH_ENDPOINT"
        "AZURE_SEARCH_API_KEY=secretref:azure-search-api-key"
        "AZURE_SEARCH_INDEX_NAME=ragdocs-v4"
        "OPENAI_API_KEY=secretref:openai-key"
        "OPENAI_MODEL=gpt-5.6-terra"
        "OPENAI_MAX_OUTPUT_TOKENS=1200"
        "OPENAI_REASONING_EFFORT=low"
        "OPENAI_VERBOSITY=low"
        "EMBEDDING_MODEL=intfloat/multilingual-e5-small"
        "EMBEDDING_MODEL_REVISION=614241f622f53c4eeff9890bdc4f31cfecc418b3"
        "EMBEDDING_VARIANT=onnx-qint8"
        "EMBEDDING_OFFLINE=1"
        "EMBEDDING_THREADS=1"
        "DD_TRACE_ENABLED=false"
    )

    if [ -n "${DD_API_KEY:-}" ]; then
        secret_args+=("dd-api-key=$DD_API_KEY")
        app_env_args+=("DD_API_KEY=secretref:dd-api-key")
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

    unset AZURE_SEARCH_API_KEY OPENAI_API_KEY
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
